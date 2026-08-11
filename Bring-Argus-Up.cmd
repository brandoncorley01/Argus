@echo off
setlocal EnableExtensions
title Bring Argus Up
echo.
echo === BRING ARGUS UP ===
echo Finds or clones Argus, then Start (Docker must be running).
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/bring-argus-up.ps1?ref=main')"
set "ERR=%ERRORLEVEL%"
echo.
if not "%ERR%"=="0" (
  echo Bring-up failed. Open Docker Desktop, then try again.
  echo Report: Argus-bringup-report.txt on Desktop / OneDrive Desktop
  pause
  exit /b %ERR%
)
echo OK. Opening Home...
start "" "http://127.0.0.1:3000/today"
timeout /t 8 >nul
exit /b 0
