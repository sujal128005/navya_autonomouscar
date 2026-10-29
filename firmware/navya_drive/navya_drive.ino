/*
  Navya drive firmware - Arduino Uno

  Drives the two rear BLDC hub motors through their YL-12 controllers by
  standing in for the hand throttle (PWM on the throttle signal wire).

  Modes, picked by the FlySky CH5 switch/knob:
    MANUAL  - right stick (CH2) up = forward, stick back = brake.
    AUTO    - the laptop autopilot drives over USB serial.
              Pulling CH2 back still stops the car (operator override).
    NO_RC   - no receiver signal: motors off, brakes on.

  The car also stops if the laptop goes quiet for HOST_TIMEOUT_MS.

  Serial protocol, 115200 baud, one command per line:
    D,<left>,<right>,<brake>   speed 0..1000 per wheel, brake 0/1
    R,<pwmLeft>,<pwmRight>     raw throttle PWM, for calibration only
    ?                          print the settings below
  Every STATUS_PERIOD_MS the Uno replies:
    S,<mode>,<ch2_us>,<ch5_us>,<host_ok>,<pwmLeft>,<pwmRight>,<brake>
*/

// ---------------- Pins ----------------
const uint8_t PIN_RC_MODE = 2;         // receiver CH5 signal (interrupt pin)
const uint8_t PIN_RC_THROTTLE = 3;     // receiver CH2 signal (interrupt pin)
const uint8_t PIN_BRAKE_LEFT = 5;      // controller brake wire (optional, active low)
const uint8_t PIN_BRAKE_RIGHT = 6;
const uint8_t PIN_DIR_RIGHT = 7;       // controller F/R silver wire
const uint8_t PIN_DIR_LEFT = 8;
const uint8_t PIN_THROTTLE_LEFT = 9;   // controller throttle purple wire
const uint8_t PIN_THROTTLE_RIGHT = 10;
const uint8_t PIN_LED = 13;

// ---------------- Throttle calibration ----------------
// Find PWM_START with: python throttle_test.py --sweep (wheels off the ground)
const uint8_t PWM_IDLE = 0;            // throttle output when stopped
const uint8_t PWM_START = 75;          // lowest PWM at which the wheels turn (bench: ~75-78)
const uint8_t PWM_MAX = 130;           // PWM sent for speed 1000 (this is the speed cap)
const uint8_t PWM_RAW_LIMIT = 160;     // ceiling for R, calibration commands
const bool INVERT_LEFT = false;        // true = drive this wheel's F/R wire low
const bool INVERT_RIGHT = false;
const uint16_t RAMP_UP_PER_10MS = 5;   // speed units gained per 10 ms (0 -> 1000 in 2 s)

// ---------------- Radio ----------------
const bool REQUIRE_RC = true;          // false = bench testing without the transmitter
// Our FS-CT6B: CH2 centre ~1464, full up ~1756 with SWA down (SWA up = dual rate, ~1644).
const uint16_t RC_AUTO_ABOVE_US = 1700;
const uint16_t RC_STOP_BELOW_US = 1400;
const uint16_t RC_FORWARD_FROM_US = 1520;
const uint16_t RC_FORWARD_FULL_US = 1740;
const uint16_t RC_TIMEOUT_MS = 100;

// ---------------- Laptop link ----------------
const uint16_t HOST_TIMEOUT_MS = 300;
const uint16_t STATUS_PERIOD_MS = 100;

enum Mode { MODE_NO_RC, MODE_MANUAL, MODE_AUTO };

struct RcSnapshot {
  uint16_t throttleUs;
  uint16_t modeUs;
  bool fresh;
};

// Written by the pin interrupts.
volatile uint32_t throttleRiseUs = 0;
volatile uint32_t modeRiseUs = 0;
volatile uint16_t throttlePulseUs = 0;
volatile uint16_t modePulseUs = 0;
volatile uint32_t throttleSeenMs = 0;
volatile uint32_t modeSeenMs = 0;

