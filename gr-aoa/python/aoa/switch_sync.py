#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 gr-aoa author.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import numpy
from gnuradio import gr
from .rf_switch_sync import RFSwitchSync

class switch_sync(gr.basic_block):
    """
    Switch Sync Demux Block
    
    Inputs:
        1 Complex Stream (Raw SDR Data)
    
    Outputs:
        7 Complex Streams:
          0: Antenna 1
          1: Antenna 2
          ...
          5: Antenna 6
          6: Dead Time (Noise/Terminated)
          
    Logic:
        Uses RFSwitchSync to detect the 'Dead Time' gap (falling edge of power).
        Aligns the stream and splits it into the 7 constituent segments.
    """
    def __init__(self,
                 sample_rate=10000000,
                 dwell_time=45e-6,
                 num_antennas=6,
                 threshold_percentile=10.0
                 ):

        # We have num_antennas + 1 outputs (Antennas + Dead Time)
        gr.basic_block.__init__(self,
            name="AOA Switch Sync Demux",
            in_sig=[numpy.complex64],
            out_sig=[numpy.complex64] * (num_antennas + 1)) 

        self.rf_sync = RFSwitchSync(
            sample_rate=sample_rate,
            dwell_time=dwell_time,
            num_antennas=num_antennas,
            threshold_percentile=threshold_percentile
        )
        
        # Buffer for continuous stream processing
        # We need to keep some history to handle frames split across chunks.
        # History length = 2 cycles is safe to ensure we never miss a connection.
        self.history_len = int(self.rf_sync.samples_per_cycle * 2.0)
        self.residue = numpy.array([], dtype=numpy.complex64)

    def general_work(self, input_items, output_items):
        in_stream = input_items[0]
        n_input = len(in_stream)
        
        # If no input, just return (unless we have enough residue? usually general_work called with data)
        if n_input == 0:
            return 0
            
        # 1. Prepend residue from previous call
        combined = numpy.concatenate((self.residue, in_stream))
        
        # 2. Adjust RFSwitchSync prediction pointer
        self.rf_sync.next_edge_predict += len(self.residue)
        
        # 3. Process
        # process_stream returns a LIST of dicts (one dict per cycle)
        payloads = self.rf_sync.process_stream(combined)
        
        # 4. Aggregate data for outputs
        ant_data = { k: [] for k in range(1, 8) }
        
        for p in payloads:
            for k in range(1, 8):
                if k in p:
                    ant_data[k].append(p[k])
        
        # Flatten and determine production count
        flattened = {}
        
        produced_len = 0
        if payloads:
            # All antennas should have the same total length
            # len(payloads) * (samples_per_slot_net)
            
            # Concatenate
            for k in range(1, 8):
                if ant_data[k]:
                    flattened[k] = numpy.concatenate(ant_data[k])
                else:
                    flattened[k] = numpy.array([], dtype=numpy.complex64)
            
            # Verify lengths (should be identical)
            produced_len = len(flattened[1])
            
            # Write to output buffers
            # Check for space
            for i in range(7):
                if len(output_items[i]) < produced_len:
                    produced_len = len(output_items[i])
            
            # Write
            for i in range(7):
                k = i + 1 # Key 1..7
                output_items[i][:produced_len] = flattened[k][:produced_len]

        # 5. Update Residue
        consumed_items = n_input # We consume everything from GR buffer
        
        # Calculate what to keep for next time
        # We want to keep everything relevant for the NEXT predicted edge.
        # Next edge is at `self.rf_sync.next_edge_predict` (index in `combined`).
        # We need history going back `samples_per_cycle` from that edge.
        
        keep_start = int(self.rf_sync.next_edge_predict - self.rf_sync.samples_per_cycle - 200) # extra safety
        if keep_start < 0:
            keep_start = 0
            
        self.residue = combined[keep_start:]
        
        # Adjust `next_edge_predict` to be relative to the START of `residue`
        # currently `next_edge_predict` is relative to start of `combined`.
        # new `next_edge_predict` = `old_next_edge_predict` - `keep_start`
        
        self.rf_sync.next_edge_predict -= keep_start
        
        self.consume(0, n_input)
        return produced_len

    def stop(self):
        return True