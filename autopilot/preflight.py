"""Pre-flight check: run before every session or demo.

    python preflight.py

Checks the laptop, Arduino, transmitter, steering, batteries, camera, LiDAR, storage,
object detection and phone link, and says how to fix anything that is wrong.
It never moves the car. Exit code 1 if anything FAILED.
"""

import importlib
import math
import os
import shutil
import socket
import subprocess
import sys
import time

import config

OK, WARN, FAIL, INFO = "OK", "WARN", "FAIL", "INFO"
results: list[tuple[str, str, str]] = []


def report(status: str, what: str, detail: str = ""):
    results.append((status, what, detail))
    print(f"[{status:^4}] {what}" + (f"  -  {detail}" if detail else ""))


def check_packages():
    fast = ("openvino", False) if os.name == "nt" else ("tensorrt", False)   # Intel laptop / Jetson
    for name, needed in (("numpy", True), ("cv2", True), ("pyrealsense2", True), ("serial", True),
                         ("ultralytics", False), fast):
        try:
            importlib.import_module(name)
        except ImportError:
            if needed:
                report(FAIL, f"Python package {name}", "pip install -r requirements.txt")
            else:
                use = {"ultralytics": "--vision", "openvino": "fast --vision", "tensorrt": "fast --vision"}[name]
                report(INFO, f"Python package {name} not installed", f"only needed for {use}")
    if not any(r[1].startswith("Python package") and r[0] == FAIL for r in results):
        report(OK, "Python packages")


def running_programs() -> set[str]:
    """Names of running programs, lower case, without '.exe'."""
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True).stdout
        names = [line.split('","')[0].strip('"') for line in out.splitlines() if line]
    else:
        names = subprocess.run(["ps", "-eo", "comm="], capture_output=True, text=True).stdout.split()
    return {n.lower().removesuffix(".exe") for n in names}


def check_programs():
    progs = running_programs()
    if "serial-monitor" in progs:
        report(FAIL, "Arduino Serial Monitor is open", "close it - it blocks the Arduino's port")
    elif progs & {"arduino ide", "arduino-ide"}:
        report(WARN, "Arduino IDE is open", "close it before driving (it can grab the port)")
    else:
        report(OK, "Arduino IDE closed")


def check_arduino():
    from serial.tools import list_ports

    from navya_link import ARDUINO_VIDS, NavyaLink, find_port
    if not config.SERIAL_PORT and not any(p.vid in ARDUINO_VIDS for p in list_ports.comports()):
        report(FAIL, "Arduino not connected", "plug in the Arduino's USB cable")
        return
    try:
        port = config.SERIAL_PORT or find_port()
    except RuntimeError as e:
        report(FAIL, "Arduino not found", str(e))
        return
    try:
        link = NavyaLink(port)
    except Exception as e:  # serial.SerialException, PermissionError
        hint = "another program has the port (Arduino IDE / Serial Monitor / a running Navya program)" \
            if "denied" in str(e).lower() else str(e)
        report(FAIL, f"Arduino on {port} can't be opened", hint)
        return
    try:
        if not link.wait_ready(6):
            report(FAIL, f"Arduino on {port} does not answer", "upload firmware/navya_drive/navya_drive.ino")
            return
        time.sleep(0.6)
        s = link.status
        if link.firmware == "v2":
            report(OK, f"Arduino on {port}, firmware v2")
        else:
            report(WARN, f"Arduino firmware {link.firmware or '?'}",
                   "upload v2 (and move the brake wires to D11/D12)")

        if s.mode == "NO_RC":
            report(FAIL, "No radio signal", "turn the transmitter on (receiver LED must be solid)")
        elif s.mode == "AUTO":
            report(WARN, "CH5 is in AUTO", "start in MANUAL; switch to AUTO once the program is running")
        else:
            report(OK, "Transmitter on, CH5 in MANUAL")
        # The firmware brakes below 1300 us and drives forward from 1520 us.
        if s.mode != "NO_RC" and not 1340 <= s.ch2_us < 1520:
            report(WARN, f"Right stick not centred (CH2 = {s.ch2_us})",
                   "let the stick spring back to centre; if it is centred, re-centre the throttle trim")

        steer = {"OK": (OK, "Steering calibrated"),
                 "OFF": (OK, "Steering calibrated (motor off: no radio)"),
                 "NOCAL": (WARN, "Steering not calibrated - run steering_calibrate.py (ignore if not fitted yet)"),
                 "POT": (FAIL, "Steering pot reading out of range - check its wires (5V, GND, wiper to A0)"),
                 "STALL": (WARN, "Steering stalled recently - check nothing blocks the wheels"),
                 "NONE": (INFO, "Steering disabled in firmware")}.get(s.steer_state)
        if steer:
            report(steer[0], steer[1])

        from battery import describe, plausible
        volts = [("left", s.battery_left_v), ("right", s.battery_right_v)]
        if all(v == 0 for _, v in volts):
            report(INFO, "Battery monitor not wired", "47k/10k dividers to A4/A5 (see README)")
        for side, v in volts:
            if v == 0:
                continue
            if not plausible(v):
                report(WARN, f"{side} battery reads {v:.1f} V", "divider wiring wrong or LiPo unplugged; "
                                                                "the low-battery stop ignores this reading")
            elif v < config.BATTERY_STOP_V:
                report(FAIL, f"{side} LiPo {describe(v)}", "charge it - the car would stop almost at once")
            elif v < config.BATTERY_WARN_V:
                report(WARN, f"{side} LiPo {describe(v)}", "getting low; charge soon")
            else:
                report(OK, f"{side} LiPo {describe(v)}")
    finally:
        link.close()


