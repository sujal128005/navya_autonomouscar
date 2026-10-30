"""Offline checks for the obstacle detector and speed planner (no camera needed).

    python test_logic.py
Builds synthetic depth images of a floor (and optionally a box) as the D435i
would see them, using the camera height and tilt from config.py.
"""

import math
import sys

import numpy as np

import config
from obstacle import CorridorDetector, Intrinsics
from speed_planner import CLEAR, RESUMING, SLOWING, STOPPED, SpeedPlanner, apply_trim

SCALE = 0.001  # D435i default: 1 unit = 1 mm
INTR = Intrinsics(640, 480, 385.0, 385.0, 320.0, 240.0)


def render(box=None, wall_at=None) -> np.ndarray:
    """box = (forward_m, half_width_m, height_m) standing on the floor, centred ahead."""
    p = math.radians(config.CAMERA_PITCH_DEG)
    c, s = math.cos(p), math.sin(p)
    h = config.CAMERA_HEIGHT_M
    us = (np.arange(INTR.width) - INTR.ppx) / INTR.fx
    vs = (np.arange(INTR.height) - INTR.ppy) / INTR.fy
    xn, yn = np.meshgrid(us, vs)

    # Ray with camera z = 1: level-forward and down components.
    fwd1 = c - yn * s
    down1 = yn * c + s
    z = np.full(xn.shape, np.inf)
    floor = down1 > 1e-6
    z[floor] = h / down1[floor]

    planes = []
    if box:
        planes.append(box)
    if wall_at:
        planes.append((wall_at, 10.0, 3.0))
    for fwd, half_w, top in planes:
        zp = np.where(fwd1 > 1e-6, fwd / np.maximum(fwd1, 1e-6), np.inf)
        height = h - down1 * zp
        hit = (np.abs(xn * zp) < half_w) & (height >= 0) & (height <= top) & (zp < z)
        z[hit] = zp[hit]

    z[(z > 10.0) | ~np.isfinite(z)] = 0  # beyond range reads as no data
    return (z / SCALE).astype(np.uint16)


def test_floor_only_is_clear():
    m = CorridorDetector(INTR, SCALE).measure(render(wall_at=8.0))
    assert m.distance_m is None and not m.blind, m


def test_box_distance():
    for dist in (1.0, 2.0, 2.7):  # a 0.5 m box drops below MIN_OBSTACLE_POINTS beyond ~2.8 m
        m = CorridorDetector(INTR, SCALE).measure(render(box=(dist, 0.25, 0.5), wall_at=8.0))
        assert m.distance_m is not None and abs(m.distance_m - dist) < 0.05, (dist, m.distance_m)


def test_box_outside_corridor_ignored():
    det = CorridorDetector(INTR, SCALE)
    depth = render(wall_at=8.0)
    side = render(box=(2.0, 0.15, 0.5), wall_at=8.0)
    # shift the box image sideways so it sits ~1 m to the right of the car
    shift = int(1.0 / 2.0 * INTR.fx)
    depth[:, shift:] = np.where(side[:, :-shift] < depth[:, shift:], side[:, :-shift], depth[:, shift:])
    m = det.measure(depth)
    assert m.distance_m is None, m.distance_m


def test_blind_when_lens_covered():
    m = CorridorDetector(INTR, SCALE).measure(np.zeros((480, 640), dtype=np.uint16))
    assert m.blind and m.distance_m == 0.0


def test_planner_cycle():
    p = SpeedPlanner()
    t = 0.0
    # starts stopped; needs RESUME_DELAY_S of clear path before moving
    assert p.update(None, t) == (0, True) and p.state == RESUMING
    t += config.RESUME_DELAY_S + 0.01
    assert p.update(None, t) == (config.CRUISE_SPEED, False) and p.state == CLEAR

    mid = (config.STOP_DIST_M + config.SLOW_DOWN_DIST_M) / 2
    speed, brake = p.update(mid, t)
    assert p.state == SLOWING and config.CREEP_SPEED < speed < config.CRUISE_SPEED and not brake

    assert p.update(config.STOP_DIST_M - 0.1, t) == (0, True) and p.state == STOPPED
    # obstacle removed: history still holds the near reading for DISTANCE_HISTORY frames
    for _ in range(config.DISTANCE_HISTORY):
        t += 0.03
        p.update(None, t)
    assert p.state == RESUMING
    t += config.RESUME_DELAY_S + 0.01
    assert p.update(None, t) == (config.CRUISE_SPEED, False)


