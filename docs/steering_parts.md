# Steering: parts and decision

## Decision (31 October 2026)

As decided by the professor, the car keeps **the toy's own steering motor and gearbox**. The toy
motor has no position sensor, so we add:
- a motor driver, so the Arduino can turn it both ways;
- a potentiometer on the steering shaft, so the Arduino knows the wheel angle;
- a limit switch at each lock, so the motor never strains against the end stops.

The firmware (`firmware/navya_drive`, v2) already runs this. Wiring is in the README, under
*Wiring → Steering*. Calibration uses `steering_calibrate.py`.

## Order now (Robu.in, ₹2,302 incl. GST, prices of 31 Oct 2026)

| Qty | Part | Robu SKU | Why |
|---|---|---|---|
| 1 | SmartElex BTS7960 motor driver (43 A, 6-27 V) | R189064 | drives the toy steering motor left/right from D5/D6 |
| 2 | 10 kΩ potentiometer, 15 mm shaft | 607345 | steering angle sensor (one spare) |
| 2 | KW4 roller-lever micro switch | R132437 | full-left / full-right limit switches |
| 1 | Inline blade fuse holders (5 pcs) | 699636 | fuse in the 12 V lead to the BTS7960 |
| 4 | 10 A blade fuse | R182177 | for those holders, plus spares |
| 2 m | 18 AWG silicone wire, red | R164399 | power wiring |
| 2 m | 18 AWG silicone wire, black | R164398 | power wiring |

Power for the steering motor comes from the car's **existing 12 V battery**, so there is
nothing to buy for it.

**Also worth adding:** 2 × 47 kΩ and 2 × 10 kΩ resistors (a few rupees, any shop) for the
battery monitor on A4/A5 (README, *Battery monitor*).

## Not buying now

These were considered and are kept in `navya_bill_robu.xlsx` for reference.

| Item | Why not now |
|---|---|
| 180 kg·cm servo (BL51180-24V), servo arm, ball joints, link rod | professor: keep the toy steering |
| Emergency-stop button, relay and socket | the transmitter's stick-back stop is the emergency stop for now |
| Two battery isolator switches | the batteries are unplugged at the controller instead |
| XT60 pigtails | the steering runs from the 12 V battery, not a LiPo tap |
| 256 GB microSD card | the existing 128 GB card is used for trip recordings |

## Before fitting

1. **Disconnect the toy's control board** from the steering motor. The motor's two wires go to
   the BTS7960 M+ / M−.
2. **Mount the potentiometer** so its shaft turns with the steering. Set it roughly mid-way with
   the wheels straight, so neither lock reaches the pot's own end.
3. **Mount the limit switches** so the linkage presses each one just before the hard stop.
4. Then follow the README: upload firmware v2, move the brake wires to D11/D12, wire the
   steering, and run `python steering_calibrate.py`.
