"""Navya demo autopilot: drive straight, slow and stop for obstacles, resume when clear.

Run on the laptop riding in the car, with the D435i and the Arduino plugged in:
    python navya_autopilot.py --show          # drive, with a live depth window
    python navya_autopilot.py --dry-run --show  # camera only, no Arduino needed

Keys (terminal or depth window): SPACE = pause/unpause (pause = stop), Q = quit.
The car only moves when the FlySky CH5 switch is in AUTO. Pull the right
stick back at any time to stop it.
"""

import argparse
import os
import sys
import time

import numpy as np
import pyrealsense2 as rs

import config
from navya_link import NavyaLink
from obstacle import CorridorDetector, Intrinsics
from speed_planner import SpeedPlanner, apply_trim

FRAME_TIMEOUT_MS = 500

if os.name == "nt":
    import msvcrt

    def read_key() -> str | None:
        if msvcrt.kbhit():
            return msvcrt.getwch().lower()
        return None
else:
    def read_key() -> str | None:
        return None


def start_camera():
    pipeline = rs.pipeline()
    cfg = rs.config()
    cfg.enable_stream(rs.stream.depth, config.DEPTH_WIDTH, config.DEPTH_HEIGHT,
                      rs.format.z16, config.DEPTH_FPS)
    profile = pipeline.start(cfg)
    device = profile.get_device()
    depth_scale = device.first_depth_sensor().get_depth_scale()
    i = profile.get_stream(rs.stream.depth).as_video_stream_profile().get_intrinsics()
    intr = Intrinsics(i.width, i.height, i.fx, i.fy, i.ppx, i.ppy)
    usb = device.get_info(rs.camera_info.usb_type_descriptor) \
        if device.supports(rs.camera_info.usb_type_descriptor) else "?"
    print(f"Camera: {device.get_info(rs.camera_info.name)}, USB {usb}, "
          f"{intr.width}x{intr.height}@{config.DEPTH_FPS}")
    if usb.startswith("2"):
        print("WARNING: camera is on USB 2. Use a blue USB 3 port/cable, or lower "
              "DEPTH_WIDTH/HEIGHT to 424x240 in config.py.")
    return pipeline, intr, depth_scale


def draw(depth_raw, measurement, stride, lines):
    import cv2

    vis = cv2.applyColorMap(cv2.convertScaleAbs(depth_raw, alpha=0.04), cv2.COLORMAP_JET)
    mask = np.kron(measurement.mask, np.ones((stride, stride), dtype=bool))
    mask = mask[:vis.shape[0], :vis.shape[1]]
    vis[mask] = (0.4 * vis[mask] + 0.6 * np.array([255, 255, 255])).astype(np.uint8)
    for n, text in enumerate(lines):
        cv2.putText(vis, text, (10, 28 + 28 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
        cv2.putText(vis, text, (10, 28 + 28 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.imshow("Navya", vis)
    key = cv2.waitKey(1) & 0xFF
    return chr(key).lower() if key != 255 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="Arduino serial port, e.g. COM5 (default: auto-detect)")
    parser.add_argument("--dry-run", action="store_true", help="camera and planner only; never talks to the Arduino")
    parser.add_argument("--show", action="store_true", help="show the depth view with the corridor highlighted")
    args = parser.parse_args()

    link = None
    if not args.dry_run:
        link = NavyaLink(args.port)
        print(f"Arduino on {link.port}, waiting for it to boot...")
        if not link.wait_ready():
            print("No reply from the Arduino. Is navya_drive.ino flashed? Last line:", repr(link.last_line))
            link.close()
            return 1

    pipeline, intr, depth_scale = start_camera()
    detector = CorridorDetector(intr, depth_scale)
    planner = SpeedPlanner()
    paused = False
    last_print = 0.0
    last_state = None
    frames_seen = 0
    fps_t0 = time.monotonic()
    fps = 0.0

    print("Running. SPACE = pause, Q = quit, Ctrl+C = quit.")
    try:
        while True:
            try:
                frames = pipeline.wait_for_frames(FRAME_TIMEOUT_MS)
                depth_frame = frames.get_depth_frame()
            except RuntimeError:
                depth_frame = None
            now = time.monotonic()

            if not depth_frame:
                planner.reset()
                if link:
                    link.stop()
                print("No depth frame from the camera - stopped.")
                continue

            depth_raw = np.asanyarray(depth_frame.get_data())
            m = detector.measure(depth_raw)

            mode = link.status.mode if link else "DRY_RUN"
            if link and link.status_age_s() > 0.5:
                mode = "NO_LINK"
            driving = (mode == "AUTO" or args.dry_run) and not paused
            if driving:
                speed, brake = planner.update(m.distance_m, now)
            else:
                planner.reset()
                speed, brake = 0, True
            left, right = apply_trim(speed)
            if link:
                link.drive(left, right, brake)

            frames_seen += 1
            if now - fps_t0 >= 1.0:
                fps = frames_seen / (now - fps_t0)
                frames_seen, fps_t0 = 0, now

            dist = "BLIND" if m.blind else ("clear" if m.distance_m is None else f"{m.distance_m:.2f} m")
            state = "PAUSED" if paused else (planner.state if driving else "IDLE")
            summary = f"{mode:8} {state:9} obstacle {dist:9} speed {left}/{right}" + (" BRAKE" if brake else "")
            if state != last_state or now - last_print > 0.5:
                pwm = f" pwm {link.status.pwm_left}/{link.status.pwm_right}" if link else ""
                print(f"{summary}{pwm}  ({m.points} pts, {fps:.0f} fps)")
                last_print, last_state = now, state

            key = read_key()
            if args.show:
                key = draw(depth_raw, m, detector.stride, [f"{mode} {state}", f"obstacle {dist}",
                                                          f"speed {left}/{right}{' BRAKE' if brake else ''}"]) or key
            if key == " ":
                paused = not paused
                print("PAUSED - car held stopped" if paused else "Unpaused")
            elif key == "q":
                break
    except KeyboardInterrupt:
        pass
    finally:
        if link:
            link.close()
        pipeline.stop()
        print("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
