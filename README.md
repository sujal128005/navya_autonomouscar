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
2. Transmitter on, CH5 in **MANUAL**, right stick centred.
3. Laptop: `python navya_autopilot.py --show`, and wait for `Running`.
4. A person holds the transmitter for the whole run, ready to pull the stick back.
5. Flip CH5 to **AUTO**. The car drives off.
6. Step in front of it (or slide a box in): it slows and stops. Step away: after
   1.5 s it moves off again.
7. End the run with CH5 back to MANUAL. On the laptop, SPACE pauses and Q quits.

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
