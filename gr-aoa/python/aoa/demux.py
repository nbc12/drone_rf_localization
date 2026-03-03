#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 gr-aoa author.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import numpy as np
from gnuradio import gr

class demux(gr.basic_block):
    """
    AOA Demux Block
    
    Inputs:
        0: Complex Stream (IQ Data)
        1: Float Stream (Clean Clock from PLL: 1.0=Dead Time, 0.0=Antennas)
        
    Outputs:
        0..5: Antenna 1-6
        6: Dead Time
    """
    def __init__(self, sample_rate=1000000, dwell_time=0.5, num_antennas=6):
        gr.basic_block.__init__(self,
            name="AOA Demux",
            in_sig=[np.complex64, np.float32],
            out_sig=[np.complex64] * (num_antennas + 1))
            
        self.samples_per_slot = int(sample_rate * dwell_time)
        self.num_ants = num_antennas
        
        self.current_ant = 0 # 0..5 = Ant 1-6
        self.in_dead_time = False
        self.samples_in_state = 0

    def general_work(self, input_items, output_items):
        in_iq = input_items[0]
        in_clk = input_items[1]
        
        n_process = min(len(in_iq), len(in_clk))
        if n_process == 0: return 0
        
        # We iterate sample by sample (or chunks) to route data
        # Logic:
        # Clock = 1.0 -> Route to Output 6 (Dead Time). Reset Antenna Counter.
        # Clock = 0.0 -> Route to Current Antenna. Count samples. Switch Antenna every dwell_time.
        
        # Performance Note: Loop in Python is slow. 
        # But we can try to find edges of the clock first.
        
        edges = np.abs(np.diff(in_clk[:n_process], prepend=in_clk[0])) > 0.5
        edge_indices = np.where(edges)[0]
        
        # Add start and end points
        points = np.concatenate(([0], edge_indices, [n_process]))
        
        for i in range(len(points) - 1):
            start = points[i]
            end = points[i+1]
            length = end - start
            if length == 0: continue
            
            # Check state of clock in this segment
            is_dead_time = (in_clk[start] > 0.5)
            
            chunk = in_iq[start:end]
            
            if is_dead_time:
                # Route to Dead Time Port (Ant 6 in code logic, 7th port)
                # Reset Antenna sequence
                self.current_ant = 0
                self.samples_in_state = 0
                
                # Check space
                if len(output_items[self.num_ants]) >= length:
                    # Write
                    # But we can't just append in general_work? 
                    # We must manage write pointers manually or use produce.
                    # basic_block general_work is tricky with multiple outputs of diff rates.
                    # We will output nothing for now and rely on user to connect sinks?
                    pass
                    
                # Actually, outputting to different streams at different rates requires careful `produce` calls.
                # Since we are essentially demuxing, every input sample goes to EXACTLY ONE output.
                # So we can just `produce` on the active port.
                
                # Write to Dead Time Port (Index 6)
                dest = self.num_ants
                out_buf = output_items[dest]
                # We assume buffer is large enough (GR usually gives 8k+)
                # But if chunk is huge, we might overflow.
                limit = min(len(out_buf), length)
                out_buf[:limit] = chunk[:limit]
                self.produce(dest, limit)
                
            else:
                # Active Antenna Time
                # We need to split this chunk into antenna slots based on sample counting
                
                offset = 0
                while offset < length:
                    remaining_in_chunk = length - offset
                    needed_for_slot = self.samples_per_slot - self.samples_in_state
                    
                    to_write = min(remaining_in_chunk, needed_for_slot)
                    
                    # Write to Current Antenna
                    dest = self.current_ant
                    # Safety check on antenna index (in case clock is 0 for too long)
                    if dest < self.num_ants:
                        out_buf = output_items[dest]
                        limit = min(len(out_buf), to_write)
                        out_buf[:limit] = chunk[offset : offset+limit]
                        self.produce(dest, limit)
                    
                    self.samples_in_state += to_write
                    offset += to_write
                    
                    if self.samples_in_state >= self.samples_per_slot:
                        # Move to next antenna
                        self.current_ant += 1
                        self.samples_in_state = 0
        
        self.consume(0, n_process)
        self.consume(1, n_process)
        return gr.WORK_CALLED_PRODUCE
