"""LiDAR radar view: what the D500 sees all around the car (never moves the car).

    python lidar_view.py             # window on the laptop
    python lidar_view.py --phone     # also watch it from a phone
    python lidar_view.py --range 3   # zoom in: show 3 m around the car

Up is forward. The grey strip is the car's driving corridor; points inside it are
obstacles. To set LIDAR_ANGLE_OFFSET_DEG: put a box about 1 m straight ahead of the
car with nothing else close, and copy the "nearest" sensor angle into config.py.
Keys: Q = quit.
"""

import argparse
import sys
import time

import cv2
import numpy as np

import config
from keyboard_input import has_screen, read_key
from lidar import LidarReader, Scan, corridor_distance, nearest_by_side


def fmt(d: float | None) -> str:
    return "-" if d is None else f"{d:.2f} m"


def render_radar(scan: Scan | None, size: int = 480, range_m: float = 6.0) -> np.ndarray:
    img = np.full((size, size, 3), 25, np.uint8)
    c = size // 2
    scale = (size / 2 - 10) / range_m

    def px(x, y):   # car coordinates (x forward, y right) -> pixel
        return int(c + y * scale), int(c - x * scale)

    # Driving corridor ahead of the bumper.
    half, setback, lateral = config.CORRIDOR_HALF_WIDTH_M, config.LIDAR_SETBACK_M, config.LIDAR_LATERAL_OFFSET_M
    cv2.rectangle(img, px(setback + config.DETECT_MAX_M, -half - lateral), px(setback, half - lateral),
                  (60, 60, 60), -1)
    for r in range(1, int(range_m) + 1):
        cv2.circle(img, (c, c), int(r * scale), (70, 70, 70), 1)
        cv2.putText(img, f"{r} m", (c + 3, c - int(r * scale) + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (140, 140, 140), 1)
    cv2.line(img, (c, 0), (c, size), (50, 50, 50), 1)
    cv2.line(img, (0, c), (size, c), (50, 50, 50), 1)
    cv2.fillPoly(img, [np.array([px(0.15, 0), px(-0.08, -0.08), px(-0.08, 0.08)])], (255, 255, 255))

    lines = ["LiDAR: no data"]
    if scan is not None:
        x, y = scan.points_xy()
        d = np.hypot(x, y)
        near = np.clip(d / 3.0, 0, 1)           # red close, green from 3 m
        for xi, yi, k in zip(x, y, near):
            if abs(xi) <= range_m and abs(yi) <= range_m:
                cv2.circle(img, px(xi, yi), 2, (0, int(255 * k), int(255 * (1 - k))), -1)
        path = corridor_distance(scan)
        if path is not None:
            cv2.line(img, px(setback + path, -half - lateral), px(setback + path, half - lateral), (0, 0, 255), 2)
        sides = nearest_by_side(scan)
        lines = [f"path {fmt(path)}   {scan.rpm / 60:.1f} turns/s",
                 "  ".join(f"{k} {fmt(v)}" for k, v in sides.items())]
        ok = scan.valid()
        if ok.any():
            i = np.flatnonzero(ok)[np.argmin(scan.distance_m[ok])]
            lines.append(f"nearest {scan.distance_m[i]:.2f} m at sensor angle {scan.angle_deg[i]:.0f} deg")
    for n, text in enumerate(lines):
        cv2.putText(img, text, (8, size - 12 - 20 * (len(lines) - 1 - n)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (255, 255, 255), 1)
    return img


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="LiDAR serial port, e.g. COM7 (default: find it)")
    parser.add_argument("--range", type=float, default=6.0, help="metres shown around the car")
    parser.add_argument("--phone", action="store_true", help="also serve the radar to a phone")
    parser.add_argument("--phone-port", type=int, default=8080)
    args = parser.parse_args()
    window = has_screen()
    if not window:
        print("No screen here: showing on the dashboard instead. Q = quit.")
        args.phone = True

    try:
        lidar = LidarReader(args.port)
    except RuntimeError as e:
        print(e)
        return 1
    print(f"LiDAR on {lidar.port}, waiting for the first turn...")
    if not lidar.wait_first():
        print("No scans. Is the sensor spinning? Check its power and the TX wire to the adapter.")
        lidar.close()
        return 1

    phone = None
    if args.phone:
        from phone_stream import PhoneStream
        phone = PhoneStream("Navya LiDAR", {"lidar": "LiDAR radar (up = forward)"}, port=args.phone_port)
        phone.print_addresses()

    print("Running. Q = quit." if not window else "Running. Q in the window = quit.")
    last_t, last_print = 0.0, 0.0
    try:
        while True:
            scan = lidar.latest()
            if scan.t != last_t:
                last_t = scan.t
                img = render_radar(scan, 640, args.range)
                if window:
                    cv2.imshow("Navya LiDAR", img)
                path, sides = corridor_distance(scan), nearest_by_side(scan)
                if phone:
                    phone.publish("lidar", img)
                    phone.set_status(mode="VIEW ONLY", path=fmt(path),
                                     around=", ".join(f"{k} {fmt(v)}" for k, v in sides.items()),
                                     speed=f"{scan.rpm / 60:.1f} turns/s")
                if time.monotonic() - last_print > 1:
                    last_print = time.monotonic()
                    print(f"path {fmt(path):8}  " + "  ".join(f"{k} {fmt(v):8}" for k, v in sides.items())
                          + f"  {scan.valid().sum()} points, {scan.rpm / 60:.1f} turns/s")
            if time.monotonic() - scan.t > 1:
                print("LiDAR stopped sending" + (f": {lidar.error}" if lidar.error else ""))
                break
            if window:
                if cv2.waitKey(20) & 0xFF in (ord("q"), ord("Q")):
                    break
            else:
                time.sleep(0.02)
                if read_key() == "q":
                    break
    except KeyboardInterrupt:
        pass
    finally:
        lidar.close()
        if phone:
            phone.close()
        if window:
            cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
