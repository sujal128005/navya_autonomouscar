"""One steering pulse in one direction. Usage: pulse1.py PORT PWM SECONDS (PWM may be negative)."""
import sys, time
sys.path.insert(0, r"C:\Users\connt\dev\navya_autonomouscar\autopilot")
from navya_link import NavyaLink

port, pwm, secs = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
assert abs(pwm) <= 255 and secs <= 1.4     # firmware stall cut-off is 1.5 s
link = NavyaLink(port)
try:
    assert link.wait_ready(), "no reply from Arduino"
    time.sleep(0.5)
    s = link.status
    print("start:", s.mode, "state", s.steer_state)
    assert s.mode == "AUTO", "not in AUTO, nothing sent"
    end = time.monotonic() + secs
    states = set()
    while time.monotonic() < end:
        link.steer_raw(pwm)
        time.sleep(0.05)
        s = link.status
        states.add(s.steer_state)
        if s.mode != "AUTO":
            print("left AUTO, stopping"); break
    print(f"pulse {pwm:+d} for {secs}s: states {sorted(states)}")
finally:
    link.steer_raw(0)
    time.sleep(0.2)
    link.close()
print("done, motor off")