def check_camera():
    try:
        import numpy as np
        import pyrealsense2 as rs
    except ImportError:
        return
    devices = list(rs.context().query_devices())
    if not devices:
        report(FAIL, "RealSense camera not found", "plug it into a USB 3 port (blue on the laptop)")
        return
    dev = devices[0]
    usb = dev.get_info(rs.camera_info.usb_type_descriptor) if dev.supports(rs.camera_info.usb_type_descriptor) else "?"
    if usb.startswith("3"):
        report(OK, f"{dev.get_info(rs.camera_info.name)} on USB {usb}")
    else:
        report(WARN, f"Camera on USB {usb}",
               "works, but depth + colour is near USB 2's limit: use a USB 3 data cable "
               "(phone charger cables are USB 2) / flip the USB-C plug")

    def grab_depth():
        pipeline = rs.pipeline()
        cfg = rs.config()
        cfg.enable_stream(rs.stream.depth, config.DEPTH_WIDTH, config.DEPTH_HEIGHT, rs.format.z16, config.DEPTH_FPS)
        profile = pipeline.start(cfg)
        try:
            scale = profile.get_device().first_depth_sensor().get_depth_scale()
            intr = profile.get_stream(rs.stream.depth).as_video_stream_profile().get_intrinsics()
            frames = [np.array(pipeline.wait_for_frames(2000).get_depth_frame().get_data()) for _ in range(20)]
        finally:
            pipeline.stop()
        return frames, scale, intr

    try:
        frames, scale, intr = grab_depth()
        report(OK, "Camera delivers depth frames")
    except RuntimeError:
        # After re-plugging, the D435i can get stuck sending nothing; a reset frees it.
        try:
            dev.hardware_reset()
            time.sleep(6)
            frames, scale, intr = grab_depth()
            report(OK, "Camera delivers depth frames (after a camera reset)")
        except RuntimeError as e:
            report(FAIL, "Camera sends no frames, even after a reset",
                   f"{e} - is another Navya program using it? Re-plug the cable")
            return

    # Does the floor still match the saved calibration? (camera knocked or re-mounted)
    from calibrate_camera import fit_plane
    depth = np.median(np.stack(frames[-10:]), axis=0) * scale
    h, w = depth.shape
    v0, u0, u1 = int(h * 0.6), int(w * 0.25), int(w * 0.75)
    vs, us = np.mgrid[v0:h:2, u0:u1:2]
    z = depth[v0:h:2, u0:u1:2]
    sel = (z > 0.2) & (z < 3.0)
    if sel.sum() < 500:
        report(INFO, "Camera calibration not checked", "no clear floor visible in front of the car")
        return
    z = z[sel]
    pts = np.column_stack([(us[sel] - intr.ppx) / intr.fx * z, (vs[sel] - intr.ppy) / intr.fy * z, z])
    normal, height = fit_plane(pts)
    pitch = math.degrees(math.atan2(normal[2], normal[1]))
    if abs(height - config.CAMERA_HEIGHT_M) > 0.05 or abs(pitch - config.CAMERA_PITCH_DEG) > 3:
        report(WARN, f"Camera now {height:.2f} m / {pitch:.1f} deg, config says "
                     f"{config.CAMERA_HEIGHT_M:.2f} m / {config.CAMERA_PITCH_DEG:.1f} deg",
               "camera moved? with clear floor ahead run: python calibrate_camera.py --write")
    else:
        report(OK, f"Camera calibration matches ({height:.2f} m, {pitch:.1f} deg)")


def check_lidar():
    from lidar import LidarReader, find_lidar_port
    port = config.LIDAR_PORT or find_lidar_port()
    if not port:
        report(INFO, "LiDAR not connected", "only needed for --lidar and lidar_view.py")
        return
    reader = LidarReader(port)
    try:
        if not reader.wait_first(3):
            report(FAIL, f"LiDAR on {port} sends no full turns", "is it spinning? check its power")
        else:
            points = int(reader.latest().valid().sum())
            report(OK if points > 100 else WARN, f"LiDAR on {port}, {reader.rpm / 60:.1f} turns/s, {points} points",
                   "" if points > 100 else "few returns - lens dirty or covered?")
    finally:
        reader.close()


