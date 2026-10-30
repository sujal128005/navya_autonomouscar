"""Make the fast copies of the YOLO model (run once, and again after changing DETECT_IMAGE_SIZE).

    python export_models.py

Needs models/yolo11n.pt (see README). Creates models/yolo11n.onnx (ONNX Runtime, CPU) and
models/yolo11n_openvino_model/ (OpenVINO, runs on the Intel GPU; needs: pip install openvino).
The detector then picks the fastest one by itself.
"""

import os
import sys

os.environ.setdefault("YOLO_OFFLINE", "1")

import config
from vision import MODEL_PATH


def main():
    from ultralytics import YOLO

    if not MODEL_PATH.exists():
        print(f"{MODEL_PATH} is missing - download it first (see README).")
        return 1
    model = YOLO(str(MODEL_PATH))
    print("ONNX:", model.export(format="onnx", imgsz=config.DETECT_IMAGE_SIZE, simplify=True, dynamic=False))
    try:
        import openvino  # noqa: F401
        print("OpenVINO:", model.export(format="openvino", imgsz=config.DETECT_IMAGE_SIZE, half=False, dynamic=False))
    except ImportError:
        print("OpenVINO not installed (pip install openvino) - skipped; ONNX will be used.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
