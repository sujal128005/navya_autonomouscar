"""Navya demo autopilot: drive straight, slow and stop for obstacles, resume when clear.

Run on the laptop riding in the car, with the D435i and the Arduino plugged in:
    python navya_autopilot.py --show            # drive, with a live depth window
    python navya_autopilot.py --phone           # drive, and watch it from a phone
    python navya_autopilot.py --phone --vision  # + object detection: people, stop signs
    python navya_autopilot.py --phone --steer   # + lane following (steering calibrated first)
    python navya_autopilot.py --phone --lidar   # + LiDAR as a second obstacle sensor
    python navya_autopilot.py --dry-run --show  # camera only, no Arduino needed

Keys (terminal or depth window): SPACE = pause/unpause (pause = stop), Q = quit.
The car only moves when the FlySky CH5 switch is in AUTO. Pull the right
stick back at any time to stop it.
"""

import argparse
import os
import sys
import time

import cv2
import numpy as np
import pyrealsense2 as rs

import config
from navya_link import NavyaLink
from obstacle import CorridorDetector, Intrinsics
from phone_stream import PhoneStream
import live_settings
from ask_navya import AskNavya
from battery import BatteryGuard, describe
from lane import WallLaneFinder
from lane_follow import LaneFollower
from speed_planner import SpeedPlanner, apply_trim
from trip_recorder import TripRecorder

FRAME_TIMEOUT_MS = 500
PHONE_COLOR_FPS = 15

if os.name == "nt":
    import msvcrt

    def read_key() -> str | None:
        if msvcrt.kbhit():
            return msvcrt.getwch().lower()
        return None
else:
    def read_key() -> str | None:
        return None


def start_camera(with_color=False, record_to=None, replay_from=None):
    """Depth stream, plus colour (phone view / object detection / recording) if asked and the USB
    link manages it. record_to: also save everything to a .bag file. replay_from: play a .bag
    instead of the live camera.
    Returns (pipeline, depth intrinsics, depth scale, colour intrinsics or None)."""
    if replay_from:
        pipeline = rs.pipeline()
        cfg = rs.config()
        cfg.enable_device_from_file(str(replay_from), repeat_playback=False)
        profile = pipeline.start(cfg)
        color = any(s.stream_type() == rs.stream.color for s in profile.get_streams())
    for color in ([] if replay_from else [True, False] if with_color else [False]):
        pipeline = rs.pipeline()
        cfg = rs.config()
        cfg.enable_stream(rs.stream.depth, config.DEPTH_WIDTH, config.DEPTH_HEIGHT,
                          rs.format.z16, config.DEPTH_FPS)
        if color:
            cfg.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, PHONE_COLOR_FPS)
        if record_to:
            cfg.enable_record_to_file(str(record_to))
        try:
            profile = pipeline.start(cfg)
            break
        except RuntimeError as e:
            if not color:
                raise
            print(f"Colour camera could not start alongside depth ({e}); "
                  "no camera picture on the phone and no object detection.")
    if not replay_from:
        try:
            pipeline.wait_for_frames(3000)
        except RuntimeError:
            # After re-plugging, the D435i can get stuck sending nothing; a reset frees it.
            print("Camera sends no frames - resetting it (about 6 s)...")
            pipeline.stop()
            profile.get_device().hardware_reset()
            time.sleep(6)
            pipeline = rs.pipeline()
            profile = pipeline.start(cfg)
            pipeline.wait_for_frames(3000)
    device = profile.get_device()
    depth_scale = device.first_depth_sensor().get_depth_scale()
    i = profile.get_stream(rs.stream.depth).as_video_stream_profile().get_intrinsics()
    intr = Intrinsics(i.width, i.height, i.fx, i.fy, i.ppx, i.ppy)
    color_intr = None
    if color:
        c = profile.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()
        color_intr = Intrinsics(c.width, c.height, c.fx, c.fy, c.ppx, c.ppy)
    usb = device.get_info(rs.camera_info.usb_type_descriptor) \
        if device.supports(rs.camera_info.usb_type_descriptor) else "?"
    source = f"replay of {replay_from}" if replay_from else f"USB {usb}"
    print(f"Camera: {device.get_info(rs.camera_info.name)}, {source}, "
          f"{intr.width}x{intr.height}" + (" + colour" if color else ""))
    if usb.startswith("2") and not replay_from:
        print("WARNING: camera is on USB 2: it works, but depth + colour is near its limit. "
              "Use a USB 3 data cable (phone charger cables are USB 2).")
    return pipeline, intr, depth_scale, color_intr


