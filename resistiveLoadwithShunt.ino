// ==========================================================
// AUTOMATED BATTERY DISCHARGE & TESTING RIG (MASTER CODE)
// ADS1115 + 125A/75mV Shunt + EEPROM + Closed-Loop Matching
// Includes Averaged Calibration for Coarse/Whole-Number Meters
// ==========================================================

#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include <EEPROM.h>
#include <math.h>

Adafruit_ADS1115 ads; // Default I2C Address 0x48

struct RelayConfig {
  int relayNumber; 
  int pin;         
  int amps;        
};

// Map of Relay # -> Arduino Pin -> Amps
RelayConfig relays[11] = {
  {11, 13, 50}, {10, 12, 20}, {9, 11, 20}, {8, 10, 10}, {7, 9, 10}, 
  {6, 8, 5}, {5, 7, 5}, {4, 6, 2}, {3, 5, 2}, {2, 4, 1}, {1, 3, 1}  
};

// --- PIN CONFIGURATIONS ---
const int PIN_SW_NOMINAL = 47; // Toggle Switch for Nominal Discharge Mode
const int PIN_SW_SERIAL  = 48; // Serial Switch
const int PIN_SW_AUTO    = 49; // Automation Switch

const int PIN_LED_SER_RED = 50;
const int PIN_LED_SER_GRN = 51;
const int PIN_LED_AUT_GRN = 52;
const int PIN_LED_AUT_RED = 53;

const int RELAY_ON  = LOW;  
const int RELAY_OFF = HIGH; 

// --- EEPROM ADDRESSES & DEFAULT MULTIPLIERS ---
const int EEPROM_ADDR_FLAG = 0;   
const int EEPROM_ADDR_VM   = 4;   
const int EEPROM_ADDR_IM   = 8;   
const uint32_t EEPROM_VALID_KEY = 0xABCD1234;

float voltageMultiplier = 16.0;   
float currentMultiplier = 1.6667; 

// --- CRITICAL THRESHOLDS ---
const float CUTOFF_VOLTAGE      = 37.5;
const float NEW_BATTERY_VOLTAGE = 44.0;
const float MAX_ALLOWED_DV_DT   = 3.0; // V/s: Sudden spike cut-off threshold

// --- TIMING CONSTANTS ---
const int SWITCHING_INTERVAL = 5000; // 5-second space between relay switching
const int BATTERY_SETTLE_TIME= 5000; // 5-second settling time after 0V reconnect

// --- GLOBAL VARIABLES ---
unsigned long currentMillis = 0;
bool serialConnected = false;
unsigned long lastBlinkTime = 0, lastFastBlinkTime = 0;
bool blinkState = false, fastBlinkState = false;

bool loggingActive = false;
unsigned long lastLogTime = 0, lastAhCalcTime = 0;
float dischargedAh = 0.0;

enum SystemMode { MODE_BOOT, MODE_SAFE, MODE_SERIAL, MODE_AUTO };
SystemMode currentSysMode = MODE_BOOT, lastSysMode = MODE_BOOT;

enum AutoState {
  STATE_IDLE, STATE_INIT_BLINK, STATE_WAITING_BATTERY, STATE_SETTLING_5S,
  STATE_STARTUP_CHASE, STATE_DISCHARGING, STATE_0V_PROTECT, 
  STATE_CUTOFF, STATE_SPIKE_FAULT, STATE_NEW_BATTERY
};
AutoState autoState = STATE_IDLE;

unsigned long stateTimer = 0;
int currentAutoLoadA = 0; // The sum of relays currently turned ON
float measuredShuntCurrent = 0.0;
float calculatedEquivalentResistance = 0.0;

float lastSavedV = 0.0;
float voltageChangeRate = 0.0; // dV/dt in Volts per second
unsigned long lastRateCalcTime = 0, lastLoadChangeTime = 0, lastLoadComputeTime = 0;

// Function Declarations
float getRawVoltageADC();
float getVoltage();
float getRawCurrentmV();
float getShuntCurrent();
void loadEEPROMCalibration();
void saveEEPROMCalibration();
void updateBlinks();
void updateSensorsAndCapacity();
void handleDischargeRules(float currentV);
void handleSerialGlobal(String cmd);
void runSerialMode(String cmd);
void runAutoMode();
void runBootMode();
void setLoad(int target);
void turnAllRelaysOff();
void turnAllLedsOff();
void handleFault(AutoState s);
void visualizeChase();
void visualizeInit();
void printLiveLog();