// Last laptop command.
int16_t hostLeft = 0;
int16_t hostRight = 0;
bool hostBrake = true;
bool hostRaw = false;
uint8_t rawLeft = 0;
uint8_t rawRight = 0;
uint32_t hostCmdMs = 0;
bool hostSeen = false;

// Ramped speeds actually being sent, 0..1000.
int16_t currentLeft = 0;
int16_t currentRight = 0;
uint32_t lastRampMs = 0;

uint8_t outPwmLeft = 0;
uint8_t outPwmRight = 0;
bool outBrake = true;

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

RcSnapshot readRc(uint32_t nowMs) {
  noInterrupts();
  uint16_t thr = throttlePulseUs;
  uint16_t mode = modePulseUs;
  uint32_t thrMs = throttleSeenMs;
  uint32_t modeMs = modeSeenMs;
  interrupts();

  RcSnapshot rc;
  rc.throttleUs = thr;
  rc.modeUs = mode;
  rc.fresh = thr != 0 && mode != 0 &&
             nowMs - thrMs < RC_TIMEOUT_MS && nowMs - modeMs < RC_TIMEOUT_MS;
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

bool parseInts(const char *s, long *out, uint8_t count) {
  for (uint8_t i = 0; i < count; i++) {
    char *end;
    out[i] = strtol(s, &end, 10);
    if (end == s) return false;
    s = end;
    if (i < count - 1) {
      if (*s != ',') return false;
      s++;
    }
  }
  return *s == '\0';
}

void printConfig() {
  Serial.print(F("CFG,pwm_start=")); Serial.print(PWM_START);
  Serial.print(F(",pwm_max=")); Serial.print(PWM_MAX);
  Serial.print(F(",raw_limit=")); Serial.print(PWM_RAW_LIMIT);
  Serial.print(F(",require_rc=")); Serial.print(REQUIRE_RC);
  Serial.print(F(",host_timeout_ms=")); Serial.println(HOST_TIMEOUT_MS);
}

void handleLine(const char *s) {
  long v[3];
  if (s[0] == 'D' && s[1] == ',' && parseInts(s + 2, v, 3)) {
    hostLeft = constrain(v[0], 0, 1000);
    hostRight = constrain(v[1], 0, 1000);
    hostBrake = v[2] != 0;
    hostRaw = false;
    hostCmdMs = millis();
    hostSeen = true;
  } else if (s[0] == 'R' && s[1] == ',' && parseInts(s + 2, v, 2)) {
    rawLeft = constrain(v[0], 0, PWM_RAW_LIMIT);
    rawRight = constrain(v[1], 0, PWM_RAW_LIMIT);
    hostRaw = true;
    hostCmdMs = millis();
    hostSeen = true;
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

  pinMode(PIN_RC_THROTTLE, INPUT);
  pinMode(PIN_RC_MODE, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_RC_THROTTLE), isrThrottle, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_RC_MODE), isrMode, CHANGE);

  Serial.begin(115200);
  Serial.println(F("NAVYA READY v1"));
  printConfig();
  lastRampMs = millis();
}

void loop() {
  readSerial();
  uint32_t nowMs = millis();
  RcSnapshot rc = readRc(nowMs);
  Mode mode = decideMode(rc);

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
    bool hostOk = hostSeen && nowMs - hostCmdMs < HOST_TIMEOUT_MS;
    if (!operatorStop && hostOk) {
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
  updateLed(mode, nowMs);

  if (nowMs - lastStatusMs >= STATUS_PERIOD_MS) {
    lastStatusMs = nowMs;
    bool hostOk = hostSeen && nowMs - hostCmdMs < HOST_TIMEOUT_MS;
    Serial.print(F("S,"));
    Serial.print(modeName(mode)); Serial.print(',');
    Serial.print(rc.throttleUs); Serial.print(',');
    Serial.print(rc.modeUs); Serial.print(',');
    Serial.print(hostOk); Serial.print(',');
    Serial.print(outPwmLeft); Serial.print(',');
    Serial.print(outPwmRight); Serial.print(',');
    Serial.println(outBrake);
  }
}
