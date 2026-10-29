"""Throttle bench test. PUT THE CAR ON BLOCKS so the rear wheels are off the ground.

The FlySky CH5 switch must be in AUTO (the firmware ignores the laptop otherwise),
and pulling the right stick back stops the wheels at any time.

    python throttle_test.py --sweep              # raw PWM 30..120: find PWM_START
    python throttle_test.py --pwm 70 --seconds 3 # hold one raw PWM value
    python throttle_test.py --speed 300          # use the calibrated 0..1000 scale
"""

import argparse
import sys
import time

from navya_link import NavyaLink

SEND_PERIOD_S = 0.05


def hold(link: NavyaLink, seconds: float, send):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        send()
        time.sleep(SEND_PERIOD_S)
    s = link.status
    print(f"    mode {s.mode}, pwm out {s.pwm_left}/{s.pwm_right}, brake {int(s.brake)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sweep", action="store_true", help="step raw PWM from 30 to 120")
    group.add_argument("--pwm", type=int, help="raw PWM 0..160 on both wheels")
    group.add_argument("--speed", type=int, help="speed 0..1000 on both wheels")
    parser.add_argument("--side", choices=["both", "left", "right"], default="both")
    parser.add_argument("--seconds", type=float, default=3.0)
    args = parser.parse_args()

    def split(value):
        return (value if args.side != "right" else 0, value if args.side != "left" else 0)

    link = NavyaLink(args.port)
    try:
        if not link.wait_ready():
            print("No reply from the Arduino. Is navya_drive.ino flashed?")
            return 1
        time.sleep(0.3)
        if link.status.mode != "AUTO":
            print(f"Arduino mode is {link.status.mode}. Flip the CH5 switch to AUTO, then run again.")
            return 1

        if args.sweep:
            for pwm in range(30, 125, 5):
                print(f"raw PWM {pwm}  - note the first value where the wheels turn")
                hold(link, 1.5, lambda: link.raw(*split(pwm)))
        elif args.pwm is not None:
            print(f"raw PWM {args.pwm} for {args.seconds}s")
            hold(link, args.seconds, lambda: link.raw(*split(args.pwm)))
        else:
            print(f"speed {args.speed} for {args.seconds}s")
            hold(link, args.seconds, lambda: link.drive(*split(args.speed), False))
    except KeyboardInterrupt:
        pass
    finally:
        link.close()
        print("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
