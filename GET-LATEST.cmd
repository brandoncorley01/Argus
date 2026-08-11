@echo off
setlocal EnableExtensions
title Get Latest Argus from GitHub
echo.
echo === GET LATEST ARGUS ===
echo 1) Prove which PC folder Home uses (Desktop Argus-folder-report.txt)
echo 2) Hard-reset that folder from GitHub main (API, not CDN)
echo Use when Home Build is stuck (e.g. v2.40).
echo.
echo TARGET should become live-monitor-v2.51 or newer.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/diagnose-argus-folder.ps1?ref=main')"
echo.
echo --- Updating ACTIVE folder from GitHub ---
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/update-argus-now.ps1?ref=main')"
set "ERR=%ERRORLEVEL%"

echo.
if not "%ERR%"=="0" (
  echo UPDATE FAILED. Open Desktop Argus-folder-report.txt and Argus-update-report.txt
  pause
  exit /b %ERR%
)

echo UPDATE OK. Hard-refresh Home: Ctrl+F5
echo Confirm Build is live-monitor-v2.51 or newer.
echo.
start "" "http://127.0.0.1:3000/today"
timeout /t 12 >nul
exit /b 0
