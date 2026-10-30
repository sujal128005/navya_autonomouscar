"""Find the lane between two black floor-tile strips, from the colour camera.

The colour image is re-projected onto the floor (a bird's-eye view) using the
calibrated camera height and tilt, so strips appear as straight bands whose
real-world position can be measured directly.
"""

import math
from dataclasses import dataclass

import cv2
import numpy as np

import config
from obstacle import Intrinsics


@dataclass
class Line:
    """lateral = a + b * forward (metres; lateral + = right of the car)."""
    a: float
    b: float

    def lateral(self, forward):
        return self.a + self.b * np.asarray(forward)


@dataclass
class Lane:
    left: Line | None
    right: Line | None
    centre: Line
    width_m: float
    offset_m: float       # lane centre at the camera; + = centre is right of the car
    heading_deg: float    # + = lane turns right ahead


@dataclass
class LaneView:
    birdseye: np.ndarray  # BGR top-down image of the floor (row 0 = furthest)
    valid: np.ndarray     # bool, floor cells the camera can see
    dark: np.ndarray      # bool, black-tile cells
    lane: Lane | None


class FloorProjector:
    """Floor position (forward, lateral) -> colour pixel, from the camera calibration."""

    def __init__(self, intr: Intrinsics):
        self.intr = intr
        p = math.radians(config.CAMERA_PITCH_DEG)
        self._cos, self._sin = math.cos(p), math.sin(p)

    def to_pixels(self, forward, lateral):
        forward = np.asarray(forward, dtype=np.float64)
        lateral = np.asarray(lateral, dtype=np.float64)
        h = config.CAMERA_HEIGHT_M
        xc = lateral - config.CAMERA_LATERAL_OFFSET_M
        yc = h * self._cos - forward * self._sin
        zc = forward * self._cos + h * self._sin
        ok = zc > 0.05
        zc = np.where(ok, zc, 1.0)
        u = self.intr.fx * xc / zc + self.intr.ppx
        v = self.intr.fy * yc / zc + self.intr.ppy
        ok &= (u >= 0) & (u <= self.intr.width - 1) & (v >= 0) & (v <= self.intr.height - 1)
        return u, v, ok


class LaneFinder:
    def __init__(self, intr: Intrinsics):
        self.projector = FloorProjector(intr)
        res = config.BEV_RES_M
        self.forwards = np.arange(config.BEV_MAX_FORWARD_M, config.BEV_MIN_FORWARD_M - 1e-9, -res)
        self.laterals = np.arange(-config.BEV_HALF_WIDTH_M, config.BEV_HALF_WIDTH_M + 1e-9, res)
        fwd, lat = np.meshgrid(self.forwards, self.laterals, indexing="ij")
        u, v, ok = self.projector.to_pixels(fwd, lat)
        self._map_x = np.where(ok, u, -1).astype(np.float32)
        self._map_y = np.where(ok, v, -1).astype(np.float32)
        self._valid = ok
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self.last_width = None    # lane width remembered from frames where both strips were seen
        self.dark_threshold = config.LANE_DARK_MAX

    def to_birdseye(self, image: np.ndarray, interpolation=cv2.INTER_LINEAR) -> np.ndarray:
        return cv2.remap(image, self._map_x, self._map_y, interpolation,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    def find(self, color_bgr: np.ndarray, not_floor: np.ndarray | None = None) -> LaneView:
        """not_floor: optional bool image (colour resolution) of pixels standing above the floor."""
        bev = self.to_birdseye(color_bgr)
        gray = cv2.cvtColor(bev, cv2.COLOR_BGR2GRAY)
        usable = self._valid.copy()
        if not_floor is not None:
            usable &= self.to_birdseye(not_floor.astype(np.uint8), cv2.INTER_NEAREST) == 0

        if usable.any():
            floor_level = float(np.median(gray[usable]))
            self.dark_threshold = min(config.LANE_DARK_MAX, config.LANE_DARK_RATIO * floor_level)
        dark = (usable & (gray < self.dark_threshold)).astype(np.uint8)
        dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, self._kernel)   # fill glare spots on tiles
        dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, self._kernel)    # drop specks
        dark = dark.astype(bool) & usable

        return LaneView(bev, self._valid, dark, self._fit(dark))

    def _fit(self, dark: np.ndarray) -> Lane | None:
        res = config.BEV_RES_M
        min_run = max(1, round(config.LANE_MIN_WIDTH_M / res))
        left_pts, right_pts = [], []
        for r in range(0, dark.shape[0], 2):
            f = self.forwards[r]
            if f > config.LANE_MAX_FORWARD_M:
                continue
            row = np.concatenate(([0], dark[r].astype(np.int8), [0]))
            edges = np.diff(row)
            starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
            keep = ends - starts >= min_run
            if not keep.any():
                continue
            mids = self.laterals[0] + (starts[keep] + ends[keep] - 1) / 2 * res
            # The strip nearest the car on each side bounds the lane.
            if (mids < 0).any():
                left_pts.append((f, mids[mids < 0].max()))
            if (mids >= 0).any():
                right_pts.append((f, mids[mids >= 0].min()))

        left, right = _fit_line(left_pts), _fit_line(right_pts)
        if left and right:
            width = float(right.a - left.a)
            self.last_width = width if self.last_width is None else 0.8 * self.last_width + 0.2 * width
            centre = Line((left.a + right.a) / 2, (left.b + right.b) / 2)
        elif (left or right) and self.last_width:
            # Only one strip in view: place the centre half a lane width from it.
            side = left or right
            half = self.last_width / 2 * (1 if left else -1)
            centre, width = Line(side.a + half, side.b), self.last_width
        else:
            return None
        return Lane(left, right, centre, width, centre.a, math.degrees(math.atan(centre.b)))


def _fit_line(points) -> Line | None:
    """Least-squares lateral = a + b*forward, refit once without outliers."""
    if len(points) < config.LANE_MIN_SAMPLES:
        return None
    pts = np.asarray(points)
    b, a = np.polyfit(pts[:, 0], pts[:, 1], 1)
    keep = np.abs(pts[:, 1] - (a + b * pts[:, 0])) < 0.15
    if keep.sum() < config.LANE_MIN_SAMPLES:
        return None
    b, a = np.polyfit(pts[keep, 0], pts[keep, 1], 1)
    return Line(float(a), float(b))
