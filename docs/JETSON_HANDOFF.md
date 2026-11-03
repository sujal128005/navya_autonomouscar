# Handoff: moving Navya from the laptop to the Jetson

*Written 3 November 2026 for the Claude Code session on the Jetson. Read all of it before
doing anything.*

## Who and what

- **User:** Sujal Negi, a student. Project: **Navya**, an autonomous car built on a TZ-306
  kids' ride-on car. (Not "Navyam", which is a separate drone project.)
- **Repo:** https://github.com/sujal128005/navya_autonomouscar. Work goes straight to
  `main`. GitHub Actions CI runs the tests and compiles the firmware on every push; keep
  it green.
- **Start with:** `README.md` (wiring, settings, troubleshooting) and
  `docs/PROJECT_REPORT.md` (design, safety layers, status).

## How to work with this user

- **One step at a time.** Explain what you are about to do and what the user must do
  physically, then wait for them to confirm. Keep messages short and plain; the user
  is not a Linux expert.
- **Never type the user's passwords, OTPs or logins.** If `sudo` or a website needs one,
  the user types it.
- **API keys:** never ask for a key in chat. Ask Navya uses free Gemini and Groq keys,
  which the user puts in the git-ignored `autopilot/keys.env` (template:
  `keys.env.example`). Don't add an Anthropic key.
- **No simulation work.** Scripted offline tests (`autopilot/test_logic.py`) are fine.
- **Steering:** the professor decided to keep the toy's own DC steering motor and gearbox
  (BTS7960 driver + potentiometer + limit switches). Don't propose a servo.
- **The car never moves without the user's go-ahead.** Wheels-up tests come before ground
  runs. Never send drive commands (`D`, `R`, `M`) unless the user has said the wheels are
  off the ground or the car is ready to drive.
- Commit messages end with the attribution line the harness gives you. Run
  `python3 autopilot/test_logic.py` before every commit. All 27 tests must pass.

## The car today (everything below is verified on the hardware, 2 Nov 2026)

| Part | Detail |
|---|---|
| Drive | 2× 8" BLDC hub motors (rear), 2× YL-12 controllers, 2× 6S LiPo 22.2 V 5200 mAh, about 31 kg in total |
| Arduino Uno (CH340 clone) | firmware v2 `firmware/navya_drive/navya_drive.ino`, **250000 baud** (115200 lost bytes), stick-back stop below 1300 µs |
| Radio | FlySky FS-CT6B + FS-R6B: SWA down; CH5 = MANUAL/AUTO; right stick back = stop in any mode |
| Camera | RealSense D435i, mounted rigidly at the front: **0.554 m high, 4.4° down** (in `config.py`). Needs USB 3. |
| LiDAR | LDROBOT D500 (STL-19P/LD19 protocol, 230400 baud) on a CP210x USB adapter, on the dashboard bar: forward −1°, clockwise, 0.365 m behind the bumper, 10 cm left of centre |
| Steering | parts ordered, not fitted. Firmware v2 supports it; `steering_calibrate.py` |
| Battery monitor | resistors not fitted. A4/A5 read as "not wired", which is expected. |

**Results on the ground (laptop):**
- box ahead: brakes at 1.97 m, rolls 0.85 m, stops 1.10 m away;
- person ahead (`--vision`): seen at 5 m, brakes at 2.85 m, stops about 1.8 m away;
- the stick-back stop overrides the laptop;
- the laptop going silent stops the motors within 0.26 s.

**Open problems:**
1. **LiDAR "lost":** with `--lidar`, the full autopilot sometimes sees no new scan for more
   than 0.5 s, and the car stops. It's not motor noise and not CPU load: separate tests ran
   clean. The autopilot now prints diagnostics when it happens (commit f3d7525). Ground
   runs were camera-only.
2. **Laptop power:** the laptop's USB hub didn't charge it, the battery ran flat, and
   Windows slept mid-session. One reason to move to the Jetson.

## Goal on the Jetson

Make the Jetson the car's onboard computer, replacing the laptop. Everything that runs
on the laptop should run here: the autopilot, pre-flight, viewers and calibration, plus
object detection on the Jetson GPU. The laptop then only connects over SSH (and a phone
can show the dashboard).

**Right now the Jetson is at the user's desk** with a monitor: no car, no camera, no
Arduino, no LiDAR. Do all the software setup there. The hardware tests happen later on
the car. **The camera and LiDAR stay mounted on the car; they are calibrated.**

## Plan (one step at a time, confirm each with the user)

1. **Find out what we have.**
   - `cat /etc/nv_tegra_release`, `dpkg -l | grep nvidia-jetpack`, `python3 --version`.
   - Which model (Orin Nano / "Super"?), storage (SD or NVMe) and free space: `df -h`.
   - `sudo nvpmodel -q`.
   - Expect JetPack 6.x with Python 3.10. The code has no 3.11+ syntax, but run
     `python3 -m compileall -q autopilot` to be sure.
