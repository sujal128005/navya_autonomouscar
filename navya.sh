#!/usr/bin/env bash
# Navya launcher for Linux / the Jetson (same menu as Navya.bat):  ./navya.sh
cd "$(dirname "$0")/autopilot" || exit 1
# Navya's own Python environment (jetson/setup_jetson.sh), if there is one
[ -f ../.venv/bin/activate ] && . ../.venv/bin/activate

pause() { echo; read -r -n1 -s -p "  Press any key to go back to the menu " ; echo; }

run() { python3 "$@"; pause; }

drive() {
    # Every drive starts with the pre-flight check; a failed check asks before going on.
    if ! python3 preflight.py; then
        echo
        read -r -n1 -p "  Pre-flight check FAILED. Drive anyway? [y/N] " answer; echo
        [[ $answer == [yY] ]] || return
    fi
    echo
    echo "  Car moves only with CH5 in AUTO. Right stick back = stop. Q here = quit."
    echo
    python3 navya_autopilot.py "$@"
    pause
}

while true; do
    clear
    cat <<'EOF'

  ===========  N A V Y A  ===========

   1  Pre-flight check

   2  Drive          (watch on phone)
   3  Drive + object detection + record trip
   4  Drive + lane following (steering)
   5  Drive with everything (detection, steering, record)
   L  Drive + LiDAR  (LiDAR plugged in)
   6  Camera test    (no Arduino, car never moves)

   7  Corridor viewer (3D map and lane)
   8  Object detection viewer
   9  LiDAR radar view

   C  Calibrate camera        S  Calibrate steering
   R  Report of the last trip T  Run the logic tests
   Q  Quit

EOF
    read -r -n1 -p "  Choose: " pick || exit 0     # no keyboard any more (connection gone): quit
    echo; echo
    case "${pick,,}" in
        1) run preflight.py ;;
        2) drive --phone ;;
        3) drive --phone --vision --record ;;
        4) drive --phone --steer ;;
        5) drive --phone --vision --steer --record ;;
        l) drive --phone --lidar ;;
        6) run navya_autopilot.py --dry-run --phone --show ;;
        7) run corridor_view.py ;;
        8) run vision_view.py --phone ;;
        9) run lidar_view.py --phone ;;
        c) run calibrate_camera.py --write ;;
        s) run steering_calibrate.py ;;
        r) run trip_report.py ;;
        t) run test_logic.py ;;
        q) exit 0 ;;
    esac
done
