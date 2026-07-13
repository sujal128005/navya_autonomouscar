# Phase 0 - Steering / Front Assembly Diagnosis

## Front steering
Front steering: DC motor, plastic gears, NO position sensor.
Status: LOCKED STRAIGHT.
Lock method: zip tie (steering linkage lashed to frame).
Front motor: unpowered / disconnected.
Photo: photos/front_wheels_locked.png

## Full front assembly (from bring-up)
- 2x DC motors: drive front wheels fwd/bwd (propulsion)
- 1x DC motor + gear + linkage: steering (left/right), NO position sensor
Total front motors: 3
PoC status: ALL front motors UNPOWERED / disconnected.
  Steering zip-tied straight; front wheels roll FREELY fwd/bwd (passive).
Decision: PoC drives on REAR 2x BLDC only. Front = passive rolling support.
Rationale: minimum-motor approach; avoids mixing DC+BLDC across axles;
  rear already drives straight and matched. Front drive + steering are
  documented assets reserved for a future turning/AWD milestone.

## Vehicle motor inventory: 5 motors total
- 2x rear BLDC hub (24V 350W, drum brake) = PoC DRIVE
- 2x front DC drive = reserved
- 1x front DC steer (no sensor) = reserved
