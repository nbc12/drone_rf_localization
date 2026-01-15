/*
 * High Performance SP8T RF Switch Controller with Serial Control
 * Target: Arduino Nano (ATmega328P)
 * IC: PE42582
 *
 * Switching Sequence (CYCLE mode): RF1 -> RF2 -> RF3 -> RF4 -> RF5 -> RF6 -> ALL OFF -> Repeat
 * Manual Mode: Controlled via Serial (RF1-RF8, RFX)
 * Dwell Time: Variable (Default 40us), set via Serial 'T' command
 * Sync: Pin D12 goes HIGH during RF1, LOW otherwise.
 * Debug: Pin D13 (LED) toggles every switch (H, L, H, L, H, L) then holds Low for All-Off
 *
 * Pin Connections:
 * D8  (PB0) -> V1
 * D9  (PB1) -> V2
 * D10 (PB2) -> V3
 * D11 (PB3) -> V4 (Used for All-Off State)
 * D12 (PB4) -> SYNC (To SDR/Scope)
 * D13 (PB5) -> DEBUG / LED
 * GND       -> LS (Pin 1)
 * GND       -> V_SS_EXT (Pin 7)
 */

#include <avr/io.h>
#include <Arduino.h> // Required for Serial and delayMicroseconds

void runCycleSequence();
void setup();
void loop();

// Direct Port B Bit Masks
// D8(PB0)=V1, D9(PB1)=V2, D10(PB2)=V3, D11(PB3)=V4, D12(PB4)=SYNC, D13(PB5)=DEBUG

// Port Patterns (Table 5 of Datasheet)
const uint8_t PATTERN_RF1 = 0x00; // V4=0, V3=0, V2=0, V1=0
const uint8_t PATTERN_RF2 = 0x04; // V4=0, V3=1, V2=0, V1=0 (PB2 High)
const uint8_t PATTERN_RF3 = 0x02; // V4=0, V3=0, V2=1, V1=0 (PB1 High)
const uint8_t PATTERN_RF4 = 0x06; // V4=0, V3=1, V2=1, V1=0 (PB1, PB2)
const uint8_t PATTERN_RF5 = 0x01; // V4=0, V3=0, V2=0, V1=1 (PB0 High)
const uint8_t PATTERN_RF6 = 0x05; // V4=0, V3=1, V2=0, V1=1 (PB0, PB2)
const uint8_t PATTERN_RF7 = 0x03; // V4=0, V3=0, V2=1, V1=1 (PB0, PB1)
const uint8_t PATTERN_RF8 = 0x07; // V4=0, V3=1, V2=1, V1=1 (PB0, PB1, PB2)

// All Isolated State (Terminated)
const uint8_t PATTERN_ALL_OFF = 0x08; // V4=1 (PB3 High)

// Globals
unsigned long dwellTime = 40; // Microseconds
bool isCycling = false;

void setup() {
  // Set D8-D13 as OUTPUT (PB0-PB5)
  // 0x3F = 00111111 (Sets bits 0-5 to 1)
  DDRB |= 0x3F; 
  PORTB &= ~0x3F; // Initial Low

  // SERIAL MODE
  Serial.begin(115200);
  Serial.setTimeout(10); // Short timeout for non-blocking feel
}

