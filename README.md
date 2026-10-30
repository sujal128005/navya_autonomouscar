# Navya

Autonomous car built on a TZ-306 4x4 ride-on, on a student budget.

**Demo 1 (current):** drive along a straight path, see an obstacle with the
Intel RealSense D435i, slow down, stop before it, and move off again by itself
once the obstacle is taken away.

## How it works

```
 D435i depth ──USB3──► Laptop: autopilot/navya_autopilot.py
                         finds the nearest thing inside the car's path
                         picks a speed: cruise / slow / stop / resume
                              │ USB serial "D,<left>,<right>,<brake>" at 30 Hz
                              ▼
 FlySky FS-R6B ──CH2,CH5──► Arduino Uno: firmware/navya_drive
                         MANUAL / AUTO / NO_RC modes, safety stops
                              │ throttle PWM + brake per wheel
                              ▼
                  2x YL-12 controller ──► 2x 8" BLDC rear hub motor
```

Front wheels are passive: steering is zip-tied straight and the three front
toy motors are disconnected. The car (~31 kg) drives on the two rear hubs only.

The Arduino is in charge of safety. The car stops if any of these happen:

| Event | Result |
|---|---|
| CH5 switch not in AUTO | laptop commands ignored (MANUAL: stick drives) |
| Right stick (CH2) pulled back | stop + brake, in any mode |
| No receiver signal for 0.1 s | stop + brake |
| No laptop command for 0.3 s (crash, cable out) | stop + brake |
| Camera stops sending frames | laptop sends stop |
| Something right against the lens (no depth) | treated as an obstacle |

## Hardware

| Part | Used for |
|---|---|
| 2x 8" BLDC hub motor, 24 V 350 W, drum brake | rear drive |
| 2x YL-12 brushless sine-wave controller (24 V, 16 A, brake active low, cut-off 21 V) | one per hub |
| 2x 6S LiPo 22.2 V 5200 mAh | motor power |
| Arduino Uno | throttle/brake output, RC input, safety |
| FlySky FS-CT6B transmitter + FS-R6B receiver | manual driving, AUTO switch, stop |
| Intel RealSense D435i | obstacle depth |
| Laptop (Windows, Python) | autopilot |
| Raspberry Pi 3B, LDROBOT D500 LiDAR | not used in Demo 1 |

## Wiring

### Arduino Uno pins

