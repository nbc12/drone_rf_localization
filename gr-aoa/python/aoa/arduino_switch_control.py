#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 gr-aoa author.
#
# SPDX-License-Identifier: GPL-3.0-or-later

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

class arduino_switch_control(gr.sync_block):
    """
    Arduino Switch Controller Block
    
    Controls the SP8T RF Switch via Serial.
    - Sets Dwell Time on initialization.
    - Starts Cycle on Start.
    - Stops Cycle on Stop.
    """
    def __init__(self, serial_port='/dev/ttyUSB0', baud_rate=115200, dwell_time=45e-6):
        gr.sync_block.__init__(self,
            name="Arduino Switch Control",
            in_sig=None,
            out_sig=None)

        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.dwell_time = dwell_time
        self.arduino = None

    def start(self):
        if self.serial_port:
            self.arduino = ArduinoSwitcherDriver(self.serial_port, self.baud_rate)
            dwell_us = self.dwell_time * 1e6
            self.arduino.set_dwell_time(dwell_us)
            self.arduino.start_cycle()
        return True

    def stop(self):
        if self.arduino:
            self.arduino.close()
            self.arduino = None
        return True

    def work(self, input_items, output_items):
        # This block does not process data, just controls hardware state.
        return 0