// ==========================================================
// SETUP & MAIN LOOP
// ==========================================================
void setup() {
  Serial.begin(115200);
  
  for (int i = 0; i < 11; i++) {
    pinMode(relays[i].pin, OUTPUT);
    digitalWrite(relays[i].pin, RELAY_OFF);
  }
  
  pinMode(PIN_SW_NOMINAL, INPUT); 
  pinMode(PIN_SW_SERIAL, INPUT); 
  pinMode(PIN_SW_AUTO, INPUT);
  
  pinMode(PIN_LED_SER_RED, OUTPUT); 
  pinMode(PIN_LED_SER_GRN, OUTPUT);
  pinMode(PIN_LED_AUT_GRN, OUTPUT); 
  pinMode(PIN_LED_AUT_RED, OUTPUT);

  // Initialize ADS1115 I2C ADC
  Wire.begin();
  if (!ads.begin(0x48)) {
    Serial.println(">>> ERROR: ADS1115 ADC not detected on I2C bus!");
  } else {
    ads.setGain(GAIN_SIXTEEN);
  }

  loadEEPROMCalibration();
  
  Serial.println("\n========================================================");
  Serial.println(">>> BATTERY RIG: CLOSED-LOOP ACTIVE MATCHING READY   <<<");
  Serial.print(">>> Stored Voltage Multiplier: "); Serial.println(voltageMultiplier, 4);
  Serial.print(">>> Stored Current Multiplier: "); Serial.println(currentMultiplier, 4);
  Serial.println("========================================================");
}

void loop() {
  currentMillis = millis();
  updateBlinks();
  updateSensorsAndCapacity();

  if (currentMillis < 3000) currentSysMode = MODE_BOOT;
  else if (digitalRead(PIN_SW_SERIAL) == HIGH) currentSysMode = MODE_SERIAL;
  else if (digitalRead(PIN_SW_AUTO) == HIGH) currentSysMode = MODE_AUTO;
  else currentSysMode = MODE_SAFE;

  if (currentSysMode != lastSysMode) {
    turnAllLedsOff();
    turnAllRelaysOff();
    autoState = STATE_IDLE;
    lastSysMode = currentSysMode;
  }

  String cmd = "";
  if (Serial.available()) {
    cmd = Serial.readStringUntil('\n');
    cmd.trim(); 
    serialConnected = true;
    handleSerialGlobal(cmd);
  }

  if (currentSysMode == MODE_BOOT) runBootMode();
  else if (currentSysMode == MODE_SERIAL) runSerialMode(cmd); 
  else if (currentSysMode == MODE_AUTO) runAutoMode();

  printLiveLog();
}

// ==========================================================
// EEPROM CALIBRATION STORAGE
// ==========================================================
void loadEEPROMCalibration() {
  uint32_t flag = 0;
  EEPROM.get(EEPROM_ADDR_FLAG, flag);
  if (flag == EEPROM_VALID_KEY) {
    EEPROM.get(EEPROM_ADDR_VM, voltageMultiplier);
    EEPROM.get(EEPROM_ADDR_IM, currentMultiplier);
  } else {
    saveEEPROMCalibration(); // Initialize default EEPROM if unwritten
  }
}

void saveEEPROMCalibration() {
  EEPROM.put(EEPROM_ADDR_FLAG, EEPROM_VALID_KEY);
  EEPROM.put(EEPROM_ADDR_VM, voltageMultiplier);
  EEPROM.put(EEPROM_ADDR_IM, currentMultiplier);
}

