#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2025 Trevor Buhler & Noah Christensen
#
# SPDX-License-Identifier: GPL-3.0-or-later

# TODO split this into 2 blocks, one for the splitting of the RF from the SDR, and another for the AOA calculation

import numpy
import serial
import time
from gnuradio import gr

class ArduinoSwitcherDriver:
    """Helper class to drive the SP8T Arduino Controller via Serial."""
    def __init__(self, port, baud_rate=115200):
        self.port = port
        self.baud = baud_rate
        self.ser = None
        self._connect()

    def _connect(self):
        try:
            print(f"[ArduinoDriver] Connecting to {self.port} @ {self.baud}...")
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            time.sleep(2)
            print("[ArduinoDriver] Connected.")
        except Exception as e:
            print(f"[ArduinoDriver] ERROR: Could not connect to Arduino: {e}")
            self.ser = None
            print(f"[ArduinoDriver] Warning: Hardware not found.")

    def send_command(self, cmd):
        if self.ser and self.ser.is_open:
            self.ser.reset_input_buffer()
            full_cmd = f"{cmd}\n"
            try:
                self.ser.write(full_cmd.encode('ascii'))
                line = self.ser.readline()
                if not line:
                    return
                response = line.decode('ascii').strip()
                expected = f"{cmd} set"
                if response.upper() != expected.upper():
                    print(f"[ArduinoDriver] Warning: Expected '{expected}', got '{response}'")
            except Exception as e:
                print(f"[ArduinoDriver] Communication Error: {e}")

    def set_dwell_time(self, microseconds):
        self.send_command(f"T{int(microseconds)}")

    def start_cycle(self):
        self.send_command("CYCLE")

    def stop_cycle(self):
        self.send_command("RFX")

    def close(self):
        if self.ser:
            try:
                self.stop_cycle()
            except:
                pass
            self.ser.close()
            print("[ArduinoDriver] Connection closed.")


class switch_sync(gr.sync_block):
    """
    Minimal Time Domain AOA Block
    Logic: Syncs to 'All Off' gap -> Captures Data -> Vector Sum -> Output.
    """
    def __init__(self,
                 sample_rate=10000000,
                 dwell_time=45e-6,
                 threshold=0.05,       # Static threshold for Sync
                 serial_port="",
                 baud_rate=115200,
                 max_antennas=6,
                 antenna_offset_deg=0.0,
                 settling_time=5e-6
                 ):

        gr.sync_block.__init__(self,
            name="AOA Switch Sync Minimal",
            in_sig=[numpy.complex64],
            out_sig=[numpy.complex64])

        # User Params
        self.threshold = threshold
        self.max_antennas = max_antennas

        # Timing Constants
        self.samples_per_antenna = int(sample_rate * dwell_time)
        self.settling_samp = int(sample_rate * settling_time)

        # RFX Gap Threshold (Look for 75% of the dwell time in silence)
        self.rfx_gap_threshold = int(self.samples_per_antenna * 0.75)

        # Hardware Control
        self.arduino = None
        if serial_port:
            self.arduino = ArduinoSwitcherDriver(serial_port, baud_rate)
            dwell_us = dwell_time * 1e6
            self.arduino.set_dwell_time(dwell_us)
            self.arduino.start_cycle()

        # Antenna Angles
        offset_rad = numpy.radians(antenna_offset_deg)
        self.antenna_angles = [
            (i * (2 * numpy.pi / self.max_antennas)) + offset_rad
            for i in range(self.max_antennas)
        ]

        # State Machine
        self.state = "SEARCH_RFX"
        self.counter = 0
        self.total_sample_counter = 0
        self.lastAOA = 0 + 0j

        self.reset_arrays()

    def stop(self):
        if self.arduino:
            self.arduino.close()
        return True

    def reset_arrays(self):
        self.antenna_data = [ [] for _ in range(self.max_antennas) ]

    def work(self, input_items, output_items):
        iq = input_items[0]
        out = output_items[0]
        n_items = len(iq)

        # 1. Vectorized Power Calculation
        power = iq.real**2 + iq.imag**2

        out[:] = self.lastAOA

        idx = 0
        while idx < n_items:

            # --- STATE 1: SEARCH FOR RFX GAP (Low Power) ---
            if self.state == "SEARCH_RFX":
                p_view = power[idx:]
                # Find samples ABOVE threshold (End of Gap / Start of RF1)
                high_indices = numpy.flatnonzero(p_view >= self.threshold)

                if len(high_indices) == 0:
                    # Entire buffer is low (Gap continues)
                    self.counter += len(p_view)
                    idx = n_items
                else:
                    # Found a Rising Edge
                    first_high = high_indices[0]
                    self.counter += first_high

                    if self.counter >= self.rfx_gap_threshold:
                        # VALID SYNC: We saw ~40us of silence, now signal is high.
                        # This moment is exactly the start of Antenna 1.
                        self.state = "CAPTURE_FRAME"
                        self.total_sample_counter = 0
                        self.reset_arrays()
                        idx += first_high
                        self.counter = 0
                    else:
                        # Glitch / Gap too short (e.g. video packet gap)
                        self.counter = 0
                        idx += first_high + 1

            # --- STATE 2: CAPTURE FRAME ---
            elif self.state == "CAPTURE_FRAME":
                total_frame_size = self.samples_per_antenna * self.max_antennas
                remaining_in_frame = total_frame_size - self.total_sample_counter
                remaining_in_input = n_items - idx
                n_process = min(remaining_in_frame, remaining_in_input)

                if n_process > 0:
                    chunk = iq[idx : idx + n_process]
                    start_frame_idx = self.total_sample_counter

                    # Distribute samples to antenna bins based on time index
                    for i in range(self.max_antennas):
                        w_start = i * self.samples_per_antenna + self.settling_samp
                        w_end = (i + 1) * self.samples_per_antenna

                        istart = max(start_frame_idx, w_start)
                        iend = min(start_frame_idx + n_process, w_end)

                        if istart < iend:
                            c_start = istart - start_frame_idx
                            c_end = iend - start_frame_idx
                            self.antenna_data[i].append(chunk[c_start:c_end])

                    self.total_sample_counter += n_process
                    idx += n_process

                if self.total_sample_counter >= total_frame_size:
                    self.calculate_aoa()
                    self.state = "SEARCH_RFX"
                    self.counter = 0

        return len(out)

    def calculate_aoa(self):
        # Flatten chunks
        raw_arrays = []
        for chunks in self.antenna_data:
            if chunks:
                raw_arrays.append(numpy.concatenate(chunks))
            else:
                raw_arrays.append(numpy.array([], dtype=numpy.complex64))

        if any(len(arr) == 0 for arr in raw_arrays): return

        # --- TIME DOMAIN AOA CALCULATION ---
        x_sum = 0.0
        y_sum = 0.0

        for i in range(self.max_antennas):
            magnitude_sum = numpy.sum(numpy.abs(raw_arrays[i]))

            x_sum += magnitude_sum * numpy.cos(self.antenna_angles[i])
            y_sum += magnitude_sum * numpy.sin(self.antenna_angles[i])

        self.lastAOA = complex(x_sum, y_sum)
