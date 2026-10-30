"""Navya corridor viewer: live lane between two black tile strips, a bird's-eye
floor map, and a 3D map of what is in front of the car.

    python corridor_view.py

Windows:
  "Navya camera"  colour view with the strips and lane centre drawn in,
                  next to the bird's-eye floor map (strips yellow, obstacles red)
  "Navya 3D"      3D point cloud; drag with the left mouse button to rotate,
                  mouse wheel to zoom
Keys: 1 view from behind, 2 top view, 3 side view, R reset view,
      S save a snapshot (PNG pictures + 3D .ply file in captures/), Q quit.

This program never drives the car. Push it, or drive it in MANUAL.
"""

import math
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pyrealsense2 as rs

import config
from lane import LaneFinder, LaneView
from obstacle import CorridorDetector, Intrinsics

CAR_LENGTH_M = 1.1
CAR_HALF_WIDTH_M = 0.31
CAPTURE_DIR = Path(__file__).with_name("captures")

STRIP_BGR = (0, 230, 255)    # yellow
CENTRE_BGR = (0, 220, 0)     # green
OBSTACLE_BGR = (40, 40, 255) # red
GRID_BGR = (90, 90, 90)
CAR_BGR = (255, 160, 0)      # blue


def start_camera():
    pipeline = rs.pipeline()
    cfg = rs.config()
    cfg.enable_stream(rs.stream.depth, config.DEPTH_WIDTH, config.DEPTH_HEIGHT, rs.format.z16, config.VIEW_FPS)
    cfg.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, config.VIEW_FPS)
    profile = pipeline.start(cfg)
    scale = profile.get_device().first_depth_sensor().get_depth_scale()
    i = profile.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()
    return pipeline, rs.align(rs.stream.color), Intrinsics(i.width, i.height, i.fx, i.fy, i.ppx, i.ppy), scale


