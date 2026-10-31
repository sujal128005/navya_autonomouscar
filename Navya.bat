@echo off
rem Navya launcher: double-click this file (or a desktop shortcut to it) for a menu.
setlocal
title Navya
cd /d "%~dp0autopilot"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3 and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

:menu
cls
echo.
echo   ===========  N A V Y A  ===========
echo.
echo    1  Pre-flight check
echo.
echo    2  Drive          (watch on phone)
echo    3  Drive + object detection + record trip
echo    4  Drive + lane following (steering)
echo    5  Drive with everything (detection, steering, record)
echo    L  Drive + LiDAR  (LiDAR plugged into the laptop)
echo    6  Camera test    (no Arduino, car never moves)
echo.
echo    7  Corridor viewer (3D map and lane)
echo    8  Object detection viewer
echo    9  LiDAR radar view
echo.
echo    C  Calibrate camera        S  Calibrate steering
echo    R  Report of the last trip T  Run the logic tests
echo    Q  Quit
echo.
choice /c 123456789CSRTLQ /n /m "  Choose: "
set pick=%errorlevel%
echo.
if %pick%==1  call :run preflight.py
if %pick%==2  call :drive --phone
if %pick%==3  call :drive --phone --vision --record
if %pick%==4  call :drive --phone --steer
if %pick%==5  call :drive --phone --vision --steer --record
if %pick%==6  call :run navya_autopilot.py --dry-run --phone --show
if %pick%==7  call :run corridor_view.py
if %pick%==8  call :run vision_view.py --phone
if %pick%==9  call :run lidar_view.py --phone
if %pick%==10 call :run calibrate_camera.py --write
if %pick%==11 call :run steering_calibrate.py
if %pick%==12 call :run trip_report.py
if %pick%==13 call :run test_logic.py
if %pick%==14 call :drive --phone --lidar
if %pick%==15 exit /b 0
goto menu

:drive
rem Every drive starts with the pre-flight check; a failed check asks before going on.
python preflight.py
if errorlevel 1 (
    echo.
    choice /c YN /n /m "  Pre-flight check FAILED. Drive anyway? [Y/N] "
    if errorlevel 2 exit /b 0
)
echo.
echo  Phone: join the laptop's hotspot, open http://192.168.137.1:8080
echo  Car moves only with CH5 in AUTO. Right stick back = stop. Q here = quit.
echo.
python navya_autopilot.py %*
echo.
pause
exit /b 0

:run
python %*
echo.
pause
exit /b 0
