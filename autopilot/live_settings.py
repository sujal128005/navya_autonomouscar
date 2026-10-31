"""Settings that can be changed from the phone while the car runs, and saved to config.py.

Every module reads config.<NAME> each time it uses it, so changing the attribute
takes effect on the next frame. Values are clamped to safe ranges here, and
settings that depend on each other are kept consistent.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import config

CONFIG_FILE = Path(__file__).with_name("config.py")


@dataclass(frozen=True)
class Setting:
    name: str
    label: str
    low: float
    high: float
    step: float


SETTINGS = [
    Setting("CRUISE_SPEED", "Cruise speed", 50, 400, 10),
    Setting("CREEP_SPEED", "Slowest speed near obstacles", 40, 200, 5),
    Setting("START_BOOST_SPEED", "Start boost", 0, 400, 10),
    Setting("SLOW_DOWN_DIST_M", "Start slowing at (m)", 1.5, 6.0, 0.1),
    Setting("STOP_DIST_M", "Stop at (m)", 0.6, 4.0, 0.1),
    Setting("RESUME_DELAY_S", "Wait before moving off (s)", 0.0, 3.0, 0.1),
    Setting("PERSON_EXTRA_MARGIN_M", "Extra margin for people (m)", 0.0, 2.0, 0.1),
    Setting("LOOKAHEAD_M", "Lane lookahead (m)", 0.8, 3.0, 0.1),
    Setting("TRIM", "Straight-line trim (+ = right wheel faster)", -0.2, 0.2, 0.01),
]
BY_NAME = {s.name: s for s in SETTINGS}
# Changed automatically to keep the rules consistent; saved along with the rest.
DEPENDENT = ["RESUME_DIST_M", "DETECT_MAX_M"]


def _decimals(step: float) -> int:
    return 0 if step >= 1 else len(f"{step:.10f}".rstrip("0").split(".")[1])


def values() -> dict[str, float]:
    return {s.name: getattr(config, s.name) for s in SETTINGS}


def apply(name: str, value: float) -> str:
    """Set one setting (clamped and rounded to its step). Returns a short note."""
    s = BY_NAME[name]
    value = min(s.high, max(s.low, float(value)))
    value = round(round(value / s.step) * s.step, _decimals(s.step))
    if s.step >= 1:
        value = int(value)
    setattr(config, name, value)
    # Keep the distance rules consistent: stop < resume, stop + 0.5 <= slow-down < detection range.
    if config.SLOW_DOWN_DIST_M < config.STOP_DIST_M + 0.5:
        config.SLOW_DOWN_DIST_M = round(config.STOP_DIST_M + 0.5, 1)
    config.RESUME_DIST_M = max(config.RESUME_DIST_M, round(config.STOP_DIST_M + 0.4, 1))
    config.DETECT_MAX_M = max(config.DETECT_MAX_M, round(config.SLOW_DOWN_DIST_M + 0.7, 1))
    return f"{s.label} = {value}"


def save(path: Path = CONFIG_FILE) -> list[str]:
    """Write the current values into config.py, keeping each line's comment."""
    text = path.read_text(encoding="utf-8")
    changed = []
    for name in [s.name for s in SETTINGS] + DEPENDENT:
        value = getattr(config, name)
        pattern = re.compile(rf"^({name}\s*=\s*)([^#\n]*?)(\s*#.*)?$", re.M)
        match = pattern.search(text)
        if not match:
            continue
        old = match.group(2).strip()
        new = repr(value) if isinstance(value, float) else str(value)
        if old != new:
            changed.append(f"{name}: {old} -> {new}")
            text = text[:match.start(2)] + new + text[match.end(2):]
    path.write_text(text, encoding="utf-8")
    return changed
