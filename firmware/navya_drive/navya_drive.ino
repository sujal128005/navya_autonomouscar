/*
  Navya drive firmware v2 - Arduino Uno

  Rear: two BLDC hub motors through their YL-12 controllers (throttle PWM stands
  in for the hand throttle). Front: the toy's own steering motor through a
  BTS7960 driver, with a potentiometer on the steering shaft for the angle and
  two limit switches at full left / full right.

  Modes, picked by the FlySky CH5 switch:
    MANUAL  - right stick up/down (CH2) = forward / brake,
              right stick left/right (CH1) = steering.
    AUTO    - the laptop drives and steers over USB serial.
              Pulling CH2 back still stops the car (operator override).
    NO_RC   - no receiver signal: motors off, brakes on, steering motor off.

  The car also stops if the laptop goes quiet for HOST_TIMEOUT_MS (steering
  then holds straight).

  Serial protocol, 115200 baud, one command per line:
    D,<left>,<right>,<brake>[,<steer>]  speed 0..1000 per wheel, brake 0/1,
                                        steer -1000 (full left)..1000 (full right)
    R,<pwmLeft>,<pwmRight>              raw throttle PWM, for calibration only
    M,<pwm>                             raw steering motor -255..255 (+ = RPWM),
                                        for steering calibration only (AUTO)
    K,L / K,C / K,R                     store the current pot reading as full left /
                                        straight / full right (kept in EEPROM)
    K,I,<0|1>                           1 = RPWM turns the wheels LEFT
    K,X                                 forget the steering calibration
    ?                                   print the settings below
  Every STATUS_PERIOD_MS the Uno replies:
    S,<mode>,<ch2_us>,<ch5_us>,<host_ok>,<pwmLeft>,<pwmRight>,<brake>,
      <ch1_us>,<steer_target>,<steer_pos>,<pot_raw>,<limit_left>,<limit_right>,<steer_state>,
      <battery_left_mV>,<battery_right_mV>       (0 = no battery divider connected)
*/

#include <EEPROM.h>

// ---------------- Pins ----------------
const uint8_t PIN_RC_MODE = 2;         // receiver CH5 signal (interrupt pin)
const uint8_t PIN_RC_THROTTLE = 3;     // receiver CH2 signal (interrupt pin)
const uint8_t PIN_RC_STEER = 4;        // receiver CH1 signal (pin-change interrupt)
const uint8_t PIN_STEER_RPWM = 5;      // BTS7960 RPWM
const uint8_t PIN_STEER_LPWM = 6;      // BTS7960 LPWM
const uint8_t PIN_DIR_RIGHT = 7;       // controller F/R silver wire
const uint8_t PIN_DIR_LEFT = 8;
const uint8_t PIN_THROTTLE_LEFT = 9;   // controller throttle purple wire
const uint8_t PIN_THROTTLE_RIGHT = 10;
const uint8_t PIN_BRAKE_LEFT = 11;     // controller brake wire (optional, active low)
const uint8_t PIN_BRAKE_RIGHT = 12;
const uint8_t PIN_LED = 13;
const uint8_t PIN_STEER_POT = A0;      // potentiometer wiper (ends to 5V and GND)
const uint8_t PIN_LIMIT_LEFT = A1;     // limit switch to GND, closed = at full left
const uint8_t PIN_LIMIT_RIGHT = A2;    // limit switch to GND, closed = at full right
const uint8_t PIN_STEER_ENABLE = A3;   // BTS7960 R_EN + L_EN
const uint8_t PIN_BATT_LEFT = A4;      // left LiPo through a 47k / 10k divider
const uint8_t PIN_BATT_RIGHT = A5;     // right LiPo through a 47k / 10k divider

// ---------------- Battery monitor ----------------
// LiPo + -> 47k -> pin -> 10k -> GND (battery negatives joined to Arduino GND).
// 25.2 V full charge reads as 4.42 V at the pin.
const float BATT_DIVIDER = (47.0 + 10.0) / 10.0;
const float BATT_ADC_REF_V = 5.0;      // the Uno's 5 V; raise/lower to match a multimeter