// ==========================================================
// AUTOMATION LOGIC
// ==========================================================
void runAutoMode() {
  float currentV = getVoltage();

  switch (autoState) {
    case STATE_IDLE:
      stateTimer = currentMillis;
      autoState = STATE_INIT_BLINK;
      break;

    case STATE_INIT_BLINK:
      visualizeInit();
      if (currentMillis - stateTimer >= 10000) {
        if (currentV < 2.0) autoState = STATE_WAITING_BATTERY;
        else if (currentV <= CUTOFF_VOLTAGE) autoState = STATE_CUTOFF;
        else autoState = STATE_DISCHARGING;
      }
      break;

    case STATE_WAITING_BATTERY:
      digitalWrite(PIN_LED_AUT_RED, blinkState);
      digitalWrite(PIN_LED_AUT_GRN, LOW);
      if (currentV >= 2.0) {
        stateTimer = currentMillis;
        dischargedAh = 0.0;
        autoState = STATE_SETTLING_5S;
      }
      break;

    case STATE_SETTLING_5S:
      digitalWrite(PIN_LED_AUT_GRN, fastBlinkState);
      digitalWrite(PIN_LED_AUT_RED, fastBlinkState);
      if (currentMillis - stateTimer >= BATTERY_SETTLE_TIME) {
        stateTimer = currentMillis;
        autoState = STATE_STARTUP_CHASE;
      }
      break;

    case STATE_STARTUP_CHASE:
      visualizeChase();
      if (currentMillis - stateTimer >= 10000) autoState = STATE_DISCHARGING;
      break;

    case STATE_DISCHARGING:
      digitalWrite(PIN_LED_AUT_GRN, HIGH);
      digitalWrite(PIN_LED_AUT_RED, LOW);
      
      if (currentV < 2.0) { handleFault(STATE_0V_PROTECT); break; }
      if (currentV <= CUTOFF_VOLTAGE) { handleFault(STATE_CUTOFF); break; }
      
      if (abs(voltageChangeRate) > MAX_ALLOWED_DV_DT) {
        handleFault(STATE_SPIKE_FAULT);
        break;
      }

      handleDischargeRules(currentV);
      break;

    case STATE_SPIKE_FAULT:
      digitalWrite(PIN_LED_AUT_RED, fastBlinkState);
      digitalWrite(PIN_LED_AUT_GRN, LOW);
      if (abs(voltageChangeRate) < 0.20 && currentV >= 2.0) {
        stateTimer = currentMillis;
        autoState = STATE_SETTLING_5S;
      }
      break;

    case STATE_CUTOFF:
      digitalWrite(PIN_LED_AUT_RED, HIGH);
      digitalWrite(PIN_LED_AUT_GRN, blinkState);
      if (currentV >= NEW_BATTERY_VOLTAGE) autoState = STATE_NEW_BATTERY;
      break;
      
    case STATE_0V_PROTECT:
      digitalWrite(PIN_LED_AUT_RED, blinkState);
      digitalWrite(PIN_LED_AUT_GRN, LOW);
      if (currentV >= 2.0) {
        stateTimer = currentMillis;
        autoState = STATE_SETTLING_5S;
      }
      break;

    case STATE_NEW_BATTERY:
      visualizeInit();
      if (currentMillis - stateTimer >= 10000) {
        turnAllLedsOff();
        currentAutoLoadA = 0; 
        dischargedAh = 0.0; 
        autoState = STATE_DISCHARGING;
      }
      break;

    default:
      handleFault(STATE_0V_PROTECT);
      break;
  }
}

void handleDischargeRules(float currentV) {
  // 1. Enforce 5s delay between switching cycles to allow current to stabilize
  if (currentMillis - lastLoadComputeTime < SWITCHING_INTERVAL) return;

  float targetLoadA = 0.0;
  bool nominalSwitchActive = (digitalRead(PIN_SW_NOMINAL) == HIGH);

  // 2. Determine the TARGET goal based on rules
  if (nominalSwitchActive) {
    if (currentV >= 45.0) targetLoadA = 50.0;
    else if (currentV >= 41.0) targetLoadA = 20.0;
    else targetLoadA = 12.0;
  } else {
    if (currentV >= 45.0) targetLoadA = 55.0;
    else if (currentV >= 41.0) targetLoadA = 50.0;
    else targetLoadA = 12.0;
  }

  // 3. CLOSED-LOOP FEEDBACK: Match ACTUAL current to TARGET current
  float currentError = targetLoadA - measuredShuntCurrent;

  // Hysteresis: Only adjust if actual current is off by > 1.5 Amps
  if (abs(currentError) > 1.5) {
    
    // Adjust the internal relay request by the error amount
    int adjustment = round(currentError);
    int newRelayRequest = currentAutoLoadA + adjustment;
    
    newRelayRequest = constrain(newRelayRequest, 0, 126);

    // Apply the new relay combination
    if (newRelayRequest != currentAutoLoadA) {
      setLoad(newRelayRequest);
      lastLoadComputeTime = currentMillis;
    }
  }
}

