@echo off
setlocal EnableExtensions
title FIX PC Argus — diagnose + GitHub pull
echo.
echo === FIX PC ARGUS ===
echo Cloud agents save ONLY to GitHub. This repairs the ACTIVE Windows folder.
echo 1) Diagnose which folder Home uses
echo 2) Hard-reset that folder from GitHub main (API, not CDN)
echo 3) Open the live build stamp the browser sees
echo.
echo TARGET after success: live-monitor-v2.50 or newer
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/diagnose-argus-folder.ps1?ref=main')"
echo.
echo --- Updating ACTIVE folder from GitHub ---
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/update-argus-now.ps1?ref=main')"
set "ERR=%ERRORLEVEL%"

echo.
echo Opening Desktop reports + live stamp...
start "" "%USERPROFILE%\Desktop\Argus-folder-report.txt"
start "" "%USERPROFILE%\Desktop\Argus-update-report.txt"
start "" "http://127.0.0.1:3000/argus-build.txt"
start "" "http://127.0.0.1:3000/today"

if not "%ERR%"=="0" (
  echo.
  echo UPDATE FAILED. Read the two Desktop report files that just opened.
  pause
  exit /b %ERR%
)

echo.
echo UPDATE OK. Hard-refresh Home: Ctrl+F5
echo Confirm Build is live-monitor-v2.50 — and argus-build.txt matches.
echo.
timeout /t 15 >nul
exit /b 0
