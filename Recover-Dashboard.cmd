@echo off
setlocal EnableExtensions
title Recover Argus Dashboard
echo.
echo === Recover Argus Dashboard ===
echo Use this when the browser shows "refused to connect".
echo It starts the local dashboard on port 3000.
echo.

set "ROOT=%~dp0"
set "SCRIPT=%ROOT%scripts\control-center\start-dashboard-only.ps1"

if not exist "%SCRIPT%" (
  echo Missing recovery script. Use Start-Argus.cmd instead.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
if errorlevel 1 (
  echo.
  echo Recovery failed. Try Start-Argus.cmd instead.
  pause
  exit /b 1
)

echo.
echo Open: http://127.0.0.1:3000/today
start "" "http://127.0.0.1:3000/today"
pause
