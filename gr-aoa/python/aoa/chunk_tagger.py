import numpy as np
from gnuradio import gr
import os
import time
import datetime

class chunk_tagger(gr.sync_block):
    def __init__(self, samp_rate=2000000, seconds_per_chunk=1.0, base_path=".", files_per_folder=1000):
        # Initialize as a complex float block (standard for SDR)
        gr.sync_block.__init__(
            self,
            name='Chunk Tagger (Sink)', # Block name
            in_sig=[np.complex64],
            out_sig=[np.complex64]
        )
        self.samp_rate = samp_rate
        self.interval = int(samp_rate * seconds_per_chunk)
        self.base_path = base_path
        
        self.dir_index = 0
        self.files_in_current_dir = 0
        self.files_per_dir = files_per_folder
        self.current_file = None
        
        # Initial directory setup
        self._ensure_dir(os.path.join(self.base_path, "0"))
        self._ensure_dir(os.path.join(self.base_path, "1"))
        self._open_new_file()

    def _ensure_dir(self, path):
        if not os.path.exists(path):
            os.makedirs(path)

    def _get_filename(self):
        # Format: timestamp_micros.dat
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S_%f")
        return f"{timestamp}.dat"

    def _open_new_file(self):
        if self.current_file:
            self.current_file.close()
        
        # Check rotation
        if self.files_in_current_dir >= self.files_per_dir:
            self.dir_index += 1
            self.files_in_current_dir = 0
            # Pre-create next directory
            next_dir = os.path.join(self.base_path, str(self.dir_index + 1))
            self._ensure_dir(next_dir)
            
        # Construct path
        current_dir = os.path.join(self.base_path, str(self.dir_index))
        self._ensure_dir(current_dir) # Safety check
        
        filename = self._get_filename()
        full_path = os.path.join(current_dir, filename)
        
        self.current_file = open(full_path, "wb")
        self.files_in_current_dir += 1

    def work(self, input_items, output_items):
        in_data = input_items[0]
        out_data = output_items[0]
        
        # Pass data through
        out_data[:] = in_data
        
        n_items = len(in_data)
        written = 0
        
        start_index = self.nitems_written(0)
        
        # While we have data to write
        while written < n_items:
            # Samples left in current chunk
            # Calculate where we are in the current interval logic
            # Use absolute sample count to avoid drift
            samples_in_current_chunk = self.interval - (start_index % self.interval)
            
            # Samples we can write from this buffer
            to_write = min(n_items - written, samples_in_current_chunk)
            
            # Write to file
            chunk = in_data[written : written + to_write]
            chunk.tofile(self.current_file)
            
            written += to_write
            start_index += to_write
            
            # If we finished a chunk, rotate file
            # Use strict equality with interval boundary logic
            if (start_index % self.interval) == 0:
                self._open_new_file()
                
        return n_items

