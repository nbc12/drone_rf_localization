#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 gr-aoa author.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import numpy as np
from gnuradio import gr

class calc(gr.basic_block):
    """
    AoA Calculation Block (Vector Sum per Frame)
    
    Inputs:
        6 Complex Streams (Antenna 1-6)
    
    Output:
        1 Complex Stream (AoA Vector)
        - Angle = Direction of Arrival
        - Magnitude = Confidence/Strength
        
    Algorithm:
        1. Consumes 'slot_len' samples from each antenna.
        2. Calculates Mean Magnitude for each antenna over the slot.
        3. Computes Vector Sum: V = Sum( Mag_i * exp(j * Angle_i) )
        4. Outputs 1 complex sample V representing the cycle's AoA.
    """
    def __init__(self, sample_rate=10000000, dwell_time=45e-6, num_antennas=6, antenna_offset_deg=0.0):
        
        # Calculate Decimation Factor (Slot Length)
        guard_time = 2.0e-6
        samps_slot = int(sample_rate * dwell_time)
        samps_guard = int(sample_rate * guard_time)
        self.slot_len = samps_slot - 2 * samps_guard
        
        if self.slot_len < 1:
            raise ValueError(f"Calculated slot length is {self.slot_len} (too small). Check sample_rate/dwell_time.")

        gr.basic_block.__init__(self,
            name="AOA Vector Calc",
            in_sig=[np.complex64] * num_antennas,
            out_sig=[np.complex64])

        self.num_antennas = num_antennas
        
        # Pre-calculate Antenna Unit Vectors
        offset_rad = np.radians(antenna_offset_deg)
        self.unit_vectors = np.zeros(num_antennas, dtype=np.complex64)
        for i in range(num_antennas):
            angle = (i * (2 * np.pi / num_antennas)) + offset_rad
            self.unit_vectors[i] = np.exp(1j * angle)

    def general_work(self, input_items, output_items):
        n_out = len(output_items[0])
        n_in_available = len(input_items[0])
        
        # Calculate how many full vectors we can process
        n_process = min(n_out, n_in_available // self.slot_len)
        
        if n_process == 0:
            self.consume_each(0)
            return 0
            
        n_in_consume = n_process * self.slot_len
        
        out = output_items[0]
        vectors = np.zeros(n_process, dtype=np.complex64)
        
        for i in range(self.num_antennas):
            # Get data for antenna i
            frames = input_items[i][:n_in_consume].reshape((n_process, self.slot_len))
            
            # Calculate mean magnitude per frame
            magnitudes = np.mean(np.abs(frames), axis=1)
            
            # Sum into the output vector stream
            vectors += magnitudes * self.unit_vectors[i]
            
        out[:n_process] = vectors
        
        self.consume_each(n_in_consume)
        return n_process