| Uno pin | Goes to |
|---|---|
| D9 | LEFT controller throttle signal (purple) |
| D10 | RIGHT controller throttle signal (purple) |
| D8 | LEFT controller F/R (silver) |
| D7 | RIGHT controller F/R (silver) |
| D5 | LEFT controller brake wire (optional) |
| D6 | RIGHT controller brake wire (optional) |
| GND | BOTH controllers' throttle black wires and F/R black wires |
| D3 | receiver CH2 signal pin |
| D2 | receiver CH5 signal pin |
| 5V / GND | receiver + / − (any channel's middle / outer pin) |
| USB | laptop |

Controller plug colours, from our bring-up:

- **Throttle plug:** black = GND, orange = +5 V out (leave unconnected), purple = signal.
- **F/R plug:** black = GND, silver = signal. Leaving it open means forward. If a wheel ever
  spins backwards, set `INVERT_LEFT` or `INVERT_RIGHT` in the firmware.
- **Brake (optional):** "Brake: Low" means pulling the brake wire to GND brakes. Without it,
  a stop is just throttle off and coast, so keep the stop distance generous.

The Uno's GND must connect to both controllers' throttle GND. Without that shared
ground the throttle signal means nothing.

Recommended additions, all cheap:

- **10 kΩ resistor** from each purple throttle wire to GND, so a disconnected or
  resetting Arduino reads as zero throttle.
- **Kill switch:** route both controllers' power-lock (ignition) wires through one
  toggle switch that someone can reach. Opening it cuts both motors, whatever the
  software is doing.

### Power

- One 6S LiPo per controller works fine. Join the two battery negatives with a proper
  wire so motor current never flows through the Arduino's ground.
- Full charge is 25.2 V; the controllers cut out at 21 V (3.5 V per cell), which
  also protects the LiPos.
- Power the Arduino before (or together with) the controllers. They refuse to start
  if they see throttle applied at power-on.
- Unplug the LiPos when the car is not being tested.

## Software setup

### 1. Flash the Arduino

1. Open `firmware/navya_drive/navya_drive.ino` in the Arduino IDE.
2. Choose board **Arduino Uno** and the right port, then click Upload.
3. Open the Serial Monitor at **115200** baud. You should see `NAVYA READY v1`, then
   `S,...` status lines 10 times a second:
   `S,<mode>,<CH2 µs>,<CH5 µs>,<laptop ok>,<pwm left>,<pwm right>,<brake>`

### 2. Laptop

Python 3.10 or newer. The D435i must be on a **USB 3** (blue) port.

```bash
cd autopilot
pip install -r requirements.txt
python test_logic.py
```

`test_logic.py` checks the obstacle maths and speed logic with simulated depth
images. It needs no hardware.

All tunable numbers live in `autopilot/config.py`.

## Bring-up, in this order

**Every step until step 7 is done with the car on blocks (rear wheels off the ground).**

1. **Radio check.** In the Serial Monitor, move the right stick: the CH2 value must
   go up and down (~1000–2000). Flip the CH5 switch: the mode must change between
   `MANUAL` and `AUTO`.
   - If CH5 doesn't respond, your switch is on another channel. Move the D2 wire to
     the channel that changes.
   - The CT6B's knobs and switches can be reassigned with the FlySky T6 config tool.
2. **Signal-loss check.** Turn the transmitter off. The mode must change to `NO_RC`
   within a moment.
   - If it stays `MANUAL`/`AUTO`, the receiver is repeating its last signal. In that
     case the transmitter is **not** a dead-man switch, and the kill switch above is
     a must.
3. **Manual drive.** CH5 in MANUAL, push the right stick up gently: both wheels must
   turn forward. Pull it back: brake.
4. **Find the throttle range.** CH5 in AUTO:
   ```bash
   python throttle_test.py --sweep
   ```
   - Note the first PWM at which both wheels turn and put it in `PWM_START` in the
     firmware.
   - Pick a `PWM_MAX` that gives a safe top speed. Start low (start + 40); 31 kg takes
     a while to stop. Re-upload.
   - Check both wheels together with `python throttle_test.py --speed 500`.
5. **Mount and calibrate the camera.** Mount it facing straight ahead, level
   side-to-side and tilted slightly down. Put the car on the floor with 2 m of
   empty floor ahead, then run:
   ```bash
   python calibrate_camera.py --write
   ```
6. **Camera-only check.** No motors are driven in this step:
   ```bash
   python navya_autopilot.py --dry-run --show
   ```
   - Walk in front of the car. The white overlay marks what counts as an obstacle,
     and the floor must **not** be white.
   - Watch the state go `CLEAR → SLOWING → STOPPED` as you get closer, and back to
     `RESUMING → CLEAR` 1.5 s after you step away.
7. **First ground run.** Set `CRUISE_SPEED = 200` in `config.py`.
   1. Place a cardboard box about 5 m ahead.
   2. CH5 to MANUAL, then run `python navya_autopilot.py --show`.
   3. Flip CH5 to AUTO. The car moves off after 1.5 s.
   4. Measure where it actually stops. Raise `STOP_DIST_M` if it stops too close,
      then raise speed step by step.

## Demo-day checklist

1. LiPos charged (above 24 V) and the kill switch in reach.
2. Transmitter on, **SWA down** (SWA up is dual rate and shortens the stick travel),
   CH5 in **MANUAL**, right stick centred.
3. Laptop: `python navya_autopilot.py --show`, and wait for `Running`.
4. A person holds the transmitter for the whole run, ready to pull the stick back.
5. Flip CH5 to **AUTO**. The car drives off.
6. Step in front of it (or slide a box in): it slows and stops. Step away: after
   1.5 s it moves off again.
7. End the run with CH5 back to MANUAL. On the laptop, SPACE pauses and Q quits.

## Trip recorder

Add `--record` to save every run:

```bash
python navya_autopilot.py --phone --vision --record
```

Each run gets its own folder, `trip_YYYYMMDD_HHMMSS`, under `navya_trips` on the **SD card**
(found automatically when inserted), or under `autopilot/recordings` if there is none. It contains:

| File | What |
|---|---|
| `camera.mp4` | camera picture with status text and detection boxes, real-time speed |
| `depth.mp4` | depth view, with the obstacle zone in white |
| `telemetry.csv` | 10 rows/s: mode, state, obstacle distance, speeds, brake, PWM, RC sticks, vision reason, objects (opens in Excel) |
| `report.png` | made by `trip_report.py` (below) |
| `raw.bag` | only with `--record-raw`: the full camera data for `--replay` |

- **Disk space:** the videos use about 15 GB per hour, and `--record-raw` adds about 100 GB per hour.
  Recording stops by itself when less than 2 GB is free; the car keeps driving.
- **Trip report:** `python trip_report.py` charts the newest trip (obstacle distance, speed, state)
  and prints stop counts and time in each state. `python trip_report.py <folder>` picks a specific one.
- **Replay:** `python navya_autopilot.py --replay <trip>/raw.bag --show --vision` runs the recorded
  camera data through the current settings. It never drives the car. Use it to tune `config.py`
  and see what the car *would* have done.

## Watch from a phone

The laptop rides in the car, so add `--phone` and open the views in any phone browser:

```bash
python navya_autopilot.py --phone          # camera, depth, mode, state, obstacle distance, speed
python corridor_view.py --phone            # camera + bird's-eye map, 3D map, lane, obstacle
```

1. On the laptop, turn on **Mobile hotspot** (Windows Settings → Network → Mobile hotspot), and
   connect the phone to it. Campus Wi-Fi often blocks phone-to-laptop traffic; the hotspot
   always works.
2. The program prints the addresses to open, for example `http://192.168.137.1:8080`. Use the
   `192.168.137.x` one when on the hotspot.
3. The phone shows the live pictures and a status bar. The mode turns **green in AUTO**, yellow
   in MANUAL and red with no radio. "NO UPDATES" means the program stopped.

The autopilot page has **Pause** and **Resume** buttons. Pause holds the car stopped, the same as
SPACE on the laptop. Wi-Fi can lag or drop, so **the transmitter stays the emergency stop**.
The first time, Windows may ask whether Python may use the network: allow it.

## Object detection

**YOLO11n** finds people, chairs, bags, bottles, bicycles, cars, stop signs and more in the
colour image. With the D435i, each object also gets its distance and side
(e.g. *person 2.3 m ahead*).

The model file is not in the repo. Download it once into `autopilot/models/`:

```bash
curl -L -o autopilot/models/yolo11n.pt https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt
```

Then:

```bash
cd autopilot
python vision_view.py              # D435i: objects + distance
python vision_view.py --webcam     # laptop webcam: objects only (no depth)
python vision_view.py --phone      # also on the phone page
```

- **Speed:** run `python export_models.py` once after downloading the model (needs
  `pip install openvino`). The detector then uses OpenVINO on the Intel GPU automatically:
  19 ms per frame (about 50 fps) on this laptop. Without OpenVINO it falls back to ONNX on the CPU
  (38 ms), then to PyTorch (about 75 ms).
- **Tuning:** `DETECT_CLASSES`, `DETECT_CONFIDENCE` and `DETECT_IMAGE_SIZE` in `config.py`
  control what it looks for, how sure it must be, and speed vs. small-object range.
- **Distance:** the nearer part of the middle of each box, so background showing around a person
  doesn't count.
- `vision_view.py` only looks. To drive with it, use the autopilot's `--vision` option (below).

### Driving with object detection

```bash
python navya_autopilot.py --phone --vision
```

- **People in or near the path:** the car stops `PERSON_EXTRA_MARGIN_M` (1 m) further away than
  for other obstacles, at 3.0 m instead of 2.0 m.
- **Stop sign within 2.5 m:** the car stops, waits 3 s, drives on, and ignores stop signs for 5 s
  so it can pass the sign. The phone and terminal show `STOP_SIGN` and the countdown.
  - **Print one:** a red octagon with white "STOP", at least A4 size.
  - **Place it beside the path** (0.5–1 m to the side, 0.5–1 m high) so the camera sees it. If you
    put it *in* the path, the depth check treats it as an obstacle and waits until it's removed.
- **Detection can only make the car more careful.** It runs in a separate thread; the depth
  obstacle check still runs every frame. If detections are late (over 0.5 s), they're ignored and
  the car behaves exactly as without `--vision`.
- Model loading adds about 8 s at start-up.

## Corridor viewer: lane and 3D map

`LANE_SOURCE` in `config.py` decides where the lane comes from:

- **`"walls"` (default):** the lane is the free corridor between the walls, measured by the depth
  camera. Shiny floors don't affect it. Our polished granite corridor mirrors the walls so strongly
  that colour-based strip finding is unreliable there.
- **`"strips"`:** the lane is the floor between two black strips (matte tape or tiles), found in the
  colour image.

```bash
cd autopilot
python corridor_view.py
```

This program only looks; it never drives the car. Two windows open:

- **Navya camera** has two parts:
  - The live picture with the strips (yellow) and the lane centre (green) drawn in.
  - A **bird's-eye floor map**: black tiles in yellow, anything standing on the floor in red.
  - The text shows how far the lane centre is to the left or right of the car, the lane's heading
    (+ = lane bends right), and the lane width.
- **Navya 3D** is a live 3D point cloud in real colours. Obstacles in the car's path are red and
  the strips are yellow; the car is outlined in blue.
  - Drag with the left mouse button to rotate, and use the wheel to zoom.
  - Keys **1 / 2 / 3** switch to the behind, top and side views.
- **S** saves a snapshot to `autopilot/captures/`: both pictures plus a `.ply` 3D file that opens
  in MeshLab or CloudCompare. **Q** quits.

Run `calibrate_camera.py --write` first. The floor map relies on the camera height and tilt.

| Problem | Change in `config.py` |
|---|---|
| Walls: lane edge jumps onto a bin or person by the wall | raise `WALL_MIN_LATERAL_M` |
| Walls: low skirting or clutter ignored / picked up | adjust `WALL_MIN_HEIGHT_M` |
| Strips not found (shown grey, not yellow) | raise `LANE_DARK_MAX` (e.g. 90) |
| Shadows or reflections show up as strips | lower `LANE_DARK_MAX` (e.g. 50) |
| Grout lines or cables picked up | raise `LANE_MIN_WIDTH_M` |

## Tuning (autopilot/config.py)

| Symptom | Change |
|---|---|
| Stops too close / bumps the obstacle | raise `STOP_DIST_M` and `SLOW_DOWN_DIST_M`, or lower `CRUISE_SPEED` |
| Stops for nothing (floor) | re-run `calibrate_camera.py --write`; raise `FLOOR_CLEARANCE_M` |
| Stops for things beside the path | lower `CORRIDOR_HALF_WIDTH_M` |
| Misses small/low objects | lower `FLOOR_CLEARANCE_M` or `MIN_OBSTACLE_POINTS` |
| Random `BLIND` stops (shiny floor) | raise `BLIND_CHECK_FRACTION`, or 1.01 to turn it off |
| Waits too long after the obstacle is gone | lower `RESUME_DELAY_S` |
| Stalls while creeping up to the obstacle | raise `CREEP_SPEED` (or `PWM_START` in the firmware is too low) |
| Veers right | raise `TRIM` a little (0.02 steps); veers left: lower it |
| Too jerky when moving off | lower `RAMP_UP_PER_10MS` in the firmware |

## Troubleshooting

- **"Could not pick the Arduino port"**: pass `--port COM5` (Device Manager shows the
  number) or set `SERIAL_PORT` in `config.py`.
- **"camera is on USB 2"**: use a blue USB 3 port and the original cable. If you must
  stay on USB 2, set 424x240 in `config.py`.
- **Mode stays `NO_RC`**: check receiver power (5V/GND) and that it is bound to the
  transmitter (receiver LED solid).
- **Wheels don't move in AUTO but the laptop shows speed**: is the status `laptop ok`
  field 1? Is the stick pulled back? Is `PWM_START` high enough?
- **Wheels won't start after power-on**: the controller saw throttle at power-on.
  Power-cycle the controllers with the Arduino already running.

## Repository layout

```
firmware/navya_drive/navya_drive.ino   Arduino Uno: RC + laptop -> throttle, brake, safety
autopilot/config.py                    every tunable number
autopilot/navya_autopilot.py           the demo program
autopilot/obstacle.py                  depth frame -> nearest obstacle in the car's path
autopilot/speed_planner.py             distance -> speed (cruise / slow / stop / resume)
autopilot/navya_link.py                serial link to the Arduino
autopilot/calibrate_camera.py          measures camera height and tilt from the floor
autopilot/throttle_test.py             bench test and PWM calibration
autopilot/test_logic.py                offline tests with simulated depth images
```

## Next steps (after Demo 1)

- LDROBOT D500 LiDAR as a second obstacle sensor and for mapping.
- Steering: replace the zip tie with a position-controlled steering actuator.
- Wheel speed feedback (hall signals) for closed-loop speed and odometry.
- Move the autopilot onto an onboard computer (ROS 2).
