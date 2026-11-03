#!/usr/bin/env bash
# NVIDIA's JetPack kernel has no driver for the CH340/CH341 USB-serial chip on our Arduino Uno
# clone (CONFIG_USB_SERIAL_CH341 is not set), so the Arduino gets no /dev/ttyUSB port.
# This builds the standard Linux ch341 driver for the running kernel and installs it.
#     bash jetson/build_ch341.sh
# Run it again after a JetPack/kernel update. Needs: nvidia-l4t-kernel-headers, gcc, make.
set -euo pipefail

KVER=$(uname -r)                        # e.g. 5.15.148-tegra
BASE=${KVER%%-*}                        # e.g. 5.15.148 (the matching kernel.org stable release)
SRC_URL="https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/plain/drivers/usb/serial/ch341.c?h=v$BASE"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

if lsmod | grep -q '^ch341 '; then
    echo "ch341 driver already loaded."
    exit 0
fi
[ -d "/lib/modules/$KVER/build" ] || { echo "Kernel headers missing: sudo apt install nvidia-l4t-kernel-headers"; exit 1; }

echo "Downloading ch341.c for Linux $BASE ..."
curl -fsSL "$SRC_URL" -o "$WORK/ch341.c"
echo 'obj-m += ch341.o' > "$WORK/Makefile"
make -s -C "/lib/modules/$KVER/build" M="$WORK" modules
modinfo "$WORK/ch341.ko" | grep -E '^(vermagic|description)'

echo "Installing (asks for the Jetson password) ..."
sudo install -D -m 644 "$WORK/ch341.ko" "/lib/modules/$KVER/updates/ch341.ko"
sudo depmod -a
sudo modprobe ch341
echo "ch341 driver installed and loaded; it loads by itself from now on."
ls /dev/ttyUSB* 2>/dev/null || true