def put_lines(img, lines):
    for n, text in enumerate(lines):
        cv2.putText(img, text, (10, 28 + 28 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
        cv2.putText(img, text, (10, 28 + 28 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return img


def depth_view(depth_raw, measurement, stride, lines):
    vis = cv2.applyColorMap(cv2.convertScaleAbs(depth_raw, alpha=0.04), cv2.COLORMAP_JET)
    mask = np.kron(measurement.mask, np.ones((stride, stride), dtype=bool))
    mask = mask[:vis.shape[0], :vis.shape[1]]
    vis[mask] = (0.4 * vis[mask] + 0.6 * np.array([255, 255, 255])).astype(np.uint8)
    return put_lines(vis, lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="Arduino serial port, e.g. COM5 (default: auto-detect)")
    parser.add_argument("--dry-run", action="store_true", help="camera and planner only; never talks to the Arduino")
    parser.add_argument("--show", action="store_true", help="show the depth view with the corridor highlighted")
    parser.add_argument("--phone", action="store_true", help="serve the camera, depth view and status to a phone")
    parser.add_argument("--phone-port", type=int, default=8080)
    parser.add_argument("--vision", action="store_true",
                        help="object detection: stop further from people, stop at stop signs")
    parser.add_argument("--record", action="store_true",
                        help="save camera + depth videos and telemetry (SD card if inserted)")
    parser.add_argument("--record-raw", action="store_true",
                        help="with --record: also save the full camera data (.bag, ~100 GB/hour) for --replay")
    parser.add_argument("--replay", metavar="BAG",
                        help="run on a recorded raw.bag instead of the camera (never drives the car)")
    parser.add_argument("--steer", action="store_true",
                        help="lane following: steer to the corridor centre (needs calibrated steering)")
    parser.add_argument("--lidar", action="store_true",
                        help="also stop for what the LiDAR sees in the path (D500 on the laptop's USB)")
    args = parser.parse_args()
    if args.replay:
        args.dry_run = True

    link = None
    if not args.dry_run:
        link = NavyaLink(args.port)
        print(f"Arduino on {link.port}, waiting for it to boot...")
        if not link.wait_ready():
            print("No reply from the Arduino. Is navya_drive.ino flashed? Last line:", repr(link.last_line))
            link.close()
            return 1

    lidar = None
    if args.lidar:
        from lidar import LidarReader, corridor_distance
        from lidar_view import render_radar
        try:
            lidar = LidarReader(skip=(link.port,) if link else ())
        except RuntimeError as e:
            print(e)
            if link:
                link.close()
            return 1
        print(f"LiDAR on {lidar.port}, waiting for the first turn...")
        if not lidar.wait_first():
            print("No scans from the LiDAR. Is it spinning? Check its power and wires.")
            lidar.close()
            if link:
                link.close()
            return 1

    phone = None
    if args.phone:
        views = {"camera": "Camera", "depth": "Depth (white = obstacle zone)"}
        if lidar:
            views["lidar"] = "LiDAR radar (up = forward)"
        phone = PhoneStream("Navya autopilot", views,
                            {"Pause (hold stopped)": "pause", "Resume": "resume"}, port=args.phone_port,
                            settings=live_settings.SETTINGS, settings_values=live_settings.values,
                            ask=True)
        phone.print_addresses()

    vision = rules = align = None
    if args.vision:
        from vision import ObjectDetector, draw
        from vision_rules import VisionRules, VisionWorker, summary
        print("Loading the YOLO model...")
        object_detector = ObjectDetector()

    recorder = TripRecorder() if args.record else None
    pipeline, intr, depth_scale, color_intr = start_camera(
        with_color=args.phone or args.vision or args.record,
        record_to=recorder.raw_path if recorder and args.record_raw else None,
        replay_from=args.replay)
    if args.vision and color_intr:
        vision = VisionWorker(object_detector, color_intr, depth_scale)
        rules = VisionRules()
        align = rs.align(rs.stream.color)
    detector = CorridorDetector(intr, depth_scale)
    planner = SpeedPlanner()
    guard = BatteryGuard()
    last_battery = ""
    note, note_at = "", 0.0
    asker = AskNavya() if phone else None
    walls = WallLaneFinder() if args.steer else None
    follower = LaneFollower() if args.steer else None
    if args.steer and link and link.status.steer_state in ("-", "NOCAL", "NONE"):
        print(f"WARNING: steering is not ready on the Arduino ({link.status.steer_state}); "
              "run steering_calibrate.py. The car will drive straight.")
    paused = False
    last_print = 0.0
    last_state = None
    last_depth_at = time.monotonic()
    phone_color = None
    radar, radar_t, lidar_lost = None, 0.0, False
    frames_seen = 0
    fps_t0 = time.monotonic()
    fps = 0.0

    print("Running. SPACE = pause, Q = quit, Ctrl+C = quit.")
    try:
        while True:
            try:
                frames = pipeline.wait_for_frames(3000 if args.replay else FRAME_TIMEOUT_MS)
            except RuntimeError:
                frames = None
                if args.replay:
                    print("End of the recording.")
                    break
            now = time.monotonic()

            color_frame = frames.get_color_frame() if frames and color_intr else None
            if color_frame:
                phone_color = np.array(color_frame.get_data())
                if vision and frames.get_depth_frame():
                    aligned_depth = align.process(frames).get_depth_frame()
                    if aligned_depth:
                        vision.submit(phone_color, np.array(aligned_depth.get_data()))
            depth_frame = frames.get_depth_frame() if frames else None
            if not depth_frame:
                # A colour-only frame set is normal; only a real gap in depth stops the car.
                if now - last_depth_at > FRAME_TIMEOUT_MS / 1000:
                    planner.reset()
                    if link:
                        link.stop()
                    print("No depth frame from the camera - stopped.")
                    last_depth_at = now
                continue
            last_depth_at = now

            depth_raw = np.asanyarray(depth_frame.get_data())
            m = detector.measure(depth_raw)

            lidar_dist, lidar_text = None, ""
            if lidar:
                scan = lidar.latest()
                lost = now - scan.t > config.LIDAR_MAX_AGE_S
                if lost != lidar_lost:
                    print("LiDAR STOPPED SENDING - car stopped" + (f" ({lidar.error})" if lidar.error else "")
                          if lost else "LiDAR back")
                lidar_lost = lost
                if not lost:
                    lidar_dist = corridor_distance(scan)
                lidar_text = "LOST" if lost else ("clear" if lidar_dist is None else f"{lidar_dist:.2f} m")
                if scan.t != radar_t:
                    radar, radar_t = render_radar(scan), scan.t

            mode = link.status.mode if link else "DRY_RUN"
            if link and link.status_age_s() > 0.5:
                mode = "NO_LINK"
            driving = (mode == "AUTO" or args.dry_run) and not paused
            detections = vision.latest() if vision else []
            rule = rules.evaluate(detections, now) if rules and driving else None
            if driving and rule and rule.hold:
                planner.reset()   # moves off again through the normal resume delay
                speed, brake = 0, True
            elif driving:
                distance = m.distance_m
                if rule and rule.distance_m is not None:
                    distance = rule.distance_m if distance is None else min(distance, rule.distance_m)
                if lidar_lost:
                    distance = 0.0      # a sensor we rely on went quiet: stop, as for lost depth
                elif lidar_dist is not None:
                    distance = lidar_dist if distance is None else min(distance, lidar_dist)
                speed, brake = planner.update(distance, now)
            else:
                planner.reset()
                speed, brake = 0, True

            steer, steer_info = 0, ""
            if follower and driving:
                decision = follower.update(walls.find(*detector.geometry(depth_raw)), now)
                steer, steer_info = decision.steer, decision.info
                if decision.speed_cap is not None:
                    speed = min(speed, decision.speed_cap)
            elif follower:
                follower.reset()

            s = link.status if link else None
            battery = guard.update(s.battery_left_v, s.battery_right_v, driving, now) if s else ""
            if battery == "STOP":
                planner.reset()
                speed, brake = 0, True
            if battery and battery != last_battery:
                print("BATTERY LOW - stopped. Charge or swap the LiPos." if battery == "STOP"
                      else f"Battery getting low: {describe(s.battery_left_v)} / {describe(s.battery_right_v)}")
            last_battery = battery
            left, right = apply_trim(speed)
            if link:
                link.drive(left, right, brake, steer)

            frames_seen += 1
            if now - fps_t0 >= 1.0:
                fps = frames_seen / (now - fps_t0)
                frames_seen, fps_t0 = 0, now

            dist = "BLIND" if m.blind else ("clear" if m.distance_m is None else f"{m.distance_m:.2f} m")
            state = "PAUSED" if paused else ("BATTERY" if battery == "STOP" else
                                             "STOP_SIGN" if rule and rule.hold else
                                             "LIDAR_LOST" if lidar_lost and driving else
                                             (planner.state if driving else "IDLE"))
            batteries = f"{describe(s.battery_left_v)} / {describe(s.battery_right_v)}" if s else "-"
            line = f"{mode:8} {state:9} obstacle {dist:9} speed {left}/{right}" + (" BRAKE" if brake else "")
            if rule and rule.reason:
                line += f"  [{rule.reason}]"
            if lidar:
                line += f"  lidar {lidar_text}"
            if follower:
                steer_state = link.status.steer_state if link else "-"
                line += f"  steer {steer:+d} ({steer_state}) {steer_info}"
            if state != last_state or now - last_print > 0.5:
                pwm = f" pwm {link.status.pwm_left}/{link.status.pwm_right}" if link else ""
                print(f"{line}{pwm}  ({m.points} pts, {fps:.0f} fps)")
                last_print, last_state = now, state

            lines = [f"{mode} {state}", f"obstacle {dist}", f"speed {left}/{right}{' BRAKE' if brake else ''}"]
            if rule and rule.reason:
                lines.append(rule.reason)
            if follower:
                lines.append(f"steer {steer:+d} {steer_info}")
            if lidar:
                lines.append(f"lidar {lidar_text}")
            if battery:
                lines.append(f"battery {batteries}" + (" - STOPPED" if battery == "STOP" else " - low"))
            key = read_key()
            recording = recorder is not None and recorder.active
            if args.show or phone or recording:
                vis = depth_view(depth_raw, m, detector.stride, lines)
                cam = None
                if phone_color is not None:
                    cam = draw(phone_color.copy(), detections) if vision else phone_color.copy()
                    put_lines(cam, lines)
                if args.show:
                    cv2.imshow("Navya", vis)
                    k = cv2.waitKey(1) & 0xFF
                    key = (chr(k).lower() if k != 255 else None) or key
                if recording:
                    recorder.frame("depth", vis)
                    if radar is not None:
                        recorder.frame("lidar", radar)
                    if cam is not None:
                        recorder.frame("camera", cam)
                    recorder.log(mode=mode, state=state,
                                 obstacle_m="" if m.distance_m is None else f"{m.distance_m:.2f}",
                                 speed_left=left, speed_right=right, brake=int(brake),
                                 pwm_left=s.pwm_left if s else "", pwm_right=s.pwm_right if s else "",
                                 ch2_us=s.ch2_us if s else "", ch5_us=s.ch5_us if s else "",
                                 vision=rule.reason if rule else "",
                                 objects=summary(detections) if vision else "", fps=f"{fps:.0f}",
                                 steer_cmd=steer if follower else "",
                                 steer_pos=s.steer_pos if s and follower else "",
                                 lane=steer_info,
                                 battery_left_v=f"{s.battery_left_v:.2f}" if s else "",
                                 battery_right_v=f"{s.battery_right_v:.2f}" if s else "",
                                 lidar_m=lidar_text)
                if phone:
                    phone.publish("depth", vis)
                    if radar is not None:
                        phone.publish("lidar", radar)
                    if cam is not None:
                        phone.publish("camera", cam)
                    status = dict(mode=mode, state=state, obstacle=dist, speed=f"{left}/{right}",
                                  brake="ON" if brake else "off",
                                  pwm=f"{link.status.pwm_left}/{link.status.pwm_right}" if link else "-",
                                  battery=batteries + (" LOW" if battery else ""),
                                  fps=f"{fps:.0f}")
                    if vision:
                        status.update(objects=summary(detections), vision_fps=f"{vision.fps:.0f}")
                    if lidar:
                        status.update(lidar=lidar_text)
                    if follower:
                        status.update(steer=f"{steer:+d} ({link.status.steer_state if link else '-'})",
                                      lane=steer_info or "-")
                    if recording:
                        status.update(recording="ON")
                    if note and now - note_at < 6:
                        status.update(note=note)
                    if asker:
                        status.update(ai=asker.answer)
                    phone.set_status(**status)
                    for cmd in phone.pop_commands():
                        if cmd == "pause" and not paused:
                            key = " "
                        elif cmd == "resume" and paused:
                            key = " "
                        elif cmd == "save":
                            changed = live_settings.save()
                            note, note_at = "saved to config.py: " + (", ".join(changed) or "no changes"), now
                            print("Settings " + note)
                    for name, value in phone.pop_settings():
                        note, note_at = "set " + live_settings.apply(name, value), now
                        print("Settings: " + note)
                    for question in phone.pop_questions():
                        if asker:
                            asker.ask(cam if cam is not None else vis, question,
                                      context=f"mode {mode}, state {state}, nearest obstacle in path {dist}"
                                              + (f", lidar {lidar_text}" if lidar else "")
                                              + (f", objects: {summary(detections)}" if vision else ""))
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
        if vision:
            vision.close()
        if lidar:
            lidar.close()
        pipeline.stop()
        if recorder:
            recorder.close()
        if phone:
            phone.close()
        print("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
