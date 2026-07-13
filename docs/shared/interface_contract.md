# Interface Contract (FROZEN) - Pi <-> Arduino

Transport: USB serial, 115200 baud (confirm in Phase 1/3)

Pi sends (1 char):
  G = go straight at set speed
  S = stop
  L = nudge left   (RESERVED - future turning, not used in PoC)
  R = nudge right  (RESERVED - future turning, not used in PoC)

Arduino replies:
  OK    = command accepted
  ESTOP = emergency stop active, command ignored

Rule: neither member changes this without the other agreeing.