def check_storage():
    from trip_recorder import removable_drives
    drives = removable_drives()
    if drives:
        best = max(drives, key=lambda d: shutil.disk_usage(d).free)
        report(OK, f"SD card {best} - {shutil.disk_usage(best).free / 1e9:.0f} GB free")
    else:
        free_c = shutil.disk_usage("C:\\" if os.name == "nt" else "/").free / 1e9
        report(WARN if free_c < 10 else INFO, "No SD card / USB stick for recordings",
               f"--record would use this computer's own disk ({free_c:.0f} GB free)")


def check_detection():
    try:
        from vision import MODEL_PATH, pick_backend
    except ImportError:
        return
    if not MODEL_PATH.exists():
        report(INFO, "YOLO model not downloaded", "only needed for --vision (see README)")
        return
    _, _, backend = pick_backend()
    fast = "OpenVINO" in backend or "TensorRT" in backend
    report(OK if fast else WARN, f"Object detection: {backend}",
           "" if fast else "run python export_models.py for the fast version")


def local_addresses() -> list[str]:
    if os.name != "nt":
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout
        return out.split()
    try:
        return socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        return []


def check_phone():
    # The address this computer gets when it runs the hotspot itself:
    # Windows Mobile hotspot 192.168.137.1, Linux NetworkManager hotspot 10.42.0.1.
    hotspot = "192.168.137.1" if os.name == "nt" else "10.42.0.1"
    if hotspot in local_addresses():
        report(OK, "Hotspot on", f"phone: join it, open http://{hotspot}:8080")
    elif os.name == "nt":
        report(WARN, "Mobile hotspot looks off", "Windows Settings > Network > Mobile hotspot (for --phone)")
    else:
        report(INFO, "No hotspot on this computer", "only for the phone page: nmcli device wifi hotspot "
                     "ssid Navya password <8+ characters>, or join the phone and this computer to one network")
    probe = socket.socket()
    try:
        probe.bind(("0.0.0.0", 8080))
        report(OK, "Port 8080 free for the phone page")
    except OSError:
        report(FAIL, "Port 8080 already in use", "another Navya program is still running - close it")
    finally:
        probe.close()
    from ask_navya import NAMES, AskNavya
    ready = AskNavya.configured()
    if len(ready) >= 2:
        report(OK, "Ask Navya: " + " -> ".join(NAMES[p] for p in ready), "with fallback")
    elif ready:
        report(OK, f"Ask Navya: {NAMES[ready[0]]} only", "add a second free key in keys.env for a fallback")
    else:
        report(INFO, "Ask Navya: no free AI key yet", "copy keys.env.example to keys.env and add a key")


def check_laptop_power():
    """The laptop sleeps at critical battery, which cuts the camera, Arduino and LiDAR.
    On a Jetson: report the power mode instead (full speed = MAXN)."""
    if os.name != "nt":
        if shutil.which("nvpmodel"):
            out = subprocess.run(["nvpmodel", "-q"], capture_output=True, text=True).stdout
            mode = out.split("NV Power Mode:")[-1].split()[0] if "NV Power Mode:" in out else "?"
            report(OK if mode.startswith("MAXN") else WARN, f"Jetson power mode {mode}",
                   "" if mode.startswith("MAXN") else "full speed: sudo nvpmodel -m 2 (Orin Nano Super: MAXN_SUPER)")
        return
    import ctypes

    class PowerStatus(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]

    s = PowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)) or s.BatteryLifePercent == 255:
        return
    pct, plugged = s.BatteryLifePercent, s.ACLineStatus == 1
    what = f"Laptop battery {pct}%" + (" (charger connected)" if plugged else " (on battery)")
    if pct < 20:
        report(FAIL, what, "the laptop sleeps at critical battery and the car loses its camera - "
                           "charge it first (plug the charger straight into the laptop)")
    elif pct < 40:
        report(WARN, what, "charge before long runs; a USB hub's PD pass-through may not keep up")
    else:
        report(OK, what)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Navya pre-flight check\n")
    for check in (check_packages, check_programs, check_laptop_power, check_arduino, check_camera, check_lidar,
                  check_storage, check_detection, check_phone):
        try:
            check()
        except Exception as e:  # one broken check must not hide the others
            report(WARN, f"{check.__name__} could not run", repr(e))
    fails = sum(1 for r in results if r[0] == FAIL)
    warns = sum(1 for r in results if r[0] == WARN)
    print(f"\n{'READY' if not fails else 'NOT READY'}: {fails} failed, {warns} warnings")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
