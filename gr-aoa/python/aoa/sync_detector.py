#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 gr-aoa author.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import numpy as np
from gnuradio import gr

class sync_detector(gr.sync_block):
    """
    AOA Sync Detector Block

    Analyzes a smoothed power stream (Float) for the characteristic "Dead Time"
    switching pattern using a dynamic percentile threshold.

    Output:
        Float stream where:
        1.0 = Dead Time (Sync detected)
        0.0 = Antenna Data (Active)
    """
    def __init__(self,
                 sample_rate=1000000,
                 dwell_time=0.5,
                 window_size=1024,
                 threshold_percentile=0.20):

        gr.sync_block.__init__(self,
            name="AOA Sync Detector",
            in_sig=[np.float32], # Assumes smoothed power input
            out_sig=[np.float32]) # Control signal output

        self.fs = sample_rate
        self.dwell = dwell_time
        self.window_size = window_size
        self.pct = threshold_percentile
        
        # State
        self.history = np.zeros(0, dtype=np.float32)

    def work(self, input_items, output_items):
        power = input_items[0]
        out = output_items[0]

        n = len(power)
        if n == 0: return 0

        # 1. Update History Window
        self.history = np.concatenate((self.history, power))
        if len(self.history) > self.window_size:
            self.history = self.history[-self.window_size:]
            
        # 2. Determine Threshold (Dynamic)
        if len(self.history) > 0:
            # np.percentile expects 0-100, we use 0.0-1.0 input
            # Strategy: For a 1/7th (~14%) Dead Time, we pick a percentile
            # slightly HIGHER (e.g. 20%). This places the threshold at the
            # bottom of the "Active Signal" distribution.
            # Since Noise << Active Signal, all Noise samples will be
            # consistently BELOW this threshold, yielding a clean, solid pulse.
            thresh = np.percentile(self.history, self.pct * 100)
        else:
            thresh = 0.0

        # 3. Generate Control Signal
        # If Power < Threshold -> Output 1.0 (Dead Time)
        # Else -> Output 0.0
        out[:] = (power < thresh).astype(np.float32)

        return n