// ---------------- Throttle calibration ----------------
// Find PWM_START with: python throttle_test.py --sweep (wheels off the ground)
const uint8_t PWM_IDLE = 0;            // throttle output when stopped
const uint8_t PWM_START = 75;          // lowest PWM at which the wheels turn (bench: ~75-78)
const uint8_t PWM_MAX = 130;           // PWM sent for speed 1000 (this is the speed cap)
const uint8_t PWM_RAW_LIMIT = 160;     // ceiling for R, calibration commands
const bool INVERT_LEFT = false;        // true = drive this wheel's F/R wire low
const bool INVERT_RIGHT = false;
const uint16_t RAMP_UP_PER_10MS = 5;   // speed units gained per 10 ms (0 -> 1000 in 2 s)

// ---------------- Steering ----------------
const bool STEERING_INSTALLED = true;  // false = never drive the steering motor
const uint8_t STEER_PWM_MAX = 200;     // full effort far from the target
const uint8_t STEER_PWM_MIN = 70;      // least effort that still moves the toy gearbox
const int16_t STEER_DEADBAND = 25;     // within 2.5% of travel: close enough, motor off
const int16_t STEER_SLOW_ZONE = 250;   // closer than this, effort drops towards STEER_PWM_MIN
const int16_t STEER_TARGET_LIMIT = 900; // never aim past 90% of the calibrated travel
const uint16_t STEER_STALL_MS = 1500;  // driving this long without the pot moving = stuck
const uint16_t STEER_FAULT_HOLD_MS = 2000;
const uint16_t POT_MIN_VALID = 15;     // readings outside this = broken pot wire
const uint16_t POT_MAX_VALID = 1008;
const uint8_t RAW_STEER_LIMIT = 255;

// ---------------- Radio ----------------
// Our FS-CT6B: CH2 centre ~1464, full up ~1756 with SWA down (SWA up = dual rate, ~1644).
const bool REQUIRE_RC = true;          // false = bench testing without the transmitter
const uint16_t RC_AUTO_ABOVE_US = 1700;
const uint16_t RC_STOP_BELOW_US = 1400;
const uint16_t RC_FORWARD_FROM_US = 1520;
const uint16_t RC_FORWARD_FULL_US = 1740;
const uint16_t RC_STEER_CENTER_US = 1500;   // CH1 stick centred (check in the S, line)
const uint16_t RC_STEER_SPAN_US = 250;      // stick this far from centre = full lock
const uint16_t RC_STEER_DEADBAND_US = 25;
const uint16_t RC_TIMEOUT_MS = 100;

// ---------------- Laptop link ----------------
const uint16_t HOST_TIMEOUT_MS = 300;
const uint16_t STATUS_PERIOD_MS = 100;

enum Mode { MODE_NO_RC, MODE_MANUAL, MODE_AUTO };

struct RcSnapshot {
  uint16_t throttleUs;
  uint16_t modeUs;
  uint16_t steerUs;
  bool fresh;        // CH2 and CH5 both arriving
  bool steerFresh;   // CH1 arriving
};

struct SteerCal {
  uint16_t magic;
  uint16_t left;
  uint16_t center;
  uint16_t right;
  uint8_t invert;    // 1 = RPWM turns the wheels left
};
const uint16_t CAL_MAGIC = 0x4E56;  // "NV"
const int CAL_ADDR = 0;

// Written by the pin interrupts.
volatile uint32_t throttleRiseUs = 0;
volatile uint32_t modeRiseUs = 0;
volatile uint32_t steerRiseUs = 0;
volatile uint16_t throttlePulseUs = 0;
volatile uint16_t modePulseUs = 0;
volatile uint16_t steerPulseUs = 0;
volatile uint32_t throttleSeenMs = 0;
volatile uint32_t modeSeenMs = 0;
volatile uint32_t steerSeenMs = 0;

