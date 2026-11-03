#!/usr/bin/env bash
# Navya on a Jetson Orin Nano (JetPack 6.2 / L4T 36.4, Python 3.10). From the repo root:
#     bash jetson/setup_jetson.sh
# Creates .venv (Navya's own Python, so other projects' packages on this Jetson stay
# untouched) with the Jetson's GPU PyTorch, RealSense, ultralytics and the rest.
# It still sees the system TensorRT and CUDA (--system-site-packages).
set -euo pipefail
cd "$(dirname "$0")/.."

JETSON_INDEX=https://pypi.jetson-ai-lab.io/jp6/cu126   # NVIDIA's Jetson wheels for JetPack 6 / CUDA 12.6
RULES=/etc/udev/rules.d/99-realsense-libusb.rules

if dpkg-query -W -f='${Status}' brltty 2>/dev/null | grep -q "ok installed" ||! python3 -c "import ensurepip" 2>/dev/null || [ ! -f "$RULES" ]; then
    echo "Run this once first (it asks for the Jetson password):"
    echo "  sudo apt-get remove -y brltty && sudo apt-get install -y python3-venv && \\"
    echo "  sudo curl -fsSL https://raw.githubusercontent.com/IntelRealSense/librealsense/v2.59.1/config/99-realsense-libusb.rules -o $RULES && \\"
    echo "  sudo udevadm control --reload-rules"
    echo "(brltty grabs the Arduino's CH340 serial chip; the rule lets the camera work without sudo.)"
    exit 1
fi

[ -d .venv ] || python3 -m venv --system-site-packages .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -q -U pip
pip install -q torch==2.8.0 torchvision==0.23.0 --index-url "$JETSON_INDEX"
# The Jetson torch build needs numpy 1.x; OpenCV 4.12+ would pull in numpy 2.
pip install -q "numpy<2" "opencv-python<4.12" pyrealsense2 pyserial matplotlib ultralytics \
    "onnx>=1.12,<1.20" onnxslim   # for the TensorRT export, installed here so ultralytics doesn't

python - <<'EOF'
import cv2, numpy, pyrealsense2, serial, torch, ultralytics
print(f"torch {torch.__version__}, GPU: {torch.cuda.is_available()}"
      + (f" ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else " - NOT AVAILABLE"))
try:
    import tensorrt
    print(f"TensorRT {tensorrt.__version__}")
except ImportError:
    print("TensorRT: not visible - object detection falls back to slower PyTorch")
print(f"numpy {numpy.__version__}, OpenCV {cv2.__version__}, ultralytics {ultralytics.__version__}, "
      f"pyserial {serial.__version__}, RealSense cameras seen: {len(pyrealsense2.context().query_devices())}")
EOF
echo
echo "Done. Use it with:  source .venv/bin/activate"