// ==========================================================
// SERIAL & CALIBRATION COMMANDS
// ==========================================================
void handleSerialGlobal(String cmd) {
  if (cmd == "") return;
  String lowerCmd = cmd;
  lowerCmd.toLowerCase();

  if (lowerCmd == "voltmeasure") {
    Serial.print("Volts: "); Serial.print(getVoltage(), 3); 
    Serial.print("V | Current: "); Serial.print(measuredShuntCurrent, 3); Serial.println("A");
  }
  else if (lowerCmd == "logi") { loggingActive = true; Serial.println(">>> TELEMETRY ENABLED"); } 
  else if (lowerCmd == "logf") { loggingActive = false; Serial.println(">>> TELEMETRY DISABLED"); }
  else if (lowerCmd == "mode") { Serial.print("Mode: "); Serial.println(currentSysMode); }

  // --- AVERAGED LIVE CALIBRATION FOR COARSE METERS ---
  else if (lowerCmd.startsWith("calib_v")) {
    float actualV = cmd.substring(7).toFloat();
    
    // Take 10 samples to smooth out reading
    float rawSum = 0;
    for(int i=0; i<10; i++) {
      rawSum += getRawVoltageADC();
      delay(10);
    }
    float rawADCVolts = rawSum / 10.0;

    if (actualV > 1.0 && rawADCVolts > 0.1) {
      voltageMultiplier = actualV / rawADCVolts;
      saveEEPROMCalibration();
      Serial.print(">>> CALIB SUCCESS: Voltage Multiplier Updated To ");
      Serial.println(voltageMultiplier, 5);
    } else {
      Serial.println(">>> CALIB ERROR: Invalid reference voltage input!");
    }
  }
  else if (lowerCmd.startsWith("calib_i")) {
    float actualI = cmd.substring(7).toFloat();
    
    // Take 10 samples to smooth out reading
    float rawSum = 0;
    for(int i=0; i<10; i++) {
      rawSum += fabs(getRawCurrentmV());
      delay(10);
    }
    float rawShuntmV = rawSum / 10.0;

    if (actualI > 0.05 && rawShuntmV > 0.01) {
      currentMultiplier = actualI / rawShuntmV;
      saveEEPROMCalibration();
      Serial.print(">>> CALIB SUCCESS: Current Multiplier Updated To ");
      Serial.println(currentMultiplier, 5);
    } else {
      Serial.println(">>> CALIB ERROR: Invalid reference current input!");
    }
  }
  else if (lowerCmd.startsWith("set_vm")) {
    voltageMultiplier = cmd.substring(6).toFloat();
    saveEEPROMCalibration();
    Serial.print(">>> VM UPDATED TO "); Serial.println(voltageMultiplier, 5);
  }
  else if (lowerCmd.startsWith("set_im")) {
    currentMultiplier = cmd.substring(6).toFloat();
    saveEEPROMCalibration();
    Serial.print(">>> IM UPDATED TO "); Serial.println(currentMultiplier, 5);
  }
}

void runSerialMode(String cmd) {
  if (serialConnected) {
    digitalWrite(PIN_LED_SER_GRN, HIGH); 
    digitalWrite(PIN_LED_SER_RED, LOW);
  } else {
    digitalWrite(PIN_LED_SER_RED, blinkState); 
    digitalWrite(PIN_LED_SER_GRN, LOW);
  }

  if (cmd == "") return;
  String lowerCmd = cmd;
  lowerCmd.toLowerCase();

  if (lowerCmd.startsWith("ireq") || lowerCmd.startsWith("iset")) {
    String val = "";
    for (int i = 0; i < cmd.length(); i++) {
      if (isDigit(cmd.charAt(i))) val += cmd.charAt(i);
    }
    if (val.length() > 0) {
      int requestedAmps = val.toInt();
      setLoad(constrain(requestedAmps, 0, 126));
      Serial.print(">>> LOAD SET TO: "); Serial.print(currentAutoLoadA); Serial.println("A");
    }
  }
}

// ==========================================================
// SENSORS & UTILITIES 
// ==========================================================
float getRawVoltageADC() {
  ads.setGain(GAIN_ONE); // +/- 4.096V range
  int16_t rawA2 = ads.readADC_SingleEnded(2);
  return ads.computeVolts(rawA2); 
}

