"""Object detection for Navya: YOLO11n on the colour image, distance from the depth camera."""

import os

os.environ.setdefault("YOLO_OFFLINE", "1")  # no update checks or usage reporting from Ultralytics

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

import config
from obstacle import Intrinsics

MODELS = Path(__file__).with_name("models")
MODEL_PATH = MODELS / "yolo11n.pt"


def pick_backend() -> tuple[Path, str | None, str]:
    """Fastest model this laptop can run: (model path, predict device, description).
    The ONNX/OpenVINO copies are made by export_models.py; the .pt is the fallback."""
    choice = config.DETECT_BACKEND
    openvino_dir = MODELS / "yolo11n_openvino_model"
    if choice in ("auto", "openvino") and openvino_dir.exists():
        try:
            import openvino
            if "GPU" in openvino.Core().available_devices:
                return openvino_dir, "intel:gpu", "OpenVINO on the Intel GPU"
        except ImportError:
            pass
    onnx_file = MODELS / "yolo11n.onnx"
    if choice in ("auto", "onnx") and onnx_file.exists():
        try:
            import onnxruntime  # noqa: F401
            return onnx_file, None, "ONNX Runtime on the CPU"
        except ImportError:
            pass
    return MODEL_PATH, None, "PyTorch on the CPU (slowest; run export_models.py)"


@dataclass
class Detection:
    label: str
    confidence: float
    box: tuple[int, int, int, int]      # x1, y1, x2, y2 in colour pixels
    distance_m: float | None = None     # straight-ahead distance from the camera
    lateral_m: float | None = None      # + = right of the camera


def box_distance(depth_raw: np.ndarray, depth_scale: float, box, intr: Intrinsics):
    """Distance to the object in a box: the nearer part of its middle, so background
    showing around the object (or between a person's legs) does not count."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    patch = depth_raw[y1 + h // 4: y2 - h // 4, x1 + w // 4: x2 - w // 4]
    z = patch[patch > 0] * depth_scale
    if z.size < 20:
        return None, None
    distance = float(np.percentile(z, 25))
    lateral = ((x1 + x2) / 2 - intr.ppx) / intr.fx * distance
    return distance, float(lateral)


class ObjectDetector:
    def __init__(self):
        import torch
        from ultralytics import YOLO   # imported here: slow to load, and only needed for detection

        torch.set_num_threads(config.DETECT_THREADS)
        model_path, self.device, self.backend = pick_backend()
        print(f"Object detection: {self.backend}")
        self.model = YOLO(str(model_path), task="detect")
        self.names = self.model.names
        wanted = set(config.DETECT_CLASSES)
        self.classes = [i for i, n in self.names.items() if not wanted or n in wanted]

    def detect(self, color_bgr, depth_raw=None, depth_scale=0.001, intr: Intrinsics | None = None) -> list[Detection]:
        result = self.model.predict(color_bgr, conf=config.DETECT_CONFIDENCE, imgsz=config.DETECT_IMAGE_SIZE,
                                    classes=self.classes, device=self.device, verbose=False)[0]
        boxes = result.boxes
        detections = []
        for xyxy, conf, cls in zip(boxes.xyxy.cpu().numpy(), boxes.conf.cpu().numpy(), boxes.cls.cpu().numpy()):
            d = Detection(self.names[int(cls)], float(conf), tuple(int(v) for v in xyxy))
            if depth_raw is not None and intr is not None:
                d.distance_m, d.lateral_m = box_distance(depth_raw, depth_scale, d.box, intr)
            detections.append(d)
        detections.sort(key=lambda d: (d.distance_m is None, d.distance_m or 0.0))
        return detections


def describe(d: Detection) -> str:
    if d.distance_m is None:
        return f"{d.label} {d.confidence:.0%}"
    side = "ahead" if abs(d.lateral_m) < 0.3 else ("right" if d.lateral_m > 0 else "left")
    return f"{d.label} {d.distance_m:.1f} m {side}"


def draw(img: np.ndarray, detections: list[Detection]) -> np.ndarray:
    for d in detections:
        hue = sum(map(ord, d.label)) * 37 % 180   # same colour per label on every run
        color = tuple(int(c) for c in cv2.cvtColor(np.uint8([[[hue, 200, 255]]]), cv2.COLOR_HSV2BGR)[0, 0])
        x1, y1, x2, y2 = d.box
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        text = describe(d)
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        ty = max(y1, th + 6)
        cv2.rectangle(img, (x1, ty - th - 6), (x1 + tw + 6, ty), color, -1)
        cv2.putText(img, text, (x1 + 3, ty - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
    return img
