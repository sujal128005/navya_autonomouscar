"""Summarise a recorded trip: a chart of what the car saw and did, plus key numbers.

    python trip_report.py                 # the newest trip
    python trip_report.py <trip folder>   # a particular trip

Writes report.png into the trip folder and prints a summary.
"""

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config
from trip_recorder import LOCAL_DIR, removable_drives

STATE_COLORS = {"CLEAR": "#c8e6c9", "SLOWING": "#fff59d", "STOPPED": "#ffcdd2", "RESUMING": "#ffe0b2",
                "STOP_SIGN": "#e1bee7", "PAUSED": "#cfd8dc", "IDLE": "#eeeeee"}


def newest_trip() -> Path | None:
    roots = [d / "navya_trips" for d in removable_drives()] + [LOCAL_DIR]
    if config.RECORD_DIR != "auto":
        roots.insert(0, Path(config.RECORD_DIR))
    trips = [t for r in roots if r.exists() for t in r.glob("trip_*") if (t / "telemetry.csv").exists()]
    return max(trips, key=lambda t: t.name) if trips else None


def load(trip: Path):
    with open(trip / "telemetry.csv", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarise(rows) -> list[str]:
    t = [float(r["t"]) for r in rows]
    duration = t[-1] - t[0] if len(t) > 1 else 0.0
    state_time: dict[str, float] = {}
    stops, sign_stops = 0, 0
    for prev, cur, t0, t1 in zip(rows, rows[1:], t, t[1:]):
        state_time[prev["state"]] = state_time.get(prev["state"], 0.0) + (t1 - t0)
        if cur["state"] == "STOPPED" and prev["state"] != "STOPPED":
            stops += 1
        if cur["state"] == "STOP_SIGN" and prev["state"] != "STOP_SIGN":
            sign_stops += 1
    seen = [num(r["obstacle_m"]) for r in rows if num(r["obstacle_m"]) is not None]
    auto = sum(dt for s, dt in state_time.items() if s not in ("IDLE", "PAUSED"))
    lines = [f"Duration {duration:.0f} s, driving itself for {auto:.0f} s",
             f"Obstacle stops: {stops}, stop-sign stops: {sign_stops}",
             f"Closest obstacle seen: {min(seen):.2f} m" if seen else "No obstacles seen"]
    lines += [f"  {s:9} {dt:6.1f} s" for s, dt in sorted(state_time.items(), key=lambda kv: -kv[1])]
    return lines


def chart(rows, trip: Path, lines: list[str]) -> Path:
    t = [float(r["t"]) for r in rows]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    for axis in (ax1, ax2):  # shade the background by driving state
        start = 0
        for i in range(1, len(rows) + 1):
            if i == len(rows) or rows[i]["state"] != rows[start]["state"]:
                axis.axvspan(t[start], t[min(i, len(t) - 1)], color=STATE_COLORS.get(rows[start]["state"], "#ffffff"),
                             lw=0)
                start = i
    ax1.plot(t, [num(r["obstacle_m"]) for r in rows], ".", ms=3, color="#c62828", label="obstacle distance")
    ax1.axhline(config.STOP_DIST_M, color="#c62828", ls="--", lw=1, label=f"stop at {config.STOP_DIST_M} m")
    ax1.axhline(config.SLOW_DOWN_DIST_M, color="#f9a825", ls="--", lw=1, label=f"slow from {config.SLOW_DOWN_DIST_M} m")
    ax1.set_ylabel("metres")
    ax1.set_ylim(0, config.DETECT_MAX_M + 0.5)
    ax1.legend(loc="upper right", fontsize=8)
    ax1.set_title(f"{trip.name}: " + lines[0])
    ax2.plot(t, [num(r["speed_left"]) for r in rows], color="#1565c0", label="speed command")
    ax2.set_ylabel("speed (0-1000)")
    ax2.set_xlabel("seconds")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in STATE_COLORS.values()]
    ax2.legend(handles, STATE_COLORS.keys(), loc="upper right", fontsize=7, ncol=4)
    fig.tight_layout()
    out = trip / "report.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def main():
    trip = Path(sys.argv[1]) if len(sys.argv) > 1 else newest_trip()
    if not trip or not (trip / "telemetry.csv").exists():
        print("No recorded trip found. Record one with: python navya_autopilot.py --record")
        return 1
    rows = load(trip)
    if len(rows) < 2:
        print(f"{trip} has no telemetry yet.")
        return 1
    lines = summarise(rows)
    print(f"Trip {trip}")
    print("\n".join(lines))
    print("Chart:", chart(rows, trip, lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
