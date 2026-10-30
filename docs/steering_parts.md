# Steering: parts to order

Navya's front wheels are zip-tied straight. The original steering is the toy's DC motor with a
plastic gearbox and **no position sensor**, so a computer cannot set an angle with it. Either route
below gives the Arduino a steering angle it can command and check.

## Route A (recommended): high-torque servo

One part does motor, gearbox, position sensor and control. It is the fastest way to working
steering, and the Arduino simply sends an angle.

| Qty | Part | Spec to look for | Approx. price (INR) | Why |
|---|---|---|---|---|
| 1 | **Digital servo, 60 kg·cm** (e.g. DS5160 / similar) | metal gears, 180° or 270°, 6-8.4 V, steel output shaft, ≥ 50 kg·cm at 7.4 V | 2,000-3,500 | turns the front axle; ~2-3x the torque we estimate is needed |
| 1 | Servo arm (horn), aluminium, 25T | matches the servo spline (usually 25T) | 150-300 | connects the servo to the linkage |
| 1 | **UBEC / buck converter, 10 A** | input up to 30 V (6S LiPo is 25.2 V full), output set to 7.4 V | 600-1,200 | powers the servo from a LiPo; the Arduino's 5 V cannot |
| 1 | Ball-link rod / turnbuckle set, M3 or M4 | 2 ball links + threaded rod, about 10 cm | 150-300 | servo arm → steering linkage |
| 1 | Mounting bracket | aluminium servo bracket, or 3D-printed | 200-500 | holds the servo firmly to the chassis |

## Route B: keep the toy motor, add a driver and an angle sensor

Cheaper if the toy motor is strong enough, but more work: the sensor must be mounted on the
steering shaft, and the Arduino runs the position-control loop.

| Qty | Part | Spec | Approx. price (INR) | Why |
|---|---|---|---|---|
| 1 | **BTS7960 motor driver** (43 A H-bridge) | 6-27 V, 2 PWM inputs | 350-550 | drives the steering motor both ways |
| 1 | **AS5600 magnetic angle sensor** + diametric magnet (6 × 2.5 mm) | I2C, 12-bit | 150-300 | contactless angle of the steering shaft; does not wear |
| or 1 | 10 kΩ linear rotary potentiometer + coupler | single-turn, metal shaft | 50-150 | cheaper sensor alternative; wears over time |
| 1 | 12 V supply | the car's existing 12 V lead-acid battery, or a 24→12 V 5 A buck | 0-600 | steering motor power |

## Both routes

| Qty | Part | Why |
|---|---|---|
| 2 | Micro limit switches (KW11 lever) | hard stop signal at full left / full right, so the motor can't strain against the end stops |
| 1 | Inline blade fuse holder + 5 A fuse | protects the steering wiring |
| 2 | XT60 pigtails (male + female) | clean tap off the LiPo for the servo/steering power |
| 1 m | 18 AWG silicone wire (red + black) | power wiring |
| 1 set | Dupont jumpers, heat-shrink, zip ties, M3 screws/nuts | assembly |

## Strongly recommended at the same time: hardware emergency stop

| Qty | Part | Why |
|---|---|---|
| 1 | 22 mm mushroom emergency-stop switch (latching, NC contact) | one big red button that anyone can hit |
| 1 | Relay or contactor rated ≥ 40 A at 24 V DC (coil 12 V or 24 V) | the e-stop opens it, cutting both motor controllers' power |

Wire the e-stop in series with the relay coil, or simpler, with both controllers' power-lock wires.
Then motor power is cut regardless of what the laptop or Arduino is doing.

## Things to check before ordering

1. **Steering effort.** Remove the zip tie, unplug the toy steering motor, and with the car on
   the ground turn the front wheels by pushing the steering linkage by hand.
   - Easy, with fingers only: Route A's 60 kg·cm servo has plenty of margin.
   - Needs a firm push: still Route A, but pick a 70-80 kg·cm servo.
2. **Route A needs the toy gearbox disconnected** from the linkage, otherwise the servo fights it.
3. **Space.** Measure where a servo (about 65 × 30 × 50 mm) can sit near the steering linkage
   under the front bonnet. Send a photo and the measurements.

## Firmware note (handled when steering is added)

The Arduino Servo library uses Timer1, which also drives PWM on **D9/D10**, our current throttle
pins. With a servo, the wiring changes to:

| Signal | Now | With steering |
|---|---|---|
| Left / right throttle | D9 / D10 | **D5 / D6** |
| Left / right brake | D5 / D6 | **D11 / D12** |
| Steering servo signal | - | **D9** |
| Receiver CH1 (manual steering) | - | **D4** |

Prices are rough estimates. **For the actual Robu.in order (products, SKUs, live prices and stock) see `docs/navya_bill_robu.xlsx`.**
