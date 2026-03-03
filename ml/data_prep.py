import os
import argparse
import datetime
import numpy as np
import pandas as pd
from pyproj import Geod

def parse_sdr_files(base_path):
    """Walks the directory and indexes SDR files by their start time."""
    sdr_files = []
    for root, _, files in os.walk(base_path):
        for file in files:
            if file.endswith('.dat'):
                # Expected format: YYYYMMDD_HHMMSS_ffffff.dat
                time_str = file.replace('.dat', '')
                try:
                    file_time = datetime.datetime.strptime(time_str, "%Y%m%d_%H%M%S_%f")
                    full_path = os.path.join(root, file)
                    sdr_files.append((file_time, full_path))
                except ValueError:
                    print(f"Skipping incorrectly named file: {file}")
    
    # Sort chronologically
    sdr_files.sort(key=lambda x: x[0])
    return sdr_files

def get_rf_chunk(start_time, duration_sec, sample_rate, sdr_files):
    """
    Fetches a specific chunk of RF data spanning `duration_sec`.
    Handles chunks that cross the boundary between two 4-second files.
    """
    samples_needed = int(duration_sec * sample_rate)
    chunk_data = np.array([], dtype=np.complex64)
    current_time = start_time

    while len(chunk_data) < samples_needed:
        # Find the file that contains the 'current_time'
        valid_files = [f for f in sdr_files if f[0] <= current_time]
        if not valid_files:
            return None # Missing data
        
        file_start_time, filepath = valid_files[-1]
        
        # Calculate how far into the file we need to start reading
        time_offset = (current_time - file_start_time).total_seconds()
        
        # If the file ended before our current_time, there's a gap in data
        if time_offset >= 4.0: 
            return None 
            
        sample_offset = int(time_offset * sample_rate)
        
        # Read the file
        file_data = np.fromfile(filepath, dtype=np.complex64)
        
        # Grab what we need (or what's left in the file)
        remaining_needed = samples_needed - len(chunk_data)
        available_in_file = len(file_data) - sample_offset
        to_take = min(remaining_needed, available_in_file)
        
        chunk_data = np.concatenate((chunk_data, file_data[sample_offset : sample_offset + to_take]))
        
        # Advance the time by the amount of data we just read
        current_time += datetime.timedelta(seconds=(to_take / sample_rate))

    return chunk_data

