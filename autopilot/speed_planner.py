"""Turns obstacle distance into a speed: cruise, slow down, stop, resume."""

from collections import deque

import config

CLEAR = "CLEAR"
SLOWING = "SLOWING"
STOPPED = "STOPPED"
RESUMING = "RESUMING"


class SpeedPlanner:
    def __init__(self):
        self.reset()

    def reset(self):
        """Back to a standstill; called whenever the car is not in AUTO."""
        self.state = STOPPED
        self._history = deque(maxlen=config.DISTANCE_HISTORY)
        self._clear_since = None

    def update(self, distance_m: float | None, now_s: float) -> tuple[int, bool]:
        """Returns (speed 0..1000, brake) for the latest distance (None = clear)."""
        self._history.append(float("inf") if distance_m is None else distance_m)
        d = min(self._history)

        if self.state in (STOPPED, RESUMING):
            if d < config.RESUME_DIST_M:
                self.state = STOPPED
                self._clear_since = None
                return 0, True
            if self._clear_since is None:
                self._clear_since = now_s
            if now_s - self._clear_since < config.RESUME_DELAY_S:
                self.state = RESUMING
                return 0, True
            self._clear_since = None

        if d <= config.STOP_DIST_M:
            self.state = STOPPED
            return 0, True

        if d < config.SLOW_DOWN_DIST_M:
            self.state = SLOWING
            frac = (d - config.STOP_DIST_M) / (config.SLOW_DOWN_DIST_M - config.STOP_DIST_M)
            speed = config.CREEP_SPEED + (config.CRUISE_SPEED - config.CREEP_SPEED) * frac
            return int(round(speed)), False

        self.state = CLEAR
        return config.CRUISE_SPEED, False


def apply_trim(speed: int, trim: float = config.TRIM) -> tuple[int, int]:
    """Split one speed into (left, right) with the straight-line trim applied."""
    left = speed * (1.0 - trim)
    right = speed * (1.0 + trim)
    return (max(0, min(1000, int(round(left)))), max(0, min(1000, int(round(right)))))