void loop() {
  // 1. Check for Serial Commands (Only if Serial is enabled)
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();
    
    if (cmd == "CYCLE") {
      isCycling = true;
      Serial.println("CYCLE set");
    } 
    else if (cmd.startsWith("T")) {
      long t = cmd.substring(1).toInt();
      if (t >= 10) dwellTime = t; // Safety limit 10us minimum
      Serial.print("T");
      Serial.print(dwellTime, DEC);
      Serial.println(" set");
    }
    else {
      // Manual Commands (Stop cycling if manual command received)
      uint8_t mask = 0xC0; 
      uint8_t basePort = PORTB & mask;
      bool valid = true;

      if      (cmd == "RF1") { PORTB = basePort | PATTERN_RF1; Serial.println("RF1 set"); }
      else if (cmd == "RF2") { PORTB = basePort | PATTERN_RF2; Serial.println("RF2 set"); }
      else if (cmd == "RF3") { PORTB = basePort | PATTERN_RF3; Serial.println("RF3 set"); }
      else if (cmd == "RF4") { PORTB = basePort | PATTERN_RF4; Serial.println("RF4 set"); }
      else if (cmd == "RF5") { PORTB = basePort | PATTERN_RF5; Serial.println("RF5 set"); }
      else if (cmd == "RF6") { PORTB = basePort | PATTERN_RF6; Serial.println("RF6 set"); }
      else if (cmd == "RF7") { PORTB = basePort | PATTERN_RF7; Serial.println("RF7 set"); }
      else if (cmd == "RF8") { PORTB = basePort | PATTERN_RF8; Serial.println("RF8 set"); }
      else if (cmd == "RFX") { PORTB = basePort | PATTERN_ALL_OFF; Serial.println("RFX set"); }
      else { valid = false; Serial.println("Unknown Command"); }

      if (valid) isCycling = false;
    }
  }

  // 2. Run Cycle if enabled
  if (isCycling) {
    runCycleSequence();
  }
}

void runCycleSequence() {
  // Pattern cache
  uint8_t mask = 0xC0;
  uint8_t basePort = PORTB & mask;

  // DISABLE TIMER0 INTERRUPT locally to prevent 6us jitter
  // We save the old value to restore it if we exit the loop
  uint8_t oldTIMSK0 = TIMSK0;
  TIMSK0 = 0; 

  // Calculate how many frames to run before checking Serial (approx 1 second interval)
  // 1 Frame = 7 states * dwellTime
  unsigned long frameDuration = 7 * dwellTime;
  if (frameDuration == 0) frameDuration = 280; // Safety fallback
  unsigned long cyclesPerCheck = 1000000 / frameDuration;
  unsigned long cycleCount = 0;

  // Start with interrupts disabled for the high-performance loop
  noInterrupts();
  int lowdelay = dwellTime - 1;
  // We loop here to avoid the overhead of returning to the main loop() function 
  while (isCycling) {
    // --- RF1 (Sync HIGH, Debug HIGH) ---
    PORTB = basePort | PATTERN_RF1 | 0x10 | 0x20;
    delayMicroseconds(dwellTime);

    // --- RF2 (Debug LOW) ---
    PORTB = basePort | PATTERN_RF2; 
    delayMicroseconds(dwellTime);

    // --- RF3 (Debug HIGH) ---
    PORTB = basePort | PATTERN_RF3 | 0x20; 
    delayMicroseconds(lowdelay);

    // // --- RF4 (Debug LOW) ---
    // PORTB = basePort | PATTERN_RF4; 
    // delayMicroseconds(dwellTime);

    // // --- RF5 (Debug HIGH) ---
    // PORTB = basePort | PATTERN_RF5 | 0x20; 
    // delayMicroseconds(lowdelay);

    // // --- RF6 (Debug LOW) ---
    // PORTB = basePort | PATTERN_RF6; 
    // delayMicroseconds(dwellTime);

    // --- ALL OFF / TERMINATED (Debug LOW) ---
    PORTB = basePort | PATTERN_ALL_OFF; 
    delayMicroseconds(lowdelay);

    // Increment frame counter
    cycleCount++;

    // Only check Serial every ~1 second to minimize jitter events
    if (cycleCount >= cyclesPerCheck) {
      cycleCount = 0;

      // Re-enable interrupts briefly to catch any pending Serial data
      interrupts(); // SEI (1 cycle)
      
      // Safety NOP
      __asm__ __volatile__ ("nop\n\t");

      if (Serial.available() > 0) {
        TIMSK0 = oldTIMSK0; // Restore Timer0 before exiting
        return; 
      }

      // Disable interrupts again immediately for the next 1-second batch
      noInterrupts(); // CLI (1 cycle)
    }
  }
  
  // Restore Timer0 and Interrupts if we exit naturally
  TIMSK0 = oldTIMSK0;
  interrupts();
}