// Last laptop command.
int16_t hostLeft = 0;
int16_t hostRight = 0;
bool hostBrake = true;
bool hostRaw = false;
uint8_t rawLeft = 0;
uint8_t rawRight = 0;
int16_t hostSteer = 0;
bool hostSteerRaw = false;
int16_t rawSteer = 0;
uint32_t hostCmdMs = 0;
bool hostSeen = false;

// Ramped speeds actually being sent, 0..1000.
int16_t currentLeft = 0;
int16_t currentRight = 0;
uint32_t lastRampMs = 0;

uint8_t outPwmLeft = 0;
uint8_t outPwmRight = 0;
bool outBrake = true;

// Steering state.
SteerCal cal;
bool calOk = false;
uint16_t potRaw = 0;
int16_t steerPos = 0;
int16_t steerTarget = 0;
const char *steerState = "OFF";
uint32_t steerFaultUntil = 0;
uint16_t stallRefPot = 0;
uint32_t stallRefMs = 0;
uint32_t lastSteerMs = 0;

char lineBuf[40];
uint8_t lineLen = 0;
uint32_t lastStatusMs = 0;

void isrThrottle() {
  uint32_t now = micros();
  if (digitalRead(PIN_RC_THROTTLE)) {
    throttleRiseUs = now;
  } else {
    uint32_t width = now - throttleRiseUs;
    if (width >= 800 && width <= 2200) {
      throttlePulseUs = width;
      throttleSeenMs = millis();
    }
  }
}

void isrMode() {
  uint32_t now = micros();
  if (digitalRead(PIN_RC_MODE)) {
    modeRiseUs = now;
  } else {
    uint32_t width = now - modeRiseUs;
    if (width >= 800 && width <= 2200) {
      modePulseUs = width;
      modeSeenMs = millis();
    }
  }
}

// CH1 on D4 (PD4): pin-change interrupt; only D4 is enabled in this group.
ISR(PCINT2_vect) {
  uint32_t now = micros();
  if (PIND & _BV(PIND4)) {
    steerRiseUs = now;
  } else {
    uint32_t width = now - steerRiseUs;
    if (width >= 800 && width <= 2200) {
      steerPulseUs = width;
      steerSeenMs = millis();
    }
  }
}

RcSnapshot readRc(uint32_t nowMs) {
  noInterrupts();
  uint16_t thr = throttlePulseUs;
  uint16_t mode = modePulseUs;
  uint16_t steer = steerPulseUs;
  uint32_t thrMs = throttleSeenMs;
  uint32_t modeMs = modeSeenMs;
  uint32_t steerMs = steerSeenMs;
  interrupts();

  RcSnapshot rc;
  rc.throttleUs = thr;
  rc.modeUs = mode;
  rc.steerUs = steer;
  rc.fresh = thr != 0 && mode != 0 &&
             nowMs - thrMs < RC_TIMEOUT_MS && nowMs - modeMs < RC_TIMEOUT_MS;
  rc.steerFresh = steer != 0 && nowMs - steerMs < RC_TIMEOUT_MS;
  return rc;
}

Mode decideMode(const RcSnapshot &rc) {
  if (!rc.fresh) return REQUIRE_RC ? MODE_NO_RC : MODE_AUTO;
  return rc.modeUs > RC_AUTO_ABOVE_US ? MODE_AUTO : MODE_MANUAL;
}

// Brake and F/R wires are pulled up inside the controller: drive LOW to
// activate, float (INPUT) to release.
void setActiveLow(uint8_t pin, bool active) {
  if (active) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
  } else {
    pinMode(pin, INPUT);
  }
}

uint8_t speedToPwm(int16_t speed) {
  if (speed <= 0) return PWM_IDLE;
  if (speed > 1000) speed = 1000;
  return PWM_START + (uint8_t)((uint32_t)(PWM_MAX - PWM_START) * speed / 1000);
}

// ---------------- Steering ----------------

