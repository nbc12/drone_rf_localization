#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 gr-aoa author.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import numpy as np
from gnuradio import gr

class sync_pll(gr.basic_block):
    """
    AOA Sync PLL Block
    
    Inputs:
        0: Float Stream (Raw Sync Detection, 1.0=Low Power/Dead Time)
        
    Outputs:
        0: Float Stream (Clean Locked Clock, 1.0=Dead Time start)
    """
    def __init__(self, sample_rate=1000000, dwell_time=0.5, num_antennas=6):
        gr.basic_block.__init__(self,
            name="AOA Sync PLL",
            in_sig=[np.float32],
            out_sig=[np.float32])

        self.samples_per_slot = int(sample_rate * dwell_time)
        self.cycle_len = int(self.samples_per_slot * (num_antennas + 1))
        
        # State
        self.locked = False
        self.sample_counter = 0
        self.next_edge_predict = 0
        self.history = np.array([], dtype=np.float32)

    def general_work(self, input_items, output_items):
        in_sig = input_items[0]
        out_sig = output_items[0]
        n_input = len(in_sig)
        
        # Concatenate history
        stream = np.concatenate((self.history, in_sig))
        
        # If not locked, simple search for a pulse
        if not self.locked:
            # Look for 1.0
            highs = np.where(stream > 0.5)[0]
            if len(highs) > 0:
                # Found a potential edge
                first_edge = highs[0]
                
                # Check if we have enough data to verify period?
                # For now, simplistic lock: assume first pulse is valid
                self.locked = True
                self.next_edge_predict = first_edge
                self.sample_counter = 0 # Phase of the cycle
                
                # Align our counter such that 'first_edge' corresponds to Dead Time Start
                # Let's say Dead Time is at end of cycle.
                # Or start? Let's say Dead Time is Counter=0
                
        # Generate Output Clock based on internal counter
        # 1.0 during Dead Time (first slot?), 0.0 otherwise?
        # Let's match previous logic: Dead Time is the LAST slot (or isolated).
        # Let's output a trigger pulse (1.0) at the start of Dead Time.
        
        generated = np.zeros(len(stream), dtype=np.float32)
        
        if self.locked:
            # Generate the clock signal for the whole buffer based on state
            # This is a "Flywheel" - it generates regardless of input quality
            # Ideally, we should correct drift here by looking at input edges.
            
            # Simple implementation: Just pass through the detected edges for now?
            # No, that defeats the purpose of PLL.
            # We want to output a CLEAN 1.0 pulse every `cycle_len`.
            
            # For every sample in buffer:
            for i in range(len(stream)):
                # If counter matches Dead Time Start
                if self.sample_counter == 0:
                    generated[i] = 1.0
                elif self.sample_counter < self.samples_per_slot:
                    # Hold high for duration of dead time?
                    # Or just a trigger? Demux needs to know duration.
                    # Let's output High for whole Dead Time slot.
                    generated[i] = 1.0
                else:
                    generated[i] = 0.0
                    
                self.sample_counter += 1
                if self.sample_counter >= self.cycle_len:
                    self.sample_counter = 0
                    
                # PLL Correction Logic (Simulated)
                # If we expect an edge (sample_counter near 0) and we see one in input,
                # we nudge the counter.
                if stream[i] > 0.5:
                    # Input is High (Dead Time)
                    # We expect to be in Dead Time (counter < samples_per_slot)
                    # If we are slightly outside, adjust.
                    pass
        
        # Write output
        # Only write what fits/matches input length
        n_out = min(len(generated), len(out_sig))
        
        # We processed 'stream' which includes history.
        # We need to map back to input timeline.
        # This is tricky with history in general_work.
        # Simpler: Don't use history for generating, only for locking.
        
        # RE-THINK:
        # Just generate N samples based on current state.
        # Input is only for correction.
        
        # 1. Generate N samples of clock
        out_clock = np.zeros(n_input, dtype=np.float32)
        if self.locked:
            for i in range(n_input):
                if self.sample_counter < self.samples_per_slot:
                    out_clock[i] = 1.0
                else:
                    out_clock[i] = 0.0
                
                self.sample_counter += 1
                if self.sample_counter >= self.cycle_len:
                    self.sample_counter = 0
        
        out_sig[:n_input] = out_clock
        self.consume(0, n_input)
        return n_input
