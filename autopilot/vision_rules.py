"""Object-aware driving rules, and a background thread that keeps detections fresh.

Rules can only make the car more careful than the depth obstacle check:
  - a person in or near the path counts as PERSON_EXTRA_MARGIN_M closer than they are;
  - a stop sign within STOP_SIGN_TRIGGER_M stops the car for STOP_SIGN_WAIT_S, then the
    car drives on and ignores stop signs for STOP_SIGN_IGNORE_S so it can pass the sign.
"""

import threading
import time
from dataclasses import dataclass

import config
from vision import Detection, describe


@dataclass
class RuleResult:
    distance_m: float | None    # extra obstacle distance for the speed planner (None = nothing)
    hold: bool                  # True = stop now (stop sign)
    reason: str                 # for the screen / phone


class VisionRules:
    def __init__(self):
        self._hold_until = 0.0
        self._ignore_signs_until = 0.0

    def evaluate(self, detections: list[Detection], now_s: float) -> RuleResult:
        in_path = config.CORRIDOR_HALF_WIDTH_M + config.PERSON_SIDE_MARGIN_M
        people = [d.distance_m for d in detections
                  if d.label == "person" and d.distance_m is not None and abs(d.lateral_m) < in_path]
        distance, reason = None, ""
        if people:
            nearest = min(people)
            distance = max(0.0, nearest - config.PERSON_EXTRA_MARGIN_M)
            reason = f"person {nearest:.1f} m"

        if now_s < self._hold_until:
            return RuleResult(distance, True, f"stop sign, waiting {self._hold_until - now_s:.1f} s")
        if now_s >= self._ignore_signs_until:
            for d in detections:
                if d.label == "stop sign" and d.distance_m is not None and d.distance_m < config.STOP_SIGN_TRIGGER_M:
                    self._hold_until = now_s + config.STOP_SIGN_WAIT_S
                    self._ignore_signs_until = self._hold_until + config.STOP_SIGN_IGNORE_S
                    return RuleResult(distance, True, f"stop sign {d.distance_m:.1f} m")
        return RuleResult(distance, False, reason)


class VisionWorker:
    """Runs the detector on the newest colour + aligned-depth frame in its own thread,
    so the driving loop never waits for it. Older frames are simply dropped."""

    def __init__(self, detector, intr, depth_scale):
        self.detector, self.intr, self.depth_scale = detector, intr, depth_scale
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._input = None
        self._detections: list[Detection] = []
        self._stamp = 0.0
        self.fps = 0.0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, color, aligned_depth):
        with self._lock:
            self._input = (color, aligned_depth, time.monotonic())
        self._wake.set()

    def latest(self, max_age_s: float = config.VISION_MAX_AGE_S) -> list[Detection]:
        """Newest detections, or [] if they are too old to trust."""
        with self._lock:
            if time.monotonic() - self._stamp > max_age_s:
                return []
            return list(self._detections)

    def close(self):
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=2.0)

    def _run(self):
        count, t0 = 0, time.monotonic()
        while not self._stop.is_set():
            self._wake.wait(0.5)
            self._wake.clear()
            with self._lock:
                job, self._input = self._input, None
            if job is None:
                continue
            color, depth, taken_at = job
            detections = self.detector.detect(color, depth, self.depth_scale, self.intr)
            with self._lock:
                self._detections, self._stamp = detections, taken_at
            count += 1
            if time.monotonic() - t0 >= 1.0:
                self.fps, count, t0 = count / (time.monotonic() - t0), 0, time.monotonic()


def summary(detections: list[Detection], limit: int = 4) -> str:
    return ", ".join(describe(d) for d in detections[:limit]) or "nothing"