def test_planner_obstacle_back_during_resume():
    p = SpeedPlanner()
    p.update(None, 0.0)
    p.update(config.RESUME_DIST_M - 0.1, 0.5)
    assert p.state == STOPPED


def render_strips(centres, half_width=0.1, heading_deg=0.0, floor=170, tile=25) -> np.ndarray:
    """Colour image of a light floor with black strips at lateral = c + tan(heading) * forward."""
    p = math.radians(config.CAMERA_PITCH_DEG)
    c, s = math.cos(p), math.sin(p)
    xn, yn = np.meshgrid((np.arange(INTR.width) - INTR.ppx) / INTR.fx, (np.arange(INTR.height) - INTR.ppy) / INTR.fy)
    down = yn * c + s
    img = np.full((INTR.height, INTR.width, 3), 110, np.uint8)  # walls above the horizon
    floor_px = down > 1e-6
    t = np.where(floor_px, config.CAMERA_HEIGHT_M / np.where(floor_px, down, 1), 0)
    forward, lateral = (c - yn * s) * t, xn * t + config.CAMERA_LATERAL_OFFSET_M
    img[floor_px] = floor
    slope = math.tan(math.radians(heading_deg))
    for centre in centres:
        img[floor_px & (np.abs(lateral - (centre + slope * forward)) < half_width)] = tile
    return img


def test_lane_between_two_strips():
    from lane import LaneFinder
    lv = LaneFinder(INTR).find(render_strips([-0.5, 0.7]))
    lane = lv.lane
    assert lane and lane.left and lane.right, lane
    assert abs(lane.offset_m - 0.1) < 0.04 and abs(lane.width_m - 1.2) < 0.06, lane
    assert abs(lane.heading_deg) < 1.5, lane


def test_lane_heading():
    from lane import LaneFinder
    lane = LaneFinder(INTR).find(render_strips([-0.6, 0.6], heading_deg=8.0)).lane
    assert lane and abs(lane.heading_deg - 8.0) < 1.5 and abs(lane.offset_m) < 0.05, lane


def test_lane_one_strip_uses_remembered_width():
    from lane import LaneFinder
    finder = LaneFinder(INTR)
    finder.find(render_strips([-0.6, 0.6]))
    lane = finder.find(render_strips([-0.6])).lane
    assert lane and lane.right is None and abs(lane.offset_m) < 0.05, lane


def test_no_strips_no_lane():
    from lane import LaneFinder
    assert LaneFinder(INTR).find(render_strips([])).lane is None


def corridor_points(left=-1.0, right=1.3, heading_deg=0.0, person=None):
    """Point arrays (forward, lateral, height, valid) for a corridor with two walls (+ optional person)."""
    rng = np.random.default_rng(1)
    slope = math.tan(math.radians(heading_deg))
    f = rng.uniform(0.3, 6.0, 20000)
    h = rng.uniform(-0.3, 2.0, 20000)   # below 0 = mirror images in a shiny floor
    lat = np.where(rng.random(20000) < 0.5, left, right) + slope * f + rng.normal(0, 0.02, 20000)
    if person:
        pf, pl = person
        f = np.concatenate([f, rng.uniform(pf, pf + 0.3, 2000)])
        lat = np.concatenate([lat, rng.uniform(pl - 0.2, pl + 0.2, 2000)])
        h = np.concatenate([h, rng.uniform(0, 1.7, 2000)])
    return f, lat, h, np.ones_like(f, dtype=bool)


def test_wall_lane():
    from lane import WallLaneFinder
    lane = WallLaneFinder().find(*corridor_points())
    assert lane and abs(lane.offset_m - 0.15) < 0.05 and abs(lane.width_m - 2.3) < 0.1, lane
    lane = WallLaneFinder().find(*corridor_points(heading_deg=-6))
    assert lane and abs(lane.heading_deg + 6) < 1.5, lane


def test_wall_lane_ignores_person_by_the_wall():
    from lane import WallLaneFinder
    lane = WallLaneFinder().find(*corridor_points(person=(2.0, 0.8)))
    assert lane and abs(lane.width_m - 2.3) < 0.1, lane


def test_trim():
    assert apply_trim(400, 0.0) == (400, 400)
    left, right = apply_trim(400, 0.05)
    assert right > left
    assert apply_trim(1000, 0.2) == (800, 1000)


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