class OrbitView:
    """A virtual camera circling a point ahead of the car. World axes: x right, y forward, z up."""

    PRESETS = {"1": (0.0, 22.0, 4.5), "2": (0.0, 89.0, 7.0), "3": (90.0, 12.0, 6.0)}

    def __init__(self, width=900, height=650):
        self.w, self.h = width, height
        self.target = np.array([0.0, 2.5, 0.3])
        self.preset("1")
        self._drag = None

    def preset(self, key):
        self.yaw, self.elev, self.dist = self.PRESETS[key]

    def on_mouse(self, event, x, y, flags, _param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self._drag = (x, y, self.yaw, self.elev)
        elif event == cv2.EVENT_LBUTTONUP:
            self._drag = None
        elif event == cv2.EVENT_MOUSEMOVE and self._drag:
            x0, y0, yaw0, elev0 = self._drag
            self.yaw = yaw0 - (x - x0) * 0.4
            self.elev = float(np.clip(elev0 + (y - y0) * 0.3, -5, 89))
        elif event == cv2.EVENT_MOUSEWHEEL:
            self.dist = float(np.clip(self.dist * (0.9 if cv2.getMouseWheelDelta(flags) > 0 else 1.1), 1.0, 15.0))

    def _basis(self):
        yaw, elev = math.radians(self.yaw), math.radians(self.elev)
        eye = self.target + self.dist * np.array([-math.sin(yaw) * math.cos(elev),
                                                  -math.cos(yaw) * math.cos(elev),
                                                  math.sin(elev)])
        fwd = self.target - eye
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, [0.0, 0.0, 1.0])
        right /= np.linalg.norm(right)
        return eye, fwd, right, np.cross(right, fwd)

    def project(self, pts):
        eye, fwd, right, up = self._basis()
        d = np.asarray(pts, dtype=np.float64) - eye
        z = d @ fwd
        ok = z > 0.1
        z = np.where(ok, z, 1.0)
        f = 0.9 * self.w
        u = f * (d @ right) / z + self.w / 2
        v = -f * (d @ up) / z + self.h / 2
        return u, v, z, ok

    def polyline(self, img, pts, color, thickness=1):
        u, v, _, ok = self.project(pts)
        for i in range(len(u) - 1):
            if ok[i] and ok[i + 1]:
                p0, p1 = (int(u[i]), int(v[i])), (int(u[i + 1]), int(v[i + 1]))
                cv2.line(img, p0, p1, color, thickness, cv2.LINE_AA)

    def render(self, pts, colors, lane, text):
        img = np.full((self.h, self.w, 3), 28, np.uint8)

        # Floor grid, 1 m squares, with distance labels.
        for f in range(0, 7):
            self.polyline(img, [(-2, f, 0), (2, f, 0)], GRID_BGR)
            u, v, _, ok = self.project([(2.15, f, 0)])
            if ok[0] and 0 <= u[0] < self.w and 0 <= v[0] < self.h:
                cv2.putText(img, f"{f} m", (int(u[0]), int(v[0])), cv2.FONT_HERSHEY_SIMPLEX, 0.45, GRID_BGR, 1)
        for x in range(-2, 3):
            self.polyline(img, [(x, 0, 0), (x, 6, 0)], GRID_BGR)

        # Points, far to near so nearer ones are drawn on top.
        u, v, z, ok = self.project(pts)
        ok &= (u >= 0) & (u < self.w - 1) & (v >= 0) & (v < self.h - 1)
        order = np.argsort(-z[ok])
        ui, vi, c = u[ok][order].astype(int), v[ok][order].astype(int), colors[ok][order]
        for du, dv in ((0, 0), (1, 0), (0, 1), (1, 1)):
            img[vi + dv, ui + du] = c

        # Car outline behind the camera.
        w, l, h = CAR_HALF_WIDTH_M, CAR_LENGTH_M, config.CAMERA_HEIGHT_M
        for zc in (0.0, h):
            self.polyline(img, [(-w, -l, zc), (w, -l, zc), (w, 0, zc), (-w, 0, zc), (-w, -l, zc)], CAR_BGR, 2)
        for x, y in ((-w, -l), (w, -l), (w, 0), (-w, 0)):
            self.polyline(img, [(x, y, 0), (x, y, h)], CAR_BGR, 2)

        if lane:
            fs = np.linspace(0.0, config.LANE_MAX_FORWARD_M, 20)
            for line, color, thick in ((lane.left, STRIP_BGR, 2), (lane.right, STRIP_BGR, 2), (lane.centre, CENTRE_BGR, 3)):
                if line:
                    self.polyline(img, np.column_stack([line.lateral(fs), fs, np.full_like(fs, 0.01)]), color, thick)

        for n, line in enumerate(text):
            cv2.putText(img, line, (10, 24 + 24 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        return img


def lane_text(lv: LaneView) -> list[str]:
    lane = lv.lane
    if not lane:
        return ["Lane: not found"]
    side = "right" if lane.offset_m > 0 else "left"
    strips = "both strips" if lane.left and lane.right else ("left strip only" if lane.left else "right strip only")
    return [f"Lane centre {abs(lane.offset_m):.2f} m {side}, heading {lane.heading_deg:+.1f} deg",
            f"Lane width {lane.width_m:.2f} m ({strips})"]


def draw_camera(color, lv: LaneView, finder: LaneFinder, text):
    vis = color.copy()
    if lv.lane:
        fs = np.linspace(config.BEV_MIN_FORWARD_M, config.LANE_MAX_FORWARD_M, 40)
        for line, bgr, thick in ((lv.lane.left, STRIP_BGR, 2), (lv.lane.right, STRIP_BGR, 2), (lv.lane.centre, CENTRE_BGR, 3)):
            if not line:
                continue
            u, v, ok = finder.projector.to_pixels(fs, line.lateral(fs))
            pts = np.column_stack([u[ok], v[ok]]).astype(np.int32)
            if len(pts) > 1:
                cv2.polylines(vis, [pts], False, bgr, thick, cv2.LINE_AA)
    for n, line in enumerate(text):
        cv2.putText(vis, line, (10, 24 + 24 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(vis, line, (10, 24 + 24 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return vis


def draw_birdseye(lv: LaneView, finder: LaneFinder, obstacle_fwd, obstacle_lat, height_px=480):
    res = config.BEV_RES_M
    img = lv.birdseye.copy()
    img[~lv.valid] = (25, 25, 25)
    img[lv.dark] = (0.3 * img[lv.dark] + 0.7 * np.array(STRIP_BGR)).astype(np.uint8)

    rows, cols = img.shape[:2]
    r = ((config.BEV_MAX_FORWARD_M - obstacle_fwd) / res).astype(int)
    c = ((obstacle_lat + config.BEV_HALF_WIDTH_M) / res).astype(int)
    inside = (r >= 0) & (r < rows) & (c >= 0) & (c < cols)
    img[r[inside], c[inside]] = OBSTACLE_BGR

    k = height_px / rows
    img = cv2.resize(img, (int(cols * k), height_px), interpolation=cv2.INTER_NEAREST)
    to_row = lambda f: int((config.BEV_MAX_FORWARD_M - f) / res * k)
    to_col = lambda lat: int((lat + config.BEV_HALF_WIDTH_M) / res * k)

    for f in range(1, int(config.BEV_MAX_FORWARD_M) + 1):
        cv2.line(img, (0, to_row(f)), (img.shape[1], to_row(f)), GRID_BGR, 1)
        cv2.putText(img, f"{f} m", (4, to_row(f) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    cv2.line(img, (to_col(0), 0), (to_col(0), img.shape[0]), GRID_BGR, 1)

    if lv.lane:
        fs = np.linspace(config.BEV_MIN_FORWARD_M, config.LANE_MAX_FORWARD_M, 20)
        for line, bgr, thick in ((lv.lane.left, STRIP_BGR, 2), (lv.lane.right, STRIP_BGR, 2), (lv.lane.centre, CENTRE_BGR, 3)):
            if line:
                pts = np.array([(to_col(lat), to_row(f)) for f, lat in zip(fs, line.lateral(fs))], np.int32)
                cv2.polylines(img, [pts], False, bgr, thick, cv2.LINE_AA)

    # Car: front edge at the bottom of the map.
    half = int(CAR_HALF_WIDTH_M / res * k)
    cx, bottom = to_col(0), img.shape[0] - 1
    cv2.rectangle(img, (cx - half, bottom - 12), (cx + half, bottom), CAR_BGR, -1)
    cv2.putText(img, "bird's-eye", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return img


def write_ply(path: Path, pts: np.ndarray, colors_bgr: np.ndarray):
    """Binary PLY point cloud (x right, y forward, z up, metres); opens in MeshLab or CloudCompare."""
    data = np.empty(len(pts), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                     ("red", "u1"), ("green", "u1"), ("blue", "u1")])
    data["x"], data["y"], data["z"] = pts[:, 0], pts[:, 1], pts[:, 2]
    data["red"], data["green"], data["blue"] = colors_bgr[:, 2], colors_bgr[:, 1], colors_bgr[:, 0]
    header = ("ply\nformat binary_little_endian 1.0\n"
              f"element vertex {len(pts)}\n"
              "property float x\nproperty float y\nproperty float z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(data.tobytes())


class Scene:
    """Everything worked out from one colour + aligned depth frame."""

    def __init__(self, intr: Intrinsics, depth_scale: float):
        self.obstacles = CorridorDetector(intr, depth_scale)
        self.cloud = CorridorDetector(intr, depth_scale, stride=config.VIEW_POINT_STRIDE)
        self.lanes = LaneFinder(intr)
        self.intr = intr

    def process(self, depth, color):
        m = self.obstacles.measure(depth)
        fwd, lat, hgt, valid = self.obstacles.geometry(depth)
        above = valid & (hgt > config.FLOOR_CLEARANCE_M) & (hgt < config.MAX_OBSTACLE_HEIGHT_M)
        not_floor = cv2.resize((valid & (hgt > 0.05)).astype(np.uint8), (self.intr.width, self.intr.height),
                               interpolation=cv2.INTER_NEAREST)
        lv = self.lanes.find(color, not_floor)

        s = config.VIEW_POINT_STRIDE
        f3, l3, h3, v3 = self.cloud.geometry(depth)
        keep = v3 & (f3 > 0.1) & (f3 < 8.0)
        pts = np.column_stack([l3[keep], f3[keep], h3[keep]])
        colors = color[::s, ::s][keep].copy()
        in_path = ((np.abs(pts[:, 0]) < config.CORRIDOR_HALF_WIDTH_M) & (pts[:, 2] > config.FLOOR_CLEARANCE_M)
                   & (pts[:, 2] < config.MAX_OBSTACLE_HEIGHT_M) & (pts[:, 1] < config.DETECT_MAX_M))
        colors[in_path] = (0.4 * colors[in_path] + 0.6 * np.array(OBSTACLE_BGR)).astype(np.uint8)

        # Black strips are drawn from the floor map, so they show even where the camera has no depth on them.
        rr, cc = np.nonzero(lv.dark[::2, ::2])
        strip = np.column_stack([self.lanes.laterals[cc * 2], self.lanes.forwards[rr * 2], np.full(len(rr), 0.005)])
        pts = np.vstack([pts, strip])
        colors = np.vstack([colors, np.tile(np.array(STRIP_BGR, np.uint8), (len(strip), 1))])

        return m, lv, pts, colors, fwd[above], lat[above]


def main():
    pipeline, align, intr, scale = start_camera()
    scene = Scene(intr, scale)
    view = OrbitView()
    cv2.namedWindow("Navya 3D")
    cv2.setMouseCallback("Navya 3D", view.on_mouse)
    CAPTURE_DIR.mkdir(exist_ok=True)
    print(__doc__)

    fps, n, t0 = 0.0, 0, time.monotonic()
    try:
        while True:
            try:
                frames = align.process(pipeline.wait_for_frames(2000))
            except RuntimeError:
                print("No frames from the camera - check the USB cable.")
                continue
            depth_frame, color_frame = frames.get_depth_frame(), frames.get_color_frame()
            if not depth_frame or not color_frame:
                continue
            depth = np.asanyarray(depth_frame.get_data())
            color = np.asanyarray(color_frame.get_data())

            m, lv, pts, colors, obs_f, obs_l = scene.process(depth, color)

            n += 1
            if time.monotonic() - t0 >= 1.0:
                fps, n, t0 = n / (time.monotonic() - t0), 0, time.monotonic()
            obstacle = "BLIND" if m.blind else ("clear" if m.distance_m is None else f"{m.distance_m:.2f} m")
            text = lane_text(lv) + [f"Obstacle in path: {obstacle}",
                    f"black below {scene.lanes.dark_threshold:.0f}/255   {fps:.0f} fps"]

            cam = np.hstack([draw_camera(color, lv, scene.lanes, text), draw_birdseye(lv, scene.lanes, obs_f, obs_l)])
            img3d = view.render(pts, colors, lv.lane, ["drag = rotate, wheel = zoom", "1 behind  2 top  3 side  R reset"])
            cv2.imshow("Navya camera", cam)
            cv2.imshow("Navya 3D", img3d)

            key = chr(cv2.waitKey(1) & 0xFF).lower()
            if key == "q":
                break
            if key in OrbitView.PRESETS:
                view.preset(key)
            elif key == "r":
                view.preset("1")
            elif key == "s":
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                cv2.imwrite(str(CAPTURE_DIR / f"navya_{stamp}_camera.png"), cam)
                cv2.imwrite(str(CAPTURE_DIR / f"navya_{stamp}_3d.png"), img3d)
                write_ply(CAPTURE_DIR / f"navya_{stamp}.ply", pts, colors)
                print(f"Saved snapshot navya_{stamp} in {CAPTURE_DIR}")
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
