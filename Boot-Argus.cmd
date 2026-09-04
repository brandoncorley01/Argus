@echo off
setlocal EnableExtensions
title Boot Argus
echo.
echo === HARD BOOT Argus ===
echo Simple start: Docker + API + worker + dashboard.
echo No GitHub sync. Live trading stays LOCKED.
echo Dashboard:  http://127.0.0.1:3000/today
echo.

set "ROOT=%~dp0"
set "BOOT=%ROOT%scripts\control-center\boot-argus.ps1"

if not exist "%BOOT%" (
  echo Could not find boot-argus.ps1
  echo Expected: %BOOT%
  pause
  exit /b 1
)

set "ARGUS_KEEP_DASHBOARD="
set "ARGUS_FORCE_SYNC="
set "ARGUS_START_SELF_UPDATED=1"
set "ARGUS_SKIP_START_SELF_UPDATE=1"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BOOT%"
if errorlevel 1 (
  echo.
  echo Boot failed. Open Docker Desktop if needed, then run Boot-Argus.cmd again.
  echo Log: %ROOT%runtime\control-center\boot-argus.log
  pause
  exit /b 1
)

echo.
echo === Boot finished ===
echo Open: http://127.0.0.1:3000/today
start "" "http://127.0.0.1:3000/today"
timeout /t 8 >nul
exit /b 0