void loadCal() {
  EEPROM.get(CAL_ADDR, cal);
  calOk = cal.magic == CAL_MAGIC && cal.left != cal.right &&
          ((cal.left < cal.center && cal.center < cal.right) ||
           (cal.right < cal.center && cal.center < cal.left));
}

void saveCal() {
  cal.magic = CAL_MAGIC;
  EEPROM.put(CAL_ADDR, cal);
  loadCal();
}

uint16_t readPot() {
  uint16_t sum = 0;
  for (uint8_t i = 0; i < 4; i++) sum += analogRead(PIN_STEER_POT);
  return sum / 4;
}

// Pot reading -> -1000 (full left) .. 0 (straight) .. 1000 (full right),
// whichever way round the potentiometer is fitted.
int16_t potToPos(uint16_t raw) {
  long d = (long)raw - cal.center;
  long toLeft = (long)cal.left - cal.center;
  long toRight = (long)cal.right - cal.center;
  long p = (d * toLeft > 0) ? -1000L * d / toLeft : 1000L * d / toRight;
  return (int16_t)constrain(p, -1100L, 1100L);
}

// Battery voltage in millivolts (0 when nothing is connected to the pin).
// An unconnected pin floats and can read any voltage, so first test it with the
// internal pull-up: the divider's 10k to GND drags the pin well down, a bare pin
// reads near 5 V.
uint16_t batteryMv(uint8_t pin) {
  pinMode(pin, INPUT_PULLUP);
  analogRead(pin);                       // settle the ADC on this pin
  bool unconnected = analogRead(pin) > 1000;
  pinMode(pin, INPUT);
  if (unconnected) return 0;
  analogRead(pin);
  uint16_t sum = 0;
  for (uint8_t i = 0; i < 4; i++) sum += analogRead(pin);
  float volts = sum / 4.0 * BATT_ADC_REF_V / 1023.0 * BATT_DIVIDER;
  return volts < 3.0 ? 0 : (uint16_t)(volts * 1000.0);
}

bool limitLeft() { return digitalRead(PIN_LIMIT_LEFT) == LOW; }
bool limitRight() { return digitalRead(PIN_LIMIT_RIGHT) == LOW; }

void steerOff() {
  analogWrite(PIN_STEER_RPWM, 0);
  analogWrite(PIN_STEER_LPWM, 0);
  digitalWrite(PIN_STEER_ENABLE, LOW);
  // The stall timer only runs while the motor is driven.
  stallRefPot = potRaw;
  stallRefMs = millis();
}

// Drive the motor; pwm > 0 means RPWM. Stops (and holds off for a while) if the
// pot does not move although the motor is driven: the gearbox is at an end stop
// or jammed, and a toy motor burns out quickly when stalled.
void steerMotorRaw(int16_t pwm, uint32_t nowMs) {
  if (pwm == 0) {
    steerOff();
    return;
  }
  if (abs((int16_t)potRaw - (int16_t)stallRefPot) > 5) {
    stallRefPot = potRaw;
    stallRefMs = nowMs;
  } else if (nowMs - stallRefMs > STEER_STALL_MS) {
    steerFaultUntil = nowMs + STEER_FAULT_HOLD_MS;
    steerState = "STALL";
    steerOff();
    return;
  }
  digitalWrite(PIN_STEER_ENABLE, HIGH);
  analogWrite(PIN_STEER_RPWM, pwm > 0 ? pwm : 0);
  analogWrite(PIN_STEER_LPWM, pwm < 0 ? -pwm : 0);
}

// pwm > 0 turns the wheels right. Limit switches block further travel.
void steerTowards(int16_t pwm, uint32_t nowMs) {
  if (pwm > 0 && limitRight()) pwm = 0;
  if (pwm < 0 && limitLeft()) pwm = 0;
  steerMotorRaw(cal.invert ? -pwm : pwm, nowMs);
}

int16_t rcSteerTarget(const RcSnapshot &rc) {
  if (!rc.steerFresh) return 0;
  int16_t d = (int16_t)rc.steerUs - (int16_t)RC_STEER_CENTER_US;
  if (abs(d) < (int16_t)RC_STEER_DEADBAND_US) return 0;
  return (int16_t)constrain(1000L * d / (long)RC_STEER_SPAN_US, -1000L, 1000L);
}

