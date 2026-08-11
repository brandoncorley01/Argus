@echo off
setlocal EnableExtensions
title Get Latest Argus from GitHub
echo.
echo === GET LATEST ARGUS ===
echo Downloads updater via GitHub API (not CDN) and hard-resets to main.
echo Use when Home Build is stuck (e.g. v2.40).
echo.
echo TARGET should become live-monitor-v2.46 or newer.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/update-argus-now.ps1?ref=main')"
set "ERR=%ERRORLEVEL%"

echo.
if not "%ERR%"=="0" (
  echo UPDATE FAILED. Open Desktop Argus-update-report.txt
  pause
  exit /b %ERR%
)

echo UPDATE OK. Hard-refresh Home: Ctrl+F5
echo Confirm Build is live-monitor-v2.46 or newer.
echo.
start "" "http://127.0.0.1:3000/today"
timeout /t 12 >nul
exit /b 0
