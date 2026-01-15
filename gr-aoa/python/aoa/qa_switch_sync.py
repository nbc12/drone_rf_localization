#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 gr-aoa author.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#

from gnuradio import gr, gr_unittest, blocks
from gnuradio.aoa import switch_sync
import numpy as np
import time

class qa_switch_sync(gr_unittest.TestCase):

    def setUp(self):
        self.tb = gr.top_block()

    def tearDown(self):
        self.tb = None

    def generate_test_signal(self, sample_rate, dwell_time, num_antennas, cycles=5, noise_level=0.01, mode='constant'):
        """Generates a synthetic signal mimicking the switching behavior.
           mode: 'constant' (clean 1.0 vs 0.001) or 'noise' (random gaussian).
        """
        samps_per_slot = int(sample_rate * dwell_time)
        cycle_len = samps_per_slot * (num_antennas + 1)
        total_samps = cycle_len * cycles
        
        signal = np.zeros(total_samps, dtype=np.complex64)
        
        # Varying gains for noisy mode to test dynamic range
        # Base signal is randn*0.5 (mean magnitude ~0.44)
        # Gains: 0.8 to 1.5. Resulting magnitudes: 0.35 to 0.66.
        # All well above noise (0.01).
        antenna_gains = [0.8, 1.2, 0.9, 1.5, 0.7, 1.1]
        
        for i in range(cycles):
            base_idx = i * cycle_len
            
            # Antennas 1 to N (High Power)
            for ant in range(num_antennas):
                start = base_idx + ant * samps_per_slot
                end = start + samps_per_slot
                
                if mode == 'constant':
                    sig = 1.0 + 0j
                else:
                    # Random signal (High Amplitude) with varying gain
                    gain = antenna_gains[ant % len(antenna_gains)]
                    sig = (np.random.randn(samps_per_slot) + 1j * np.random.randn(samps_per_slot)) * 0.5 * gain
                
                signal[start:end] = sig
                
            # Dead Time (Antenna N+1) (Low Power / Noise)
            dt_start = base_idx + num_antennas * samps_per_slot
            dt_end = dt_start + samps_per_slot
            
            if mode == 'constant':
                noise = 0.001 + 0j
            else:
                noise = (np.random.randn(samps_per_slot) + 1j * np.random.randn(samps_per_slot)) * noise_level
                
            signal[dt_start:dt_end] = noise
            
        return signal

    def test_001_sync_acquisition(self):
        """Tests if the block can lock onto the signal and separate streams correctly."""
        
        # Params
        sr = 1000000
        dwell = 40e-6
        ants = 6
        cycles = 50
        
        # Generate Signal
        src_data = self.generate_test_signal(sr, dwell, ants, cycles=cycles, mode='constant')
        
        # Prepend high power "garbage" to simulate lock-in
        offset_len = 200 
        garbage = np.ones(offset_len, dtype=np.complex64) # Constant High
        full_input = np.concatenate((garbage, src_data))
        
        # Source Block
        src = blocks.vector_source_c(full_input.tolist(), False)
        
        # DUT (Device Under Test)
        dut = switch_sync(
            sample_rate=sr,
            dwell_time=dwell,
            num_antennas=ants,
            threshold_percentile=30.0
        )
        
        # Sinks (One for each output)
        sinks = [blocks.vector_sink_c() for _ in range(ants + 1)]
        
        # Connect
        self.tb.connect(src, dut)
        for i in range(ants + 1):
            self.tb.connect((dut, i), sinks[i])
            
        # Run
        self.tb.run()
        
        # Validation
        print("\n--- Test Results (Clean) ---")
        # Check Dead Time Port (Index 6)
        dead_data = np.array(sinks[6].data())
        dead_power = np.mean(np.abs(dead_data)**2)
        print(f"Avg Dead Time Power: {dead_power:.6f}")
        
        # Check Antenna Ports (0-5)
        powers = []
        for i in range(ants):
            ant_data = np.array(sinks[i].data())
            ant_power = np.mean(np.abs(ant_data)**2) if len(ant_data) > 0 else 0.0
            powers.append(float(f"{ant_power:.6f}"))
        
        print(f"Antenna Powers: {powers}")
        
        for p in powers:
            self.assertTrue(p > 0.9, f"Antenna power {p} should be ~1.0")
        self.assertTrue(dead_power < 0.1, "Dead Time should be ~0.0")
        
        # Assert Synchronization Count
        ant1_data = np.array(sinks[0].data())
        slot_len = int(sr*dwell)
        guard = int(sr*2e-6)
        payload_len = slot_len - 2*guard
        
        recovered_cycles = len(ant1_data) / payload_len
        print(f"Recovered Cycles: {recovered_cycles:.2f} / {cycles}")
        self.assertGreater(recovered_cycles, cycles * 0.8, "Should recover >80% of cycles with clean signal")

    def test_002_sync_acquisition_noisy(self):
        """Tests lock on a noisy Rayleigh signal."""
        print("\n--- Test 002: Noisy Signal ---")
        
        # Params
        sr = 1000000
        dwell = 40e-6
        ants = 6
        cycles = 50
        
        # Generate Signal (Noisy)
        src_data = self.generate_test_signal(sr, dwell, ants, cycles=cycles, mode='noise')
        
        # Prepend high power noisy garbage
        offset_len = 200 
        garbage = (np.random.randn(offset_len) + 1j * np.random.randn(offset_len)) * 0.5
        full_input = np.concatenate((garbage, src_data))
        
        # Source
        src = blocks.vector_source_c(full_input.tolist(), False)
        
        # DUT
        dut = switch_sync(
            sample_rate=sr,
            dwell_time=dwell,
            num_antennas=ants,
            threshold_percentile=20.0
        )
        
        # Sinks
        sinks = [blocks.vector_sink_c() for _ in range(ants + 1)]
        
        # Connect
        self.tb.connect(src, dut)
        for i in range(ants + 1):
            self.tb.connect((dut, i), sinks[i])
            
        # Run
        self.tb.run()
        
        # Validation
        # Check Dead Time
        dead_data = np.array(sinks[6].data())
        dead_power = np.mean(np.abs(dead_data)**2)
        print(f"Avg Dead Time Power: {dead_power:.6f}")
        
        # Check Antennas
        powers = []
        for i in range(ants):
            ant_data = np.array(sinks[i].data())
            ant_power = np.mean(np.abs(ant_data)**2) if len(ant_data) > 0 else 0.0
            powers.append(float(f"{ant_power:.6f}"))
            
        print(f"Antenna Powers: {powers}")
        
        for p in powers:
            self.assertTrue(p > dead_power * 100, f"Antenna power {p} separation failed")
        
        # Recovery Check
        ant1_data = np.array(sinks[0].data())
        slot_len = int(sr*dwell)
        guard = int(sr*2e-6)
        payload_len = slot_len - 2*guard
        recovered_cycles = len(ant1_data) / payload_len
        print(f"Recovered Cycles: {recovered_cycles:.2f} / {cycles}")
        
        self.assertGreater(recovered_cycles, cycles * 0.7, "Should recover >70% of cycles with noisy signal")

    def test_003_clock_drift(self):
        """Tests if the PLL can track clock drift (sample rate mismatch)."""
        print("\n--- Test 003: Clock Drift ---")
        
        sr_nominal = 1000000
        dwell = 40e-6
        ants = 6
        cycles = 100
        
        # Test range of drift factors: Small (0.01%), Medium (0.2%), Large (1.0%)
        drift_factors = [1.0001, 0.9999, 1.002, 0.998, 1.01, 0.99]
        
        for drift in drift_factors:
            
            src_data_nominal = self.generate_test_signal(sr_nominal, dwell, ants, cycles=cycles, mode='constant')
            
            # Resample to simulate clock drift
            from scipy import signal as scipy_signal
            new_len = int(len(src_data_nominal) * drift)
            src_data_drifted = scipy_signal.resample(src_data_nominal, new_len).astype(np.complex64)
            
            # Source
            src = blocks.vector_source_c(src_data_drifted.tolist(), False)
            
            # DUT (Nominal settings)
            dut = switch_sync(
                sample_rate=sr_nominal,
                dwell_time=dwell,
                num_antennas=ants,
                threshold_percentile=30.0 # Clean signal
            )
            
            sinks = [blocks.vector_sink_c() for _ in range(ants + 1)]
            
            self.tb.connect(src, dut)
            for i in range(ants + 1):
                self.tb.connect((dut, i), sinks[i])
                
            self.tb.run()
            
            # Validation
            ant1_data = np.array(sinks[0].data())
            recovered = len(ant1_data) / (int(sr_nominal*dwell) - dut.rf_sync.guard_samples*2)
            print(f"Drift {drift:.4f}: Recovered {recovered:.2f} / {cycles}")
            
            self.assertGreater(recovered, cycles * 0.7, f"Failed to track drift {drift}")
            
            # Reset TB
            self.tb = gr.top_block()

    def test_004_sample_integrity(self):
        """Verifies bit-exact sample passing from input to output for ALL antennas."""
        print("\n--- Test 004: Sample Integrity (All Antennas) ---")
        
        sr = 1000000
        dwell = 40e-6
        ants = 6
        cycles = 20
        
        # 1. Generate Indexed Signal
        samps_per_slot = int(sr * dwell)
        cycle_len = samps_per_slot * (ants + 1)
        total_samps = cycle_len * cycles
        
        # Start with Garbage
        offset_len = 200
        garbage = np.ones(offset_len, dtype=np.complex64)
        
        # Create Signal with Index embedded
        signal = np.zeros(total_samps, dtype=np.complex64)
        for i in range(total_samps):
            slot_idx = (i % cycle_len) // samps_per_slot
            # Antennas 0-5 are Signal. Slot 6 is Dead.
            if slot_idx < 6:
                val = 100.0 + (i * 0.0001)
                signal[i] = val + 0j
            else:
                signal[i] = 0.001 + 0j
                
        full_input = np.concatenate((garbage, signal))
        
        # Source & DUT
        src = blocks.vector_source_c(full_input.tolist(), False)
        dut = switch_sync(sample_rate=sr, dwell_time=dwell, num_antennas=ants, threshold_percentile=30.0)
        sinks = [blocks.vector_sink_c() for _ in range(ants + 1)]
        
        self.tb.connect(src, dut)
        for i in range(ants + 1):
            self.tb.connect((dut, i), sinks[i])
        self.tb.run()
        
        # Validation
        # Find start reference from Ant1
        ant1_data = np.array(sinks[0].data())
        if len(ant1_data) == 0:
            self.fail("No data produced")
            
        first_val = ant1_data[0].real
        first_k = int(round((first_val - 100.0) / 0.0001))
        print(f"Locked onto base sample index: {first_k}")
        
        guard = dut.rf_sync.guard_samples
        payload_len = samps_per_slot - 2*guard
        
        # Verify ALL 6 Antennas
        for a in range(ants):
            ant_data = np.array(sinks[a].data())
            num_samples = len(ant_data)
            
            for i in range(num_samples):
                frame_idx = i // payload_len
                offset_in_frame = i % payload_len
                
                # Calculate expected index k for THIS antenna in THIS frame
                # k = base_lock_index + frame_offset + antenna_offset + intra_slot_offset
                expected_k = first_k + (frame_idx * cycle_len) + (a * samps_per_slot) + offset_in_frame
                expected_val = 100.0 + (expected_k * 0.0001)
                
                if abs(ant_data[i].real - expected_val) > 2e-5:
                    self.fail(f"Integrity Mismatch! Ant {a+1}, frame {frame_idx}, index {offset_in_frame}: "
                              f"Got {ant_data[i].real:.5f}, Expected {expected_val:.5f} (k={expected_k})")
                              
        print(f"Sample Integrity Verified: All {ants} antenna streams perfectly match input sequence.")

if __name__ == '__main__':
    gr_unittest.run(qa_switch_sync)
