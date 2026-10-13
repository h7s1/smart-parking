@echo off
title Smart Parking website
cd /d "%~dp0"

rem Find the Python environment: .venv inside this folder, or next to it.
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Could not find the .venv folder. Follow "Run it" in README.md first.
  echo.
  pause
  exit /b 1
)

echo Starting the Smart Parking website at https://localhost:5000
echo Keep this window open while you use the website. Close it to stop the website.
echo.

rem Open the browser after the server has had a few seconds to start.
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'https://localhost:5000'"

"%PY%" run.py
echo.
pause
