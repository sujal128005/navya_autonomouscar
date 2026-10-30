"""Find the nearest obstacle in the car's path from a RealSense depth frame."""

import math
from dataclasses import dataclass

import numpy as np

import config


@dataclass
class Intrinsics:
    width: int
    height: int
    fx: float
    fy: float
    ppx: float
    ppy: float


@dataclass
class Measurement:
    distance_m: float | None    # None = path clear
    points: int                 # corridor points behind the decision
    blind: bool                 # lens blocked / object closer than the sensor can see
    mask: np.ndarray            # corridor points, at DEPTH_STRIDE resolution


class CorridorDetector:
    """Keeps depth points inside a box in front of the car and reports the nearest.

    The box is defined in level, floor-based coordinates, so the camera's
    height and downward tilt (from config) are taken into account. That is
    what stops the floor itself from being reported as an obstacle.
    """

    def __init__(self, intr: Intrinsics, depth_scale: float, stride: int = config.DEPTH_STRIDE):
        self.stride = stride
        self.depth_scale = depth_scale
        us = np.arange(0, intr.width, stride, dtype=np.float32)
        vs = np.arange(0, intr.height, stride, dtype=np.float32)
        self._xn = ((us - intr.ppx) / intr.fx)[None, :]
        self._yn = ((vs - intr.ppy) / intr.fy)[:, None]
        pitch = math.radians(config.CAMERA_PITCH_DEG)
        self._cos = math.cos(pitch)
        self._sin = math.sin(pitch)

        rows, cols = len(vs), len(us)
        self._blind_rows = slice(int(rows * 0.3), int(rows * 0.9))
        self._blind_cols = slice(int(cols * 0.3), int(cols * 0.7))

    def geometry(self, depth_raw: np.ndarray):
        """Per-pixel (forward, lateral, height, valid) in level floor coordinates, at stride resolution."""
        s = self.stride
        z = depth_raw[::s, ::s].astype(np.float32) * self.depth_scale
        x = self._xn * z
        y = self._yn * z
        forward = z * self._cos - y * self._sin
        height = config.CAMERA_HEIGHT_M - (y * self._cos + z * self._sin)
        lateral = x + config.CAMERA_LATERAL_OFFSET_M
        return forward, lateral, height, z > 0

    def measure(self, depth_raw: np.ndarray) -> Measurement:
        forward, lateral, height, valid = self.geometry(depth_raw)

        mask = (
            valid
            & (forward > config.DETECT_MIN_M)
            & (forward < config.DETECT_MAX_M)
            & (np.abs(lateral) < config.CORRIDOR_HALF_WIDTH_M)
            & (height > config.FLOOR_CLEARANCE_M)
            & (height < config.MAX_OBSTACLE_HEIGHT_M)
        )

        blind_zone = valid[self._blind_rows, self._blind_cols]
        blind = 1.0 - blind_zone.mean() > config.BLIND_CHECK_FRACTION
        if blind:
            return Measurement(0.0, 0, True, mask)

        points = int(np.count_nonzero(mask))
        if points < config.MIN_OBSTACLE_POINTS:
            return Measurement(None, points, False, mask)

        nearest = float(np.percentile(forward[mask], config.OBSTACLE_PERCENTILE))
        return Measurement(max(0.0, nearest - config.CAMERA_SETBACK_M), points, False, mask)