def main():
    parser = argparse.ArgumentParser(description="Join DJI Flight Logs with SDR IQ Data.")
    parser.add_argument('--sdr_dir', required=True, help="Root directory of the SDR .dat files.")
    parser.add_argument('--dji_log', required=True, help="Path to the DJI CSV flight log.")
    parser.add_argument('--out_dir', required=True, help="Directory to save the labeled 1-second chunks.")
    
    parser.add_argument('--lat', type=float, required=True, help="Station Latitude (decimal degrees).")
    parser.add_argument('--lon', type=float, required=True, help="Station Longitude (decimal degrees).")
    parser.add_argument('--heading', type=float, required=True, help="Station antenna heading (degrees from True North).")
    
    # Replaced time_shift with timezone
    parser.add_argument('--timezone', type=str, default='America/Denver', help="Local timezone of the SDR data (e.g., 'America/Denver', 'America/New_York').")
    
    parser.add_argument('--trim_start', type=float, default=0.0, help="Seconds to drop from the start of the joined data.")
    parser.add_argument('--trim_end', type=float, default=0.0, help="Seconds to drop from the end of the joined data.")
    
    args = parser.parse_args()
    
    os.makedirs(args.out_dir, exist_ok=True)
    SAMPLE_RATE = 250000
    WINDOW_SEC = 1.0

    print("Indexing SDR files...")
    sdr_files = parse_sdr_files(args.sdr_dir)
    if not sdr_files:
        print("No SDR files found! Check your directory.")
        return
    print(f"Found {len(sdr_files)} SDR files.")

    print("Parsing DJI Log...")
    # Skip the "sep=," row if it exists
    with open(args.dji_log, 'r') as f:
        first_line = f.readline()
    skip_rows = 1 if 'sep=' in first_line else 0
    df = pd.read_csv(args.dji_log, skiprows=skip_rows)

    # Combine Date and Time columns into a single datetime
    df['datetime_str'] = df['CUSTOM.date [local]'] + ' ' + df['CUSTOM.updateTime [local]']
    df['timestamp'] = pd.to_datetime(df['datetime_str'], format='mixed')
    
    # --- TIMEZONE HANDLING ---
    # 1. Localize the DJI timestamps to UTC (since they are logged in GPS/UTC time)
    # 2. Convert them to your local timezone (e.g., MST/MDT)
    # 3. Make them naive again so they perfectly match the naive SDR datetimes
    df['timestamp'] = df['timestamp'].dt.tz_localize('UTC') \
                                     .dt.tz_convert(args.timezone) \
                                     .dt.tz_localize(None)

    print("Calculating Polar Coordinates...")
    geod = Geod(ellps='WGS84')
    
    station_lons = [args.lon] * len(df)
    station_lats = [args.lat] * len(df)
    drone_lons = df['OSD.longitude'].values
    drone_lats = df['OSD.latitude'].values
    
    azimuths, _, distances = geod.inv(station_lons, station_lats, drone_lons, drone_lats)
    
    azimuths = (azimuths + 360) % 360
    relative_thetas = (azimuths - args.heading) % 360
    
    df['radius'] = distances 
    df['theta'] = relative_thetas 

    # Drop rows where drone lat/lon is missing/zero (before takeoff)
    df = df[(df['OSD.latitude'] != 0) & (df['OSD.longitude'] != 0)].dropna(subset=['OSD.latitude', 'OSD.longitude'])

    # Find intersection of times
    sdr_start = sdr_files[0][0]
    sdr_end = sdr_files[-1][0] + datetime.timedelta(seconds=4.0) 
    
    df = df[(df['timestamp'] >= sdr_start) & (df['timestamp'] <= sdr_end - datetime.timedelta(seconds=WINDOW_SEC))]
    
    if df.empty:
        print("ERROR: Timeframes do not overlap! Check your --timezone argument.")
        print(f"SDR Range: {sdr_start} to {sdr_end}")
        return

    # Apply user trimming
    flight_start = df['timestamp'].iloc[0] + pd.Timedelta(seconds=args.trim_start)
    flight_end = df['timestamp'].iloc[-1] - pd.Timedelta(seconds=args.trim_end)
    df = df[(df['timestamp'] >= flight_start) & (df['timestamp'] <= flight_end)]

    print(f"Extracted valid window. Processing {len(df)} overlapping chunks (10Hz)...")

    success_count = 0
    for index, row in df.iterrows():
        target_time = row['timestamp']
        radius = row['radius']
        theta = row['theta']
        
        chunk = get_rf_chunk(target_time, WINDOW_SEC, SAMPLE_RATE, sdr_files)
        
        if chunk is not None and len(chunk) == int(WINDOW_SEC * SAMPLE_RATE):
            time_str = target_time.strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{time_str}_R{radius:.1f}_T{theta:.1f}.dat"
            filepath = os.path.join(args.out_dir, filename)
            
            chunk.tofile(filepath)
            success_count += 1
            
            if success_count % 100 == 0:
                print(f"Processed {success_count} / {len(df)} chunks...")

    print(f"Done! Saved {success_count} labeled IQ chunks to {args.out_dir}")

"""python prep_rf_data.py \
  --sdr_dir "./raw_sdr_data" \
  --dji_log "./flight_log.csv" \
  --out_dir "./training_data" \
  --lat 40.29148 \
  --lon -111.73973 \
  --heading 180.0 \
  --timezone "America/Denver" \
  --trim_start 10 \
  --trim_end 5"""

if __name__ == "__main__":
    main()