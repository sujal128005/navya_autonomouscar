"""Battery watch: warn when a LiPo gets low, and stop the car before the controllers cut out.

The YL-12 controllers shut off at 21 V; stopping at BATTERY_STOP_V keeps a margin,
so the car stops where we decide instead of rolling to a halt somewhere random.
Once tripped, the stop stays until the program is restarted (voltage recovers a
little at rest, which must not make the car drive off again).
"""

import config

CELLS = 6
PLAUSIBLE_MIN_V = 15.0      # lower readings (2.5 V/cell) are a wiring fault, not a real LiPo


def plausible(volts: float) -> bool:
    return volts >= PLAUSIBLE_MIN_V


def describe(volts: float) -> str:
    if volts <= 0:
        return "-"
    if not plausible(volts):
        return f"{volts:.1f} V (check divider)"
    per_cell = volts / CELLS
    percent = max(0, min(100, round((per_cell - 3.5) / (4.2 - 3.5) * 100)))
    return f"{volts:.1f} V ({percent}%)"


class BatteryGuard:
    def __init__(self):
        self.tripped = False
        self._low_since = None

    def update(self, left_v: float, right_v: float, driving: bool, now_s: float) -> str:
        """Returns '' (fine), 'LOW' (warn) or 'STOP' (hold the car stopped)."""
        readings = [v for v in (left_v, right_v) if plausible(v)]   # 0 = not wired
        if self.tripped:
            return "STOP"
        if not readings:
            return ""
        lowest = min(readings)
        if lowest < config.BATTERY_STOP_V and driving:
            if self._low_since is None:
                self._low_since = now_s
            if now_s - self._low_since >= config.BATTERY_STOP_S:
                self.tripped = True
                return "STOP"
        else:
            self._low_since = None
        return "LOW" if lowest < config.BATTERY_WARN_V else ""