void updateSteering(Mode mode, const RcSnapshot &rc, bool hostOk, uint32_t nowMs) {
  if (nowMs - lastSteerMs < 10) return;
  lastSteerMs = nowMs;
  potRaw = readPot();
  steerPos = calOk ? potToPos(potRaw) : 0;

  if (!STEERING_INSTALLED) {
    steerState = "NONE";
    steerOff();
    return;
  }
  if (mode == MODE_AUTO && hostOk && hostSteerRaw) {   // calibration tool
    steerState = "RAW";
    if (nowMs < steerFaultUntil) { steerState = "STALL"; steerOff(); return; }
    steerMotorRaw(rawSteer, nowMs);
    return;
  }
  if (!calOk) { steerState = "NOCAL"; steerOff(); return; }
  if (potRaw < POT_MIN_VALID || potRaw > POT_MAX_VALID) { steerState = "POT"; steerOff(); return; }
  if (nowMs < steerFaultUntil) { steerState = "STALL"; steerOff(); return; }
  if (mode == MODE_NO_RC) { steerState = "OFF"; steerOff(); return; }

  int16_t target = mode == MODE_MANUAL ? rcSteerTarget(rc) : (hostOk ? hostSteer : 0);
  steerTarget = constrain(target, -STEER_TARGET_LIMIT, STEER_TARGET_LIMIT);
  steerState = "OK";

  int16_t err = steerTarget - steerPos;
  int16_t pwm = 0;
  if (abs(err) > STEER_DEADBAND) {
    int16_t mag = abs(err) >= STEER_SLOW_ZONE
        ? STEER_PWM_MAX
        : STEER_PWM_MIN + (int16_t)((long)(STEER_PWM_MAX - STEER_PWM_MIN) * abs(err) / STEER_SLOW_ZONE);
    pwm = err > 0 ? mag : -mag;
  }
  steerTowards(pwm, nowMs);
}

// ---------------- Serial ----------------

uint8_t parseInts(const char *s, long *out, uint8_t maxCount) {
  uint8_t n = 0;
  while (n < maxCount) {
    char *end;
    out[n] = strtol(s, &end, 10);
    if (end == s) return 0;
    n++;
    s = end;
    if (*s == '\0') return n;
    if (*s != ',') return 0;
    s++;
  }
  return *s == '\0' ? n : 0;
}

void printConfig() {
  Serial.print(F("CFG,pwm_start=")); Serial.print(PWM_START);
  Serial.print(F(",pwm_max=")); Serial.print(PWM_MAX);
  Serial.print(F(",raw_limit=")); Serial.print(PWM_RAW_LIMIT);
  Serial.print(F(",require_rc=")); Serial.print(REQUIRE_RC);
  Serial.print(F(",host_timeout_ms=")); Serial.print(HOST_TIMEOUT_MS);
  Serial.print(F(",steering=")); Serial.print(STEERING_INSTALLED);
  Serial.print(F(",cal_ok=")); Serial.print(calOk);
  Serial.print(F(",cal_left=")); Serial.print(cal.left);
  Serial.print(F(",cal_center=")); Serial.print(cal.center);
  Serial.print(F(",cal_right=")); Serial.print(cal.right);
  Serial.print(F(",cal_invert=")); Serial.println(cal.invert);
}

