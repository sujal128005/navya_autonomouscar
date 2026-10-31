"""Steering calibration for the toy steering motor (BTS7960 + potentiometer).

Run once after fitting the potentiometer, and again whenever it is moved:
    python steering_calibrate.py

Before you start:
  - firmware v2 uploaded (navya_drive.ino), Arduino IDE closed;
  - the toy's blue control board disconnected from the steering motor;
  - 12 V connected to the BTS7960 (through the fuse);
  - transmitter on, SWA down, CH5 in AUTO, right stick centred.
The rear wheels stay braked the whole time. Keep fingers away from the front wheels.
"""

import argparse
import os
import sys
import time

from navya_link import NavyaLink

PULSE_PWMS = (120, 170, 220)   # tried in turn until the steering moves
SEND_PERIOD_S = 0.05
END_STILL_S = 0.6              # pot unchanged this long = reached the end stop
END_TIMEOUT_S = 8.0

if os.name == "nt":
    import msvcrt


def send_for(link: NavyaLink, pwm: int, seconds: float):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        link.steer_raw(pwm)
        time.sleep(SEND_PERIOD_S)
    link.steer_raw(0)


def ask(prompt: str, choices: str) -> str:
    while True:
        answer = input(prompt).strip().lower()[:1]
        if answer in choices:
            return answer


def drive_to_end(link: NavyaLink, pwm: int, side: str) -> int:
    """Drive until the limit switch for `side` closes or the pot stops moving."""
    last_pot, still_since = link.status.pot_raw, time.monotonic()
    start = time.monotonic()
    while time.monotonic() - start < END_TIMEOUT_S:
        link.steer_raw(pwm)
        time.sleep(SEND_PERIOD_S)
        s = link.status
        if (side == "left" and s.limit_left) or (side == "right" and s.limit_right):
            reason = "limit switch"
            break
        if s.steer_state == "STALL":
            reason = "stall cut-off"
            break
        if abs(s.pot_raw - last_pot) > 3:
            last_pot, still_since = s.pot_raw, time.monotonic()
        elif time.monotonic() - still_since > END_STILL_S:
            reason = "end stop"
            break
    else:
        reason = "timeout"
    link.steer_raw(0)
    time.sleep(0.3)
    print(f"  {side}: stopped by {reason}, pot = {link.status.pot_raw}")
    return link.status.pot_raw


def centre(link: NavyaLink, pwm_right: int, pot_left: int, pot_right: int) -> None:
    """Drive to the middle of the travel, then let the user nudge it straight."""
    middle = (pot_left + pot_right) // 2
    right_increases_pot = pot_right > pot_left
    for _ in range(80):
        pot = link.status.pot_raw
        if abs(pot - middle) <= 6:
            break
        need_right = (pot < middle) == right_increases_pot
        send_for(link, pwm_right if need_right else -pwm_right, 0.08)
        time.sleep(0.15)
    print("\nNow make the front wheels point exactly straight ahead.")
    print("  A = nudge left, D = nudge right, ENTER = this is straight")
    while True:
        if os.name == "nt":
            key = msvcrt.getwch().lower()
        else:
            key = (input("a/d/enter: ").strip().lower() or "\r")[:1]
        if key == "a":
            send_for(link, -pwm_right, 0.1)
        elif key == "d":
            send_for(link, pwm_right, 0.1)
        elif key in ("\r", "\n"):
            return
        time.sleep(0.2)
        print(f"  pot = {link.status.pot_raw}", end="\r")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port")
    args = parser.parse_args()

    link = NavyaLink(args.port)
    try:
        if not link.wait_ready():
            print("No reply from the Arduino. Is navya_drive.ino flashed? Is the Arduino IDE closed?")
            return 1
        time.sleep(0.5)
        s = link.status
        if s.steer_state == "-":
            print("This Arduino runs firmware v1. Upload firmware/navya_drive/navya_drive.ino (v2) first.")
            return 1
        if s.mode != "AUTO":
            print(f"Arduino mode is {s.mode}. Transmitter on, CH5 to AUTO, stick centred - then run again.")
            return 1
        print(f"Pot reads {s.pot_raw} (0-1023), limit switches L={int(s.limit_left)} R={int(s.limit_right)}")
        if not 15 <= s.pot_raw <= 1008:
            print("Pot reading is at the very end of its range: check the pot wiring (5V, GND, wiper to A0).")
            return 1

        print("\nStep 1/4: which way does the motor turn the wheels?")
        moved_pwm = None
        for pwm in PULSE_PWMS:
            before = link.status.pot_raw
            send_for(link, pwm, 0.4)
            time.sleep(0.4)
            if abs(link.status.pot_raw - before) > 8:
                moved_pwm = pwm
                break
            print(f"  no movement at PWM {pwm}, trying harder...")
        if moved_pwm is None:
            print("The steering did not move. Check: 12 V at the BTS7960, motor wires on M+/M-, "
                  "R_EN/L_EN to A3, RPWM/LPWM to D5/D6, and that the pot turns with the steering.")
            return 1
        turned = ask("Which way did the front wheels just turn? [l]eft / [r]ight: ", "lr")
        invert = turned == "l"
        link.steer_set_invert(invert)
        pwm_right = -moved_pwm if invert else moved_pwm   # raw PWM that turns the wheels right

        print("\nStep 2/4: finding full left and full right (the motor will stop by itself)...")
        input("  Press ENTER to start. ")
        pot_left = drive_to_end(link, -pwm_right, "left")
        link.steer_store("L")
        pot_right = drive_to_end(link, pwm_right, "right")
        link.steer_store("R")
        if abs(pot_right - pot_left) < 40:
            print("Full left and full right read almost the same: the pot is not turning with the steering.")
            return 1

        print("\nStep 3/4: centring...")
        centre(link, pwm_right, pot_left, pot_right)
        link.steer_store("C")
        time.sleep(0.5)

        print("\n\nStep 4/4: test - left, straight, right, straight")
        for target in (-600, 0, 600, 0):
            end = time.monotonic() + 2.0
            while time.monotonic() < end:
                link.drive(0, 0, True, target)
                time.sleep(SEND_PERIOD_S)
            s = link.status
            print(f"  asked {target:+5d}  ->  reached {s.steer_pos:+5d}   ({s.steer_state})")
        cfg = link.config
        print(f"\nSaved in the Arduino: left={cfg.get('cal_left')} centre={cfg.get('cal_center')} "
              f"right={cfg.get('cal_right')} invert={cfg.get('cal_invert')}")
        print("Last step by hand: measure the front-wheel angle at full lock (degrees) and set "
              "STEER_MAX_DEG in config.py.")
    except KeyboardInterrupt:
        pass
    finally:
        link.steer_raw(0)
        link.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
