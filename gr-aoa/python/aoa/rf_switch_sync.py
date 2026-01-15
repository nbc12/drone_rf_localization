# -*- coding: utf-8 -*-
#
# Copyright 2026 gr-aoa author.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import numpy as np

class RFSwitchSync:
    def __init__(self, sample_rate, dwell_time=40e-6, num_antennas=6, 
                 threshold_percentile=10.0):
        """
        :param threshold_percentile: The percentile of power (0-100) considered as 'Low' (Dead Time).
                                     Since Dead Time is ~14% of cycle, a value like 10.0 works well.
        """
        self.fs = sample_rate
        self.dwell_time = dwell_time
        self.num_ants = num_antennas
        
        # TIMING CONSTANTS (Initial Estimates)
        self.samples_per_slot = int(sample_rate * dwell_time)
        self.cycle_slots = num_antennas + 1 # 7 slots total
        self.samples_per_cycle = float(self.samples_per_slot * self.cycle_slots) # Float for precision
        
        # CONFIG
        self.guard_samples = int(sample_rate * 2.0e-6)
        self.threshold_percentile = threshold_percentile
        self.search_window = 20 # +/- samples for fine tuning
        
        # STATE
        self.locked = False
        self.next_edge_predict = 0.0 # Float for sub-sample precision
        self.clock_history = [] 
        
    def process_stream(self, samples_chunk):
        """
        Main entry point. Pass in a continuous stream of IQ samples.
        Returns: LIST of Dicts. Each Dict contains separated antenna data for one cycle.
                 Keys: 1..6 (Antennas), 7 (Dead Time/Noise)
        """
        power = np.abs(samples_chunk)**2
        results = []
        
        # Calculate Threshold for this chunk
        current_threshold = np.percentile(power, self.threshold_percentile)
        
        # Determine strict bounds for a complete frame
        safety_margin = self.search_window + 10
        req_before = int(self.samples_per_slot * 6) + safety_margin
        req_after = int(self.samples_per_slot) + safety_margin
        
        # Re-acquisition cursor
        # If we lose lock, we start searching from where we left off (approximately)
        # But _acquire_lock_robust scans the passed buffer.
        # So we need to slice the buffer.
        
        # We process until we can't anymore
        processing = True
        
        while processing:
            if not self.locked:
                # ACQUISITION PHASE
                # We need to decide where to search. 
                # Ideally, we search from the current 'next_edge_predict' if valid, 
                # or from 0 if completely reset. 
                # Simpler: Search from 0 of the *current view*.
                # But we don't track a 'cursor' easily because tracking moves freely.
                # However, if we slipped, we want to re-acquire AFTER the slip.
                
                # Let's assume we search the whole remaining relevant buffer.
                # Since 'next_edge_predict' might be anywhere, let's use it as a hint 
                # if it is within bounds, otherwise 0.
                
                start_search_idx = int(self.next_edge_predict)
                if start_search_idx < 0: start_search_idx = 0
                if start_search_idx >= len(power): 
                    # End of buffer, can't acquire
                    break
                    
                power_view = power[start_search_idx:]
                
                try:
                    rel_edge, avg_period = self._acquire_lock_robust(power_view, current_threshold)
                    
                    if avg_period > 0:
                        self.samples_per_cycle = avg_period
                    
                    # Found edge relative to start_search_idx
                    self.next_edge_predict = float(start_search_idx + rel_edge)
                    self.locked = True
                    
                except RuntimeError:
                    # Failed to find lock in remaining data
                    break

            if self.locked:
                # TRACKING PHASE
                predicted_idx = int(round(self.next_edge_predict))
                
                # Boundary Checks
                if (predicted_idx + req_after > len(power)):
                    # Frame doesn't fit at end
                    break
                
                if (predicted_idx - req_before < 0):
                    # Partial frame at start
                    self.next_edge_predict += self.samples_per_cycle
                    continue

                # Fine Tune
                try:
                    actual_idx = self._fine_tune_edge(power, predicted_idx, current_threshold)
                    
                    # PLL Update
                    error = actual_idx - predicted_idx
                    beta = 0.01 
                    self.samples_per_cycle += (error * beta)
                    
                    # Extract
                    payload = self._extract_payload(samples_chunk, actual_idx)
                    if payload:
                        results.append(payload)
                        
                    # Advance
                    self.next_edge_predict = actual_idx + self.samples_per_cycle
                    
                except RuntimeError:
                    # Slip detected
                    self.locked = False
                    # Advance cursor slightly so we don't re-find the same bad edge?
                    # Or just let acquire handle it. 
                    # Set next search to be slightly after where we failed
                    self.next_edge_predict += (self.samples_per_slot * 2) 
                    continue
            
        return results

    def _acquire_lock_robust(self, power, threshold_value):
        """
        Scans buffer. Returns: (first_edge_index, measured_avg_period)
        """
        # print(f"DEBUG: Acquiring lock on len={len(power)}...")

        # --- NEW: Buffer Length Safety Check ---
        min_required = int(self.samples_per_cycle * 2.5)
        if len(power) < min_required:
            raise RuntimeError(
                f"SYNC ERROR: Buffer too short. Need >{min_required} samples, "
                f"got {len(power)}. (Try increasing SDR read buffer size)"
            )

        # 1. Thresholding
        is_low = power < threshold_value
        
        # 2. Pulse Width Filtering (Reject short noise spikes)
        is_low_int = is_low.astype(int)
        diffs = np.diff(is_low_int)
        starts = np.where(diffs == 1)[0]
        ends = np.where(diffs == -1)[0]
        
        # Handle empty cases
        if len(starts) == 0:
            raise RuntimeError("SYNC ERROR: No falling edges found (Signal too high?)")
        if len(ends) == 0:
             # Could be one long low pulse?
             pass

        # Clean up boundaries to ensure pairs
        # If the first 'end' comes before the first 'start', it means we started in a Low state.
        # We can't know the width, so discard that partial pulse.
        if len(ends) > 0 and ends[0] < starts[0]:
            ends = ends[1:]
            
        # If we have a 'start' without an 'end' (buffer ends in Low), discard it.
        if len(starts) > len(ends):
            starts = starts[:len(ends)]
            
        # Calculate widths and filter
        # Widths are distance between falling edge (start of dead time) and rising edge (end of dead time).
        widths = ends - starts
        min_width = self.samples_per_slot * 0.5
        
        valid_indices = np.where(widths > min_width)[0]
        falling_edges = starts[valid_indices]
        
        # 3. Candidate Filtering
        if len(falling_edges) < 2:
             # Just one edge found? We can't verify period. 
             pass 
        
        # Calculate distances between edges
        edge_diffs = np.diff(falling_edges)
        expected = self.samples_per_slot * self.cycle_slots
        tolerance = expected * 0.05
        
        # Find the sequence of edges that matches our cycle period
        consecutive_matches = []
        current_seq = [falling_edges[0]] if len(falling_edges) > 0 else []
        
        for i in range(len(edge_diffs)):
            dist = edge_diffs[i]
            if abs(dist - expected) < tolerance:
                current_seq.append(falling_edges[i+1])
            else:
                if len(current_seq) > 1:
                    consecutive_matches.append(current_seq)
                current_seq = [falling_edges[i+1]]
        if len(current_seq) > 1:
            consecutive_matches.append(current_seq)
            
        # Select best sequence (longest one)
        if not consecutive_matches:
            # --- UPDATED: Detailed Error Message ---
            raise RuntimeError(
                "SYNC ERROR: No periodic dead zones found. "
                "Causes: Signal blocked, Threshold too high, or Buffer too short."
            )
            
        best_seq = max(consecutive_matches, key=len)
        # print(f"DEBUG: Found seq len={len(best_seq)}")
        
        # Calculate Average Period from this chunk
        total_span = best_seq[-1] - best_seq[0]
        num_gaps = len(best_seq) - 1
        avg_period = total_span / num_gaps if num_gaps > 0 else 0
        
        return best_seq[0], avg_period

    def _fine_tune_edge(self, power, predicted_idx, threshold_value):
        start = max(0, predicted_idx - self.search_window)
        end = min(len(power), predicted_idx + self.search_window)
        segment = power[start:end]
        
        lows = np.where(segment < threshold_value)[0]
        if len(lows) == 0:
            raise RuntimeError("Edge lost")
            
        # Robust check: Find the first low that starts a run of lows
        # We expect the dead time to be ~40 samples.
        # We should see at least 5-10 consecutive lows to call it an edge.
        min_run = 10
        
        for idx in lows:
            # Check if this index starts a run
            # Boundary check within segment
            if idx + min_run <= len(segment):
                run = segment[idx : idx + min_run]
                if np.all(run < threshold_value):
                    return start + idx
            else:
                # If run extends beyond segment, check as much as we have?
                # Or just assume if we are near end of segment and it's all low, it's valid.
                # Let's be strict: if we can't verify min_run, ignore (unless segment was cut short?).
                # Actually, 'end' is usually len(power) if at end of buffer.
                # If we are at end of buffer, we might not have 10 samples.
                # But 'boundary check' in process_stream ensures we have 'req_after' (40+ samples).
                # So segment *should* have enough data if predicted_idx is correct.
                # But 'segment' is sliced by search_window.
                # If the edge is at the very end of the search window, we might not see the full run.
                # We should probably extend the segment reading for verification?
                pass

        # Fallback: If strict check fails, maybe return the first one?
        # No, that causes the bug.
        # If we didn't find a sustained run in the *window*, maybe the edge isn't here.
        # But we must return something or fail.
        
        raise RuntimeError("Edge lost (noise)")

    def _extract_payload(self, samples, sync_idx):
        payload = {}
        # Working backwards from Dead Zone Start (which is end of Ant 6)
        # Antennas 1-6
        for ant in range(1, 7):
            end_offset = (6 - ant) * self.samples_per_slot
            start_offset = end_offset + self.samples_per_slot
            
            idx_end = sync_idx - end_offset
            idx_start = sync_idx - start_offset
            
            # Apply Guard
            idx_start += self.guard_samples
            idx_end -= self.guard_samples
            
            if idx_start >= 0 and idx_end <= len(samples):
                payload[ant] = samples[idx_start:idx_end]

        # Dead Time (Antenna 7) - Located AFTER sync_idx
        # sync_idx is the falling edge (start of dead time)
        dt_start = sync_idx
        dt_end = sync_idx + self.samples_per_slot
        
        # Apply Guard to Dead Time as well
        dt_start += self.guard_samples
        dt_end -= self.guard_samples
        
        if dt_start >= 0 and dt_end <= len(samples):
            payload[7] = samples[dt_start:dt_end]
                
        return payload