void handleLine(const char *s) {
  long v[4];
  uint8_t n;
  if (s[0] == 'D' && s[1] == ',' && (n = parseInts(s + 2, v, 4)) >= 3) {
    hostLeft = constrain(v[0], 0, 1000);
    hostRight = constrain(v[1], 0, 1000);
    hostBrake = v[2] != 0;
    hostSteer = n == 4 ? constrain(v[3], -1000, 1000) : 0;
    hostRaw = false;
    hostSteerRaw = false;
    hostCmdMs = millis();
    hostSeen = true;
  } else if (s[0] == 'R' && s[1] == ',' && parseInts(s + 2, v, 2) == 2) {
    rawLeft = constrain(v[0], 0, PWM_RAW_LIMIT);
    rawRight = constrain(v[1], 0, PWM_RAW_LIMIT);
    hostRaw = true;
    hostSteerRaw = false;
    hostCmdMs = millis();
    hostSeen = true;
  } else if (s[0] == 'M' && s[1] == ',' && parseInts(s + 2, v, 1) == 1) {
    rawSteer = constrain(v[0], -RAW_STEER_LIMIT, RAW_STEER_LIMIT);
    hostSteerRaw = true;
    hostRaw = false;
    hostLeft = hostRight = 0;    // car held still while calibrating
    hostBrake = true;
    hostCmdMs = millis();
    hostSeen = true;
  } else if (s[0] == 'K' && s[1] == ',') {
    char which = s[2];
    if (which == 'L') { cal.left = potRaw; saveCal(); }
    else if (which == 'C') { cal.center = potRaw; saveCal(); }
    else if (which == 'R') { cal.right = potRaw; saveCal(); }
    else if (which == 'I' && s[3] == ',') { cal.invert = s[4] == '1'; saveCal(); }
    else if (which == 'X') { cal.magic = 0; EEPROM.put(CAL_ADDR, cal); loadCal(); }
    printConfig();
  } else if (s[0] == '?') {
    printConfig();
  }
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (lineLen > 0) {
        lineBuf[lineLen] = '\0';
        handleLine(lineBuf);
        lineLen = 0;
      }
    } else if (lineLen < sizeof(lineBuf) - 1) {
      lineBuf[lineLen++] = c;
    } else {
      lineLen = 0;  // overlong line: drop it
    }
  }
}

// Speed drops take effect at once; rises are limited to RAMP_UP_PER_10MS.
void rampTowards(int16_t targetLeft, int16_t targetRight, uint32_t nowMs) {
  if (targetLeft < currentLeft) currentLeft = targetLeft;
  if (targetRight < currentRight) currentRight = targetRight;
  while (nowMs - lastRampMs >= 10) {
    lastRampMs += 10;
    currentLeft = min(targetLeft, (int16_t)(currentLeft + RAMP_UP_PER_10MS));
    currentRight = min(targetRight, (int16_t)(currentRight + RAMP_UP_PER_10MS));
  }
}

const char *modeName(Mode mode) {
  switch (mode) {
    case MODE_MANUAL: return "MANUAL";
    case MODE_AUTO: return "AUTO";
    default: return "NO_RC";
  }
}

void updateLed(Mode mode, uint32_t nowMs) {
  bool on;
  if (mode == MODE_AUTO) on = true;
  else if (mode == MODE_MANUAL) on = (nowMs / 500) % 2;
  else on = (nowMs / 100) % 2;
  digitalWrite(PIN_LED, on);
}

void setup() {
  // Throttles to zero first: the controllers refuse to start with throttle applied.
  pinMode(PIN_THROTTLE_LEFT, OUTPUT);
  pinMode(PIN_THROTTLE_RIGHT, OUTPUT);
  analogWrite(PIN_THROTTLE_LEFT, PWM_IDLE);
  analogWrite(PIN_THROTTLE_RIGHT, PWM_IDLE);
  setActiveLow(PIN_BRAKE_LEFT, true);
  setActiveLow(PIN_BRAKE_RIGHT, true);
  setActiveLow(PIN_DIR_LEFT, INVERT_LEFT);
  setActiveLow(PIN_DIR_RIGHT, INVERT_RIGHT);
  pinMode(PIN_LED, OUTPUT);

  pinMode(PIN_STEER_RPWM, OUTPUT);
  pinMode(PIN_STEER_LPWM, OUTPUT);
  pinMode(PIN_STEER_ENABLE, OUTPUT);
  steerOff();
  pinMode(PIN_LIMIT_LEFT, INPUT_PULLUP);
  pinMode(PIN_LIMIT_RIGHT, INPUT_PULLUP);
  loadCal();

  pinMode(PIN_RC_THROTTLE, INPUT);
  pinMode(PIN_RC_MODE, INPUT);
  pinMode(PIN_RC_STEER, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_RC_THROTTLE), isrThrottle, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_RC_MODE), isrMode, CHANGE);
  PCICR |= _BV(PCIE2);         // pin-change interrupts for D0-D7...
  PCMSK2 = _BV(PCINT20);       // ...but only D4 (CH1)

  Serial.begin(115200);
  Serial.println(F("NAVYA READY v2"));
  printConfig();
  lastRampMs = millis();
}

