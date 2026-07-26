
About me I am Rishav Anand from PVL PE 

=========================================================
      BATTERY RIG MASTER STUDIO v2.0 - SYSTEM README
=========================================================

Welcome to the Automated Battery Discharge & Testing Rig!

DEVELOPER: Rishav
(Click the email link above for support, updates, or inquiries)

--- SYSTEM OVERVIEW ---
This application interfaces with a laboratory-grade, automated battery capacity tester. Utilizing Closed-Loop Active Feedback, the rig dynamically switches 11 individual high-power relays to perfectly match target discharge rates across different voltage brackets, regardless of battery voltage sag.

Designed for precision and safety, the hardware relies on an ADS1115 16-bit I2C ADC, a 125A/75mV current shunt, and a custom 150kΩ/10kΩ voltage divider to safely measure up to 65V DC with microvolt accuracy.

--- CORE FEATURES ---

1. Closed-Loop Active Feedback:
   The system actively calculates the error between the targeted load (e.g., 55A) and the actual measured shunt current. It dynamically stacks and adjusts relays in real-time to achieve the exact requested load.

2. EEPROM Persistent Calibration:
   Hardware calibration multipliers (Voltage and Current) are securely saved to the Arduino's internal EEPROM. Calibration survives power cycles and firmware reflashes.

3. Advanced Safety Protocols:
   - Voltage Spike Guard: Instantly cuts all load (0A) if a sudden voltage spike/drop is detected (dV/dt > 3.0V/s).
   - 0V Emergency Protect: Universal kill-switch if the battery disconnects or the BMS trips.
   - 5-Second Settling Time: Allows battery chemistry to stabilize upon connection before applying heavy loads.
   - 5-Second Switching Delay: Prevents mechanical relay chatter.

4. Dual Operation Modes:
   - Standard Mode: Aggressive discharge targets (up to 55A).
   - Nominal Mode: Gentle discharge targets activated via hardware switch (Pin 47) for standard capacity rating.

--- GUI FUNCTIONALITY ---

• Control & Monitor: 
  Watch live telemetry (Volts, Amps, Ah), calculated internal resistance, and active relay requests. Includes a raw Serial Debug console to monitor every system byte.

• Calibration Studio: 
  Live 10-sample averaged calibration designed specifically to work flawlessly with coarse/whole-number multimeters.

• Security & Source Code: 
  Securely access the underlying Python and Arduino source code directly from this application via password-protected tabs.

=========================================================
"Precision Testing. Automated Safety. Maximum Control."
=========================================================