"""Build docs/Navya_wiring_16x9.png: every connection on the car in one 16:9 image (3840 x 2160).

    python docs/wiring/make_wiring_image.py

Pins follow firmware v2 (firmware/navya_drive/navya_drive.ino). Signal wires are drawn in
their real colours. Dashed = not wired yet. Edit this file when the wiring changes.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).resolve().parent.parent / "Navya_wiring_16x9.png"

RED, BLACK, BLUE, GREEN = "#d32f2f", "#212121", "#1565c0", "#2e7d32"
PURPLE, SILVER, YELLOW, ORANGE, GREY = "#8e24aa", "#8d9ba3", "#e6a700", "#ef6c00", "#757575"
FILL = {"power": "#ffebee", "drive": "#fff8e1", "control": "#e3f2fd", "compute": "#e8f5e9",
        "sensor": "#f3e5f5", "planned": "#fff3e0", "other": "#f5f5f5"}

fig = plt.figure(figsize=(16, 9), facecolor="white")
ax = fig.add_axes((0.012, 0.012, 0.976, 0.905))
ax.set_xlim(0, 160)
ax.set_ylim(0, 90)
ax.axis("off")
fig.text(0.016, 0.955, "Navya - complete wiring", fontsize=23, weight="bold", color="#212121")
fig.text(0.016, 0.93, "Setup as of 4 Nov 2026: two LiPos, one per controller. Signal wires are shown in "
                      "their real colours. Dashed = not wired yet.", fontsize=11.5, color="#555555")


def box(x, y, w, h, title=None, lines=(), kind="other", dashed=False, title_x=None, size=12):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.8", zorder=2,
                                fc=FILL[kind], ec=ORANGE if dashed else "#424242",
                                lw=1.5, ls="--" if dashed else "-"))
    cx = x + w / 2 if title_x is None else title_x
    if title:
        ax.text(cx, y + h - 0.9, title, ha="center", va="top", fontsize=size, weight="bold", zorder=4)
    for i, line in enumerate(lines):
        ax.text(cx, y + h - 4.1 - 2.3 * i, line, ha="center", va="top", fontsize=9.2,
                color="#424242", zorder=4)


def wire(points, color, lw=2.6, ls="-"):
    xs, ys = zip(*points)
    ax.plot(xs, ys, color=color, lw=lw, ls=ls, zorder=1, solid_capstyle="round")


def label(x, y, text, color="#424242", size=9.2, ha="center", va="center", weight="normal", rotation=0):
    ax.text(x, y, text, color=color, fontsize=size, ha=ha, va=va, weight=weight, rotation=rotation,
            zorder=5, bbox=dict(fc="white", ec="none", pad=1.0, alpha=1.0))


def text(x, y, s, color="#212121", size=9.6, ha="left", weight="normal"):
    ax.text(x, y, s, color=color, fontsize=size, ha=ha, va="center", weight=weight, zorder=4)


def dot(x, y, color=BLACK):
    ax.plot([x], [y], "o", color=color, ms=7, zorder=3)


# ---------------------------------------------------------------- Arduino
AX0, AX1 = 34, 52
box(AX0, 8, AX1 - AX0, 74, kind="control")
ax.text(43, 53, "Arduino\nUno", ha="center", va="center", fontsize=16, weight="bold", zorder=4)
ax.text(43, 46.5, "firmware v2\n250000 baud", ha="center", va="center", fontsize=9.6,
        color="#424242", zorder=4)

# ---------------------------------------------------------------- radio
box(2, 81.5, 22, 7, "FS-CT6B transmitter", kind="other", size=11)
ax.text(13, 83.5, "SWA down", ha="center", va="center", fontsize=9.2, color="#424242", zorder=4)
wire([(13, 81.5), (13, 79.5)], GREY, lw=2, ls=":")
box(2, 57.5, 22, 22, "FS-R6B receiver", kind="control", size=11)
for y, ch, pin, color in ((73.5, "CH5  MANUAL / AUTO", "D2", BLUE), (70, "CH2  throttle, stop", "D3", BLUE),
                          (66.5, "CH1  steering", "D4", BLUE), (63, "+  power in", "5V", RED),
                          (59.5, "-  ground", "GND", BLACK)):
    wire([(24, y), (AX0, y)], color)
    text(3, y, ch)
    text(AX0 + 0.8, y, pin, weight="bold")

# ---------------------------------------------------------------- steering + battery monitor (planned)
box(2, 36, 22, 18.5, "BTS7960 steering driver", kind="planned", dashed=True, size=10)
for y, name, pin in ((49.5, "RPWM", "D5"), (46, "LPWM", "D6"), (42.5, "R_EN + L_EN", "A3")):
    wire([(24, y), (AX0, y)], ORANGE, ls="--")
    text(3, y, name)
    text(AX0 + 0.8, y, pin, weight="bold")
text(3, 38.4, "toy motor, 12 V battery, 10 A fuse", size=8.2, color="#555555")

box(2, 21, 22, 13.5, "Pot and limit switches", kind="planned", dashed=True, size=10.5)
for y, name, pin in ((29.8, "Pot middle pin", "A0"), (26.3, "Left limit to GND", "A1"), (22.8, "Right limit to GND", "A2")):
    wire([(24, y), (AX0, y)], ORANGE, ls="--")
    text(3, y, name)
    text(AX0 + 0.8, y, pin, weight="bold")

box(2, 8, 22, 11.5, "Battery monitor", kind="planned", dashed=True, size=10.5)
for y, name, pin in ((14.8, "Left LiPo divider", "A4"), (11.6, "Right LiPo divider", "A5")):
    wire([(24, y), (AX0, y)], ORANGE, ls="--")
    text(3, y, name)
    text(AX0 + 0.8, y, pin, weight="bold")
text(3, 9.3, "LiPo + -47k- pin -10k- GND", size=8.2, color="#555555")

# ---------------------------------------------------------------- controllers
CX0, CX1 = 78, 96


def controller(side, top, rows, black_y, notes_y):
    box(CX0, notes_y - 3.6, CX1 - CX0, top - notes_y + 3.6, f"YL-12 {side}", kind="drive")
    for y, name, pin, color, ls, what in rows:
        wire([(AX1, y), (CX0, y)], color, lw=3.2, ls=ls)
        text(AX1 - 0.8, y, pin, ha="right", weight="bold")
        text(CX0 + 0.8, y, name)
        label(62, y, what, color=color if color != SILVER else "#5f6d75", weight="bold")
    wire([(70, black_y), (CX0, black_y)], BLACK, lw=3.2)
    dot(70, black_y)
    text(CX0 + 0.8, black_y, "Black wires (GND)")
    text(CX0 + 0.8, notes_y, "Orange 5 V wire: leave free", size=8.4, color="#555555")
    text(CX0 + 0.8, notes_y - 2, "2nd brake plug: leave free", size=8.4, color="#555555")


controller("LEFT", 84, [(78.5, "Throttle: purple", "D9", PURPLE, "-", "throttle"),
                        (74, "F/R: silver", "D8", SILVER, "-", "forward / reverse"),
                        (69.5, "Brake: yellow", "D11", YELLOW, "--", "brake (after checks)")], 65, 60)
controller("RIGHT", 39.6, [(29.5, "Throttle: purple", "D10", PURPLE, "-", "throttle"),
                         (25, "F/R: silver", "D7", SILVER, "-", "forward / reverse"),
                         (20.5, "Brake: yellow", "D12", YELLOW, "--", "brake (after checks)")], 34, 15.5)

# shared ground: Arduino GND to the black wires of both controllers
wire([(70, 65), (70, 34)], BLACK, lw=3.2)
wire([(AX1, 49.5), (70, 49.5)], BLACK, lw=3.2)
dot(70, 49.5)
text(AX1 - 0.8, 49.5, "GND", ha="right", weight="bold")
label(62, 49.5, "shared ground", color=BLACK, weight="bold")

box(CX0 - 2, 41.5, CX1 - CX0 + 4, 12, "Brake plug", kind="other", size=10.5)
ax.text(87, 47, "Yellow = signal, black = GND.\nCheck with a multimeter first.\nPull to GND = brake.",
        ha="center", va="center", fontsize=8.8, color="#424242", zorder=4)

# ---------------------------------------------------------------- batteries and motors
PX0, PX1 = 102, 118
box(PX0, 71, PX1 - PX0, 13, "LiPo LEFT", ["6S 22.2 V 5200 mAh", "25.2 V full, 21 V empty"], "power")
box(PX0, 54, PX1 - PX0, 13, "Hub motor LEFT", ['8" BLDC 24 V 350 W', "3 phases + hall wires"], "drive", size=11)
box(PX0, 27, PX1 - PX0, 13, "Hub motor RIGHT", ['8" BLDC 24 V 350 W', "3 phases + hall wires"], "drive", size=11)
box(PX0, 10, PX1 - PX0, 13, "LiPo RIGHT", ["6S 22.2 V 5200 mAh", "25.2 V full, 21 V empty"], "power")

for y_plus, y_minus, y_motor in ((79, 75, 60), (19, 15, 33.5)):
    wire([(CX1, y_plus), (PX0, y_plus)], RED, lw=3.4)
    wire([(CX1, y_minus), (PX0, y_minus)], BLACK, lw=3.4)
    wire([(CX1, y_motor), (PX0, y_motor)], GREEN, lw=4.2)
    label(99, y_plus + 1.5, "+", color=RED, size=12, weight="bold")
    label(99, y_minus - 1.5, "-", color=BLACK, size=12, weight="bold")

# joined battery negatives
wire([(PX1, 75), (121, 75), (121, 15), (PX1, 15)], BLACK, lw=3.4)
label(119.6, 47, "negatives joined", color=BLACK, size=9.2, weight="bold", rotation=90)

# ---------------------------------------------------------------- Jetson and what plugs into it
JX0, JX1 = 127, 141
box(JX0, 26, JX1 - JX0, 38, "Jetson\nOrin Nano", kind="compute", size=14)
ax.text(134, 46, "autopilot\nobject detection\ndashboard :8080", ha="center", va="center",
        fontsize=9.6, color="#424242", zorder=4)

box(JX0, 72, JX1 - JX0, 13, "Laptop", ["screen + menu", "Navya Jetson.bat"], "other")
wire([(134, 72), (134, 64)], GREY, lw=2.2, ls=":")
label(134, 68, "Wi-Fi", color=GREY, weight="bold")

SX0, SX1 = 147, 158.5
box(SX0, 68, SX1 - SX0, 16, "RealSense\nD435i", ["", "plain cable,", "no dock"], "sensor", size=10.5)
box(SX0, 47, SX1 - SX0, 13, "LiDAR D500", ["CP2102 USB", "adapter"], "sensor", size=10.5)
box(SX0, 31, SX1 - SX0, 12.5, "Samsung T7", ["1 TB SSD", "/mnt/t7ssd"], "compute", size=10.5)
wire([(JX1, 60), (144, 60), (144, 76), (SX0, 76)], GREEN, lw=3)
wire([(JX1, 54), (SX0, 54)], GREEN, lw=3)
wire([(JX1, 37.5), (SX0, 37.5)], GREEN, lw=3)
label(144, 39.7, "USB-C", color=GREEN, size=8.6, weight="bold")
label(144, 56.2, "USB", color=GREEN, size=8.6, weight="bold")
label(144, 68, "USB 3", color=GREEN, size=8.6, weight="bold", rotation=90)

# Arduino USB, along the bottom edge to the Jetson
wire([(43, 8), (43, 3), (144, 3), (144, 30), (JX1, 30)], GREEN, lw=3)
label(90, 3, "Arduino USB to Jetson (data + Arduino power)", color=GREEN, weight="bold")

# Jetson power
box(JX0, 6.5, JX1 - JX0, 14, "Jetson power", ["now: 19 V adapter", "planned: 5 A fuse", "+ 12 V step-down"], "planned", dashed=True, size=10.5)
wire([(134, 20.5), (134, 26)], RED, lw=3)
label(134, 23.2, "barrel jack 9-20 V", color=RED, size=8.6, weight="bold")
wire([(PX1, 81), (123.5, 81), (123.5, 15), (JX0, 15)], ORANGE, lw=2.6, ls="--")
wire([(121, 15), (121, 10), (JX0, 10)], ORANGE, lw=2.6, ls="--")
label(125.2, 47, "planned: + from LEFT LiPo", color=ORANGE, size=9, weight="bold", rotation=90)

# ---------------------------------------------------------------- legend
lx, ly = 147, 26.5
ax.text(lx, ly + 0.2, "Wire key", fontsize=10.5, weight="bold", va="center", zorder=4)
for i, (color, ls, name) in enumerate([(RED, "-", "Power +"), (BLACK, "-", "Ground / -"),
                                       (BLUE, "-", "Radio signal"), (GREEN, "-", "USB / motor"),
                                       (GREY, ":", "Wireless"), (ORANGE, "--", "Planned")]):
    y = ly - 2.8 - 2.9 * i
    ax.plot([lx, lx + 3.4], [y, y], color=color, lw=2.8, ls=ls, zorder=4)
    ax.text(lx + 4.2, y, name, fontsize=9.6, va="center", zorder=4)

fig.savefig(OUT, dpi=240, facecolor="white")
print(OUT)
