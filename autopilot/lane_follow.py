"""Lane following: steer towards the lane centre with pure pursuit.

Pure pursuit picks the point on the lane centre-line LOOKAHEAD_M ahead and works
out the front-wheel angle whose arc passes through it:

    wheel angle = atan(2 * wheelbase * y / d^2)

where y is the point's sideways offset and d its distance, both measured from
the rear axle. Positive = steer right, matching the Arduino's steering command.
"""

import math
from dataclasses import dataclass

import config
from lane import Lane


@dataclass
class SteerDecision:
    steer: int                # -1000 full left .. 1000 full right
    speed_cap: int | None     # limit the planned speed (lane lost), or None
    info: str


class LaneFollower:
    def __init__(self):
        self.reset()

    def reset(self):
        self._steer = 0.0
        self._last_t = None
        self._lost_since = None

    def wheel_angle_deg(self, lane: Lane) -> float:
        """Front-wheel angle (degrees, + = right) that heads for the lookahead point."""
        y = float(lane.centre.lateral(config.LOOKAHEAD_M))
        x = config.LOOKAHEAD_M + config.CAMERA_TO_REAR_AXLE_M
        return math.degrees(math.atan2(2.0 * config.WHEELBASE_M * y, x * x + y * y))

    def update(self, lane: Lane | None, now_s: float) -> SteerDecision:
        dt = 0.0 if self._last_t is None else max(0.0, now_s - self._last_t)
        self._last_t = now_s

        cap = None
        if lane is None:
            if self._lost_since is None:
                self._lost_since = now_s
            if now_s - self._lost_since < config.LANE_LOST_HOLD_S:
                target, info = self._steer, "lane lost - holding"
            else:
                target, cap, info = 0.0, config.LANE_LOST_SPEED, "lane lost - straight, slow"
        else:
            self._lost_since = None
            angle = self.wheel_angle_deg(lane)
            target = max(-1000.0, min(1000.0, angle / config.STEER_MAX_DEG * 1000.0))
            side = "right" if lane.offset_m > 0 else "left"
            info = f"lane {abs(lane.offset_m):.2f} m {side} -> steer {angle:+.1f} deg"

        max_step = config.STEER_RATE_PER_S * dt
        self._steer += max(-max_step, min(max_step, target - self._steer))
        return SteerDecision(int(round(self._steer)), cap, info)