void loop() {
  readSerial();
  uint32_t nowMs = millis();
  RcSnapshot rc = readRc(nowMs);
  Mode mode = decideMode(rc);
  bool hostOk = hostSeen && nowMs - hostCmdMs < HOST_TIMEOUT_MS;

  int16_t targetLeft = 0;
  int16_t targetRight = 0;
  bool brake = true;
  bool raw = false;

  if (mode == MODE_MANUAL) {
    if (rc.throttleUs >= RC_FORWARD_FROM_US) {
      uint16_t us = constrain(rc.throttleUs, RC_FORWARD_FROM_US, RC_FORWARD_FULL_US);
      targetLeft = targetRight = map(us, RC_FORWARD_FROM_US, RC_FORWARD_FULL_US, 0, 1000);
      brake = false;
    } else if (rc.throttleUs > RC_STOP_BELOW_US) {
      brake = false;  // stick centred: coast
    }
  } else if (mode == MODE_AUTO) {
    bool operatorStop = rc.fresh && rc.throttleUs < RC_STOP_BELOW_US;
    if (!operatorStop && hostOk && !hostSteerRaw) {
      if (hostRaw) {
        raw = true;
        brake = false;
      } else {
        targetLeft = hostLeft;
        targetRight = hostRight;
        brake = hostBrake;
      }
    }
  }

  if (brake) targetLeft = targetRight = 0;

  if (raw) {
    currentLeft = currentRight = 0;
    lastRampMs = nowMs;
    outPwmLeft = rawLeft;
    outPwmRight = rawRight;
  } else {
    rampTowards(targetLeft, targetRight, nowMs);
    outPwmLeft = speedToPwm(currentLeft);
    outPwmRight = speedToPwm(currentRight);
  }
  outBrake = brake;

  analogWrite(PIN_THROTTLE_LEFT, outPwmLeft);
  analogWrite(PIN_THROTTLE_RIGHT, outPwmRight);
  setActiveLow(PIN_BRAKE_LEFT, outBrake);
  setActiveLow(PIN_BRAKE_RIGHT, outBrake);
  updateSteering(mode, rc, hostOk, nowMs);
  updateLed(mode, nowMs);

  if (nowMs - lastStatusMs >= STATUS_PERIOD_MS) {
    lastStatusMs = nowMs;
    Serial.print(F("S,"));
    Serial.print(modeName(mode)); Serial.print(',');
    Serial.print(rc.throttleUs); Serial.print(',');
    Serial.print(rc.modeUs); Serial.print(',');
    Serial.print(hostOk); Serial.print(',');
    Serial.print(outPwmLeft); Serial.print(',');
    Serial.print(outPwmRight); Serial.print(',');
    Serial.print(outBrake); Serial.print(',');
    Serial.print(rc.steerUs); Serial.print(',');
    Serial.print(steerTarget); Serial.print(',');
    Serial.print(steerPos); Serial.print(',');
    Serial.print(potRaw); Serial.print(',');
    Serial.print(limitLeft()); Serial.print(',');
    Serial.print(limitRight()); Serial.print(',');
    Serial.print(steerState); Serial.print(',');
    Serial.print(batteryMv(PIN_BATT_LEFT)); Serial.print(',');
    Serial.println(batteryMv(PIN_BATT_RIGHT));
  }
}