float getVoltage() {
  float batteryVolts = getRawVoltageADC() * voltageMultiplier;
  return (batteryVolts < 1.0) ? 0.0 : batteryVolts;
}

float getRawCurrentmV() {
  ads.setGain(GAIN_SIXTEEN); // Force +/- 0.256V gain before reading shunt
  int16_t rawDiff = ads.readADC_Differential_0_1();
  return ads.computeVolts(rawDiff) * 1000.0; // Converts Volts to mV
}

float getShuntCurrent() {
  float raw_mV = getRawCurrentmV();
  float currentAmps = fabs(raw_mV) * currentMultiplier; 
  return (currentAmps < 0.05) ? 0.0 : currentAmps;
}

void updateSensorsAndCapacity() {
  measuredShuntCurrent = getShuntCurrent();
  float currentV = getVoltage();

  if (measuredShuntCurrent > 0.2) {
    calculatedEquivalentResistance = currentV / measuredShuntCurrent;
  } else {
    calculatedEquivalentResistance = 0.0;
  }

  if (currentMillis - lastRateCalcTime >= 1000) {
    voltageChangeRate = currentV - lastSavedV;
    lastSavedV = currentV;
    lastRateCalcTime = currentMillis;
  }

  if (currentMillis - lastAhCalcTime >= 1000) {
    dischargedAh += (measuredShuntCurrent / 3600.0);
    lastAhCalcTime = currentMillis;
  }
}

void setLoad(int target) {
  if (target == currentAutoLoadA) return;
  lastLoadChangeTime = currentMillis;
  
  for (int i = 0; i < 11; i++) digitalWrite(relays[i].pin, RELAY_OFF);
  
  int remaining = target;
  for (int i = 0; i < 11; i++) {
    if (remaining >= relays[i].amps) {
      remaining -= relays[i].amps;
      digitalWrite(relays[i].pin, RELAY_ON);
    }
  }
  currentAutoLoadA = target;
}

void turnAllRelaysOff() { 
  for (int i = 0; i < 11; i++) digitalWrite(relays[i].pin, RELAY_OFF); 
  if (currentAutoLoadA != 0) lastLoadChangeTime = currentMillis;
  currentAutoLoadA = 0;
}

void turnAllLedsOff() {
  digitalWrite(PIN_LED_SER_RED, LOW); digitalWrite(PIN_LED_SER_GRN, LOW);
  digitalWrite(PIN_LED_AUT_RED, LOW); digitalWrite(PIN_LED_AUT_GRN, LOW);
}

void handleFault(AutoState s) {
  turnAllRelaysOff();
  stateTimer = currentMillis;
  autoState = s;
}

void updateBlinks() {
  if (currentMillis - lastBlinkTime >= 500) { blinkState = !blinkState; lastBlinkTime = currentMillis; }
  if (currentMillis - lastFastBlinkTime >= 150) { fastBlinkState = !fastBlinkState; lastFastBlinkTime = currentMillis; }
}

void visualizeChase() {
  int step = (currentMillis / 250) % 3;
  digitalWrite(PIN_LED_AUT_GRN, step < 2);
  digitalWrite(PIN_LED_AUT_RED, step > 0);
}

void visualizeInit() {
  digitalWrite(PIN_LED_AUT_GRN, blinkState);
  if (blinkState && (currentMillis % 10 < 5)) digitalWrite(PIN_LED_AUT_RED, HIGH);
  else digitalWrite(PIN_LED_AUT_RED, LOW);
}

void runBootMode() {
  digitalWrite(PIN_LED_SER_RED, blinkState);
  digitalWrite(PIN_LED_AUT_GRN, !blinkState);
}

void printLiveLog() {
  if (!loggingActive || (currentMillis - lastLogTime < 1000)) return;
  lastLogTime = currentMillis;
  
  Serial.print("[LOG] Volts: "); Serial.print(getVoltage(), 2);
  Serial.print("V | ACTUAL Current: "); Serial.print(measuredShuntCurrent, 2);
  Serial.print("A | Relay Req: "); Serial.print(currentAutoLoadA);
  
  Serial.print("A | Mode: "); 
  Serial.print(digitalRead(PIN_SW_NOMINAL) ? "NOMINAL" : "STANDARD");
  
  Serial.print(" | Ah: "); Serial.print(dischargedAh, 2); Serial.println(" Ah");
}