2. **Basics:**
   - `sudo apt update`, then `git`, `python3-pip`, `python3-venv`.
   - Clone the repo to `~/navya_autonomouscar`. If it's private, the user logs in to
     GitHub themselves (`gh auth login`, or an SSH key they add).
   - Put the user in the `dialout` group for serial ports.
   - **Remove `brltty`** (`sudo apt remove brltty`). On Ubuntu it grabs CH340 serial
     adapters, so the Arduino would vanish.
3. **RealSense:** `pyrealsense2` for Python 3.10 on aarch64. Check first whether pip has a
   wheel for this platform. If not, build librealsense from source with
   `-DFORCE_RSUSB_BACKEND=ON -DBUILD_PYTHON_BINDINGS=ON`, plus the udev rules. Look up the
   current instructions; don't guess.
4. **Python packages:**
   - From `autopilot/requirements.txt`: numpy, opencv, pyserial, matplotlib, ultralytics.
   - Use NVIDIA's Jetson PyTorch wheel for this JetPack (check the current Jetson AI Lab
     or NVIDIA instructions). Plain pip PyTorch has no CUDA on Jetson.
   - Prefer the system `python3` with `--user`, or a venv created with
     `--system-site-packages`, so TensorRT and the CUDA libraries stay visible.
5. **Object detection on the GPU:**
   - `autopilot/vision.py` → `pick_backend()` knows OpenVINO, ONNX and `.pt`. Add a
     **TensorRT** backend: export `yolo11n.pt` to a `.engine` on the Jetson
     (`export_models.py`), and pick it first when present with `device=0`.
   - Check the speed on a sample image.
6. **Port the Windows-only bits.** Keep Windows working too; the laptop stays a fallback.
   - `navya_autopilot.py` `read_key()` and `steering_calibrate.py` `wait_key()` use
     `msvcrt`. On Linux, use `termios`/`select` for a non-blocking key read.
     **Important:** `steering_calibrate.wait_key` must keep sending `M,0` (`hold_still`)
     while it waits. A blocking `input()` lets the Arduino's 0.3 s laptop timeout expire,
     and the steering then moves on its own old calibration.
   - `preflight.py`:
     - `running_programs` uses `tasklist`;
     - `check_laptop_power` uses Windows `GetSystemPowerStatus`. On the Jetson, check the
       supply instead (`tegrastats` or the INA sensors), or skip it;
     - `check_phone` looks for the Windows hotspot address `192.168.137.1`. On Linux, use
       NetworkManager's hotspot (usually `10.42.0.1`);
     - `check_storage` uses `C:\`.
   - `trip_recorder.removable_drives()` is Windows-only. On Linux, use `/media/$USER/*`,
     or record to the NVMe drive.
   - Serial ports are `/dev/ttyUSB*` here. Auto-detection goes by USB vendor ID: CH340 =
     Arduino, CP210x = LiDAR. 250000 baud works with pyserial on Linux.
   - Add a `navya.sh` launcher with the same menu as `Navya.bat`.
7. **Tests:** `python3 autopilot/test_logic.py` (27 tests), and `preflight.py` with nothing
   plugged in. The expected FAILs are Arduino and camera.
8. **Remote access:**
   - SSH from the laptop, so the monitor isn't needed on the car.
   - Optional: a Wi-Fi hotspot on the Jetson for the phone dashboard (`--phone`, port
     8080). The user said the phone page is low priority; driving comes first.
   - `sudo nvpmodel -m <max>` and `jetson_clocks` for full speed. Ask before changing
     power modes.
9. **Later, on the car (not at the desk):**
   - power the Jetson from a LiPo through a step-down converter (it needs a part);
   - plug in camera (USB 3 port), Arduino and LiDAR;
   - `preflight.py`;
   - the wheels-up bench test;
   - then ground runs: plain → `--vision` → `--lidar` (watch the new LiDAR diagnostics).

## Useful facts

- All tuning lives in `autopilot/config.py`, one commented line per setting.
- Speed planner: stop 2.0 m, slow from 3.8 m, resume beyond 2.4 m after 0.5 s; start
  boost 250 for 0.4 s; cruise 130; creep 80. People: stop 1 m earlier (`--vision`).
- The serial protocol is documented at the top of `navya_drive.ino`. The Arduino sends
  `NAVYA READY v2`, a `CFG,...` line, then `S,...` status lines (17 fields) at 10 Hz.
- The CH340 clone loses bytes at 115200; that's why the link runs at 250000. The laptop
  side ignores and counts damaged lines (`NavyaLink.bad_lines`).
- The D435i can get stuck after re-plugging. Pre-flight and the autopilot reset it once
  by themselves.
- Pending for the user: Ask Navya keys (`keys.env`); steering parts; battery-monitor
  resistors (47k/10k on A4/A5).
