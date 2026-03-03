/*
 * High Performance SP8T RF Switch Controller (Standalone Mode)
 * Target: Arduino Nano (ATmega328P)
 * IC: PE42582
 *
 * BEHAVIOR: 
 * - Cycles RF1 -> RF2 -> RF3 -> RF4 -> RF5 -> RF6 -> ALL OFF -> Repeat
 * - No Serial Control (Fixed Speed)
 * - Jitter-Free (Interrupts Disabled)
 *
 * Pin Connections:
 * D8  (PB0) -> V1
 * D9  (PB1) -> V2
 * D10 (PB2) -> V3
 * D11 (PB3) -> V4 (All-Off State)
 * D12 (PB4) -> SYNC (Trigger for Scope)
 * D13 (PB5) -> DEBUG / LED
 */

#include <avr/io.h>
#include <Arduino.h>

// ==========================================
// CONFIGURATION
// ==========================================
const unsigned long dwellTime = 50; // Time in microseconds per switch
// ==========================================

// Port Masks
const uint8_t PATTERN_RF1 = 0x00; 
const uint8_t PATTERN_RF2 = 0x04; 
const uint8_t PATTERN_RF3 = 0x02; 
const uint8_t PATTERN_RF4 = 0x06; 
const uint8_t PATTERN_RF5 = 0x01; 
const uint8_t PATTERN_RF6 = 0x05; 
const uint8_t PATTERN_ALL_OFF = 0x08; 

void setup() {
  // 1. Configure Ports
  // Set D8-D13 as OUTPUT (PB0-PB5)
  DDRB |= 0x3F; 
  PORTB &= ~0x3F; // Start Low

  // 2. Disable Interrupts for maximum stability
  // This kills Serial, millis(), and micros(), but ensures 
  // the delayMicroseconds() function is perfectly consistent.
  noInterrupts();
}

void loop() {
  // We use a while(1) here to avoid the tiny overhead of the 
  // main loop() function restarting.
  
  uint8_t mask = 0xC0; // Preserve top 2 bits of Port B
  uint8_t basePort = PORTB & mask;
  
  // Pre-calculate delay to account for loop instruction overhead
  // (Tuning: usually -1us is close enough for Arduino 16MHz)
  unsigned long runDelay = (dwellTime > 1) ? dwellTime - 1 : 1;

  while (true) {
    // --- RF1 (Sync HIGH, Debug HIGH) ---
    // 0x10 = Pin D12 (Sync)
    // 0x20 = Pin D13 (LED/Debug)
    PORTB = basePort | PATTERN_RF1 | 0x10 | 0x20;
    delayMicroseconds(dwellTime);

    // --- RF2 (Debug LOW) ---
    PORTB = basePort | PATTERN_RF2; 
    delayMicroseconds(dwellTime);

    // --- RF3 (Debug HIGH) ---
    PORTB = basePort | PATTERN_RF3 | 0x20; 
    delayMicroseconds(runDelay);

    // --- RF4 (Debug LOW) ---
    PORTB = basePort | PATTERN_RF4; 
    delayMicroseconds(dwellTime);

    // --- RF5 (Debug HIGH) ---
    PORTB = basePort | PATTERN_RF5 | 0x20; 
    delayMicroseconds(runDelay);

    // --- RF6 (Debug LOW) ---
    PORTB = basePort | PATTERN_RF6; 
    delayMicroseconds(dwellTime);

    // --- ALL OFF / TERMINATED (Debug LOW) ---
    PORTB = basePort | PATTERN_ALL_OFF; 
    delayMicroseconds(runDelay);
  }
}