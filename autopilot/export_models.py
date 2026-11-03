"""Make the fast copies of the YOLO model (run once, and again after changing DETECT_IMAGE_SIZE).

    python export_models.py

Needs models/yolo11n.pt (see README). Creates:
  - on a Jetson: models/yolo11n.engine (TensorRT on the GPU, FP16; takes a few minutes);
  - elsewhere: models/yolo11n.onnx (ONNX Runtime, CPU) and models/yolo11n_openvino_model/
    (OpenVINO, runs on the Intel GPU; needs: pip install openvino).
A TensorRT engine only runs on the kind of device and TensorRT version that built it.
The detector then picks the fastest one by itself.
"""

import os
import sys

os.environ.setdefault("YOLO_OFFLINE", "1")
os.environ.setdefault("YOLO_AUTOINSTALL", "false")   # its auto-installs once upgraded numpy and broke torch

import config
from vision import MODEL_PATH


def main():
    from ultralytics import YOLO

    if not MODEL_PATH.exists():
        print(f"{MODEL_PATH} is missing - download it first (see README).")
        return 1
    model = YOLO(str(MODEL_PATH))
    try:
        import tensorrt  # noqa: F401
        import torch
        jetson = torch.cuda.is_available()
    except ImportError:
        jetson = False
    if jetson:
        # A failure here is shown, not hidden: falling back to ONNX would be much slower.
        print("TensorRT:", model.export(format="engine", imgsz=config.DETECT_IMAGE_SIZE, half=True,
                                        dynamic=False, device=0))
        return 0
    print("ONNX:", model.export(format="onnx", imgsz=config.DETECT_IMAGE_SIZE, simplify=True, dynamic=False))
    try:
        import openvino  # noqa: F401
        print("OpenVINO:", model.export(format="openvino", imgsz=config.DETECT_IMAGE_SIZE, half=False, dynamic=False))
    except ImportError:
        print("OpenVINO not installed (pip install openvino) - skipped; ONNX will be used.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
