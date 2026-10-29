"""Measure the D435i's height above the floor and its downward tilt.

Park the car on the demo floor with at least 2 m of empty floor in front of it,
then run:
    python calibrate_camera.py           # print the values
    python calibrate_camera.py --write   # also save them into config.py
Re-run it whenever the camera mount is moved or bumped.
"""

import argparse
import math
import re
import sys
from pathlib import Path

import numpy as np
import pyrealsense2 as rs

import config

FRAMES = 30


def fit_plane(points: np.ndarray) -> tuple[np.ndarray, float]:
    """Least-squares plane through points, refined twice by dropping outliers.
    Returns (unit normal pointing down in camera coordinates, camera-to-plane distance)."""
    keep = np.ones(len(points), dtype=bool)
    for _ in range(3):
        centroid = points[keep].mean(axis=0)
        _, _, vt = np.linalg.svd(points[keep] - centroid, full_matrices=False)
        normal = vt[2]
        if normal[1] < 0:  # camera y axis points down
            normal = -normal
        dist = np.abs((points - centroid) @ normal)
        keep = dist < max(0.02, np.percentile(dist[keep], 80))
    return normal, float(centroid @ normal)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="save the result into config.py")
    args = parser.parse_args()

    pipeline = rs.pipeline()
    cfg = rs.config()
    cfg.enable_stream(rs.stream.depth, config.DEPTH_WIDTH, config.DEPTH_HEIGHT, rs.format.z16, config.DEPTH_FPS)
    profile = pipeline.start(cfg)
    try:
        scale = profile.get_device().first_depth_sensor().get_depth_scale()
        intr = profile.get_stream(rs.stream.depth).as_video_stream_profile().get_intrinsics()
        for _ in range(15):  # let auto-exposure settle
            pipeline.wait_for_frames()
        # np.array copies: holding librealsense frame buffers would starve its small frame pool
        stack = [np.array(pipeline.wait_for_frames().get_depth_frame().get_data()) for _ in range(FRAMES)]
    finally:
        pipeline.stop()

    depth = np.median(np.stack(stack), axis=0) * scale
    h, w = depth.shape
    v0, u0, u1 = int(h * 0.6), int(w * 0.25), int(w * 0.75)  # lower-middle of the image: the floor
    vs, us = np.mgrid[v0:h:2, u0:u1:2]
    z = depth[v0:h:2, u0:u1:2]
    ok = (z > 0.2) & (z < 3.0)
    if ok.sum() < 500:
        print("Not enough floor visible in the lower part of the image. Is the camera pointing at the floor ahead?")
        return 1
    z = z[ok]
    pts = np.column_stack([(us[ok] - intr.ppx) / intr.fx * z, (vs[ok] - intr.ppy) / intr.fy * z, z])

    normal, height = fit_plane(pts)
    pitch = math.degrees(math.atan2(normal[2], normal[1]))
    roll = math.degrees(math.atan2(normal[0], normal[1]))
    print(f"CAMERA_HEIGHT_M = {height:.3f}")
    print(f"CAMERA_PITCH_DEG = {pitch:.1f}    (positive = tilted down)")
    print(f"roll = {roll:.1f} deg (not used; keep the camera level if this is more than ~3)")
    if not 0.05 < height < 1.5:
        print("That height looks wrong - check that the floor really is what the camera sees.")
        return 1

    if args.write:
        path = Path(__file__).with_name("config.py")
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"^CAMERA_HEIGHT_M = [-\d.]+", f"CAMERA_HEIGHT_M = {height:.3f}", text, flags=re.M)
        text = re.sub(r"^CAMERA_PITCH_DEG = [-\d.]+", f"CAMERA_PITCH_DEG = {pitch:.1f}", text, flags=re.M)
        path.write_text(text, encoding="utf-8")
        print(f"Saved to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
