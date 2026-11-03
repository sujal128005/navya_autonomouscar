@echo off
rem Drive the car with the Jetson, from the laptop: double-click this file.
rem The laptop and the Jetson must be on the same Wi-Fi (a phone hotspot or the laptop's
rem Mobile hotspot - not college Wi-Fi). The Navya menu then runs on the Jetson, and the
rem dashboard opens in the laptop's browser as soon as a drive or viewer starts.
setlocal
title Navya on the Jetson
cd /d "%~dp0"

echo.
echo  Looking for the Jetson on this Wi-Fi...
set JIP=
for /f "tokens=2 delims==" %%i in ('python jetson\find_jetson.py') do set JIP=%%i
if "%JIP%"=="" (
    echo.
    pause
    exit /b 1
)
echo  Jetson at %JIP%. The dashboard opens by itself at http://%JIP%:8080
echo.

rem Open the dashboard in the browser once it is up (gives up after about 30 minutes).
start "" /b powershell -NoProfile -WindowStyle Hidden -Command ^
  "for ($i = 0; $i -lt 900; $i++) { $c = New-Object Net.Sockets.TcpClient; try { $c.Connect('%JIP%', 8080); $c.Close(); Start-Process 'http://%JIP%:8080'; break } catch { Start-Sleep 2 } }"

rem Latest code from GitHub (skipped quietly without internet), then the menu.
ssh -t jetson "cd ~/navya_autonomouscar && timeout 15 git pull -q; ./navya.sh"
