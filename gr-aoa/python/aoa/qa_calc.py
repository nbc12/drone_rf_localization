#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 gr-aoa author.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#

from gnuradio import gr, gr_unittest, blocks
from gnuradio.aoa.calc import calc
import numpy as np

class qa_calc(gr_unittest.TestCase):

    def setUp(self):
        self.tb = gr.top_block()

    def tearDown(self):
        self.tb = None

    def test_001_single_antenna_direction(self):
        """Verify that high power on a single antenna produces the correct angle."""
        sr = 1000000
        dwell = 40e-6
        ants = 6
        
        # Calculate samples per slot
        # Matches logic in block: int(sr*dwell) - 2*int(sr*2e-6)
        slot_len = int(sr * dwell) - 2 * int(sr * 2.0e-6)
        
        # Generate 10 frames of data
        frames = 10
        total_len = frames * slot_len
        
        # Case A: Antenna 1 (0 degrees)
        # Input 0 is 1.0, others 0.0
        in0 = [1.0+0j] * total_len
        others = [0.0+0j] * total_len
        
        srcs = [blocks.vector_source_c(in0, False)]
        for _ in range(5):
            srcs.append(blocks.vector_source_c(others, False))
            
        dut = calc(sample_rate=sr, dwell_time=dwell, num_antennas=ants)
        snk = blocks.vector_sink_c()
        
        for i in range(6):
            self.tb.connect(srcs[i], (dut, i))
        self.tb.connect(dut, snk)
        
        self.tb.run()
        
        result = np.array(snk.data())
        self.assertEqual(len(result), frames, "Output length mismatch")
        
        # Check Angle (Ant 1 is at 0)
        avg_angle = np.mean(np.angle(result))
        avg_mag = np.mean(np.abs(result))
        
        print("\n--- Test 001: Single Antenna (Ant 1 @ 0 deg) ---")
        print(f"Calculated Angle: {avg_angle:.4f} rad ({np.degrees(avg_angle):.2f} deg)")
        print(f"Calculated Magnitude: {avg_mag:.4f}")
        
        self.assertAlmostEqual(avg_angle, 0.0, delta=0.01)
        self.assertAlmostEqual(avg_mag, 1.0, delta=0.01)

    def test_002_mixed_direction(self):
        """Verify vector addition (signal between Ant 1 and Ant 2)."""
        sr = 1000000
        dwell = 40e-6
        ants = 6
        slot_len = int(sr * dwell) - 2 * int(sr * 2.0e-6)
        total_len = 10 * slot_len
        
        # Ant 1 (0 deg) and Ant 2 (60 deg) have equal power
        sig = [1.0+0j] * total_len
        silence = [0.0+0j] * total_len
        
        srcs = []
        srcs.append(blocks.vector_source_c(sig, False)) # Ant 1
        srcs.append(blocks.vector_source_c(sig, False)) # Ant 2
        for _ in range(4):
            srcs.append(blocks.vector_source_c(silence, False))
            
        dut = calc(sample_rate=sr, dwell_time=dwell, num_antennas=ants)
        snk = blocks.vector_sink_c()
        
        for i in range(6):
            self.tb.connect(srcs[i], (dut, i))
        self.tb.connect(dut, snk)
        
        self.tb.run()
        
        result = np.array(snk.data())
        
        # Expected Angle: Average of 0 and 60 deg = 30 deg
        expected_angle = np.radians(30.0)
        avg_angle = np.mean(np.angle(result))
        avg_mag = np.mean(np.abs(result))
        
        print("\n--- Test 002: Mixed Direction (Ant 1 & 2 @ 30 deg) ---")
        print(f"Calculated Angle: {avg_angle:.4f} rad ({np.degrees(avg_angle):.2f} deg)")
        print(f"Calculated Magnitude: {avg_mag:.4f}")
        
        self.assertAlmostEqual(avg_angle, expected_angle, delta=0.01)
        
        # Expected Magnitude: sqrt(3) ~ 1.732
        expected_mag = np.sqrt(3.0)
        self.assertAlmostEqual(avg_mag, expected_mag, delta=0.01)

    def test_003_noisy_direction(self):
        """Verify angle calculation with noisy inputs using a directional pattern."""
        sr = 1000000
        dwell = 40e-6
        ants = 6
        slot_len = int(sr * dwell) - 2 * int(sr * 2.0e-6)
        total_len = 50 * slot_len # 50 frames
        
        # Target Source at 30 degrees (0.523 rad)
        target_deg = 30.0
        target_rad = np.radians(target_deg)
        
        srcs = []
        
        # Antenna Pattern: Cardioid M = 0.5 * (1 + cos(theta - ant_angle))
        # This simulates directional antennas (like DF loop)
        for i in range(ants):
            ant_angle = i * (2 * np.pi / ants)
            # Pattern magnitude (0.0 to 1.0)
            pattern_mag = 0.5 * (1.0 + np.cos(target_rad - ant_angle))
            # Increase base power for visibility
            pattern_mag *= 2.0 
            
            # Generate Noisy Signal (Rayleigh)
            # Amplitude ~ pattern_mag
            # Noise Floor ~ 0.1
            noise = (np.random.randn(total_len) + 1j * np.random.randn(total_len)) * 0.1
            signal = (np.random.randn(total_len) + 1j * np.random.randn(total_len)) * 0.5 * pattern_mag
            
            stream_data = signal + noise
            srcs.append(blocks.vector_source_c(stream_data.tolist(), False))
            
        dut = calc(sample_rate=sr, dwell_time=dwell, num_antennas=ants)
        snk = blocks.vector_sink_c()
        
        for i in range(ants):
            self.tb.connect(srcs[i], (dut, i))
        self.tb.connect(dut, snk)
        
        self.tb.run()
        
        result = np.array(snk.data())
        avg_angle = np.angle(np.mean(result)) # Vector average then angle
        
        avg_deg = np.degrees(avg_angle)
        
        print("\n--- Test 003: Noisy Direction (Target 30 deg) ---")
        print(f"Calculated Angle: {avg_deg:.2f} deg")
        print(f"Vector Magnitude: {np.abs(np.mean(result)):.4f}")
        
        # Tolerance: +/- 5 degrees for noisy signal
        diff = abs(avg_deg - target_deg)
        self.assertTrue(diff < 5.0, f"Angle {avg_deg} too far from {target_deg}")

    def test_004_complex_pattern(self):
        """Verify angle calculation with ideal Cosine projection on multiple antennas."""
        sr = 1000000
        dwell = 40e-6
        ants = 6
        slot_len = int(sr * dwell) - 2 * int(sr * 2.0e-6)
        total_len = 10 * slot_len
        
        # Target Source at 45 degrees
        target_deg = 45.0
        target_rad = np.radians(target_deg)
        
        srcs = []
        
        print("\n--- Test 004: Complex Pattern (Target 45 deg) ---")
        print("Inputs:")
        
        # Generate magnitudes based on Cosine projection (Ideal beamforming)
        # Mag_i = max(0, cos(target - ant_angle))
        for i in range(ants):
            ant_angle = i * (2 * np.pi / ants)
            
            # Use cosine distance for magnitude
            cos_dist = np.cos(target_rad - ant_angle)
            mag = max(0.0, cos_dist)
            
            print(f"  Ant {i+1} ({np.degrees(ant_angle):.0f} deg): {mag:.4f}")
            
            data = [mag + 0j] * total_len
            srcs.append(blocks.vector_source_c(data, False))
            
        dut = calc(sample_rate=sr, dwell_time=dwell, num_antennas=ants)
        snk = blocks.vector_sink_c()
        
        for i in range(ants):
            self.tb.connect(srcs[i], (dut, i))
        self.tb.connect(dut, snk)
        
        self.tb.run()
        
        result = np.array(snk.data())
        avg_angle = np.mean(np.angle(result))
        avg_deg = np.degrees(avg_angle)
        
        print(f"Calculated Angle: {avg_deg:.2f} deg")
        
        # Verify
        self.assertAlmostEqual(avg_deg, target_deg, delta=0.1)

if __name__ == '__main__':
    gr_unittest.run(qa_calc)
