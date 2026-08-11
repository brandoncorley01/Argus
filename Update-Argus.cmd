@echo off
setlocal EnableExtensions
title Update Argus from GitHub
echo.
echo === Update Argus (nuclear) ===
echo Hard-resets this folder to GitHub main via GitHub API (not CDN).
echo Use when Home Build stays stuck on an old stamp after cloud merges.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/update-argus-now.ps1?ref=main')"
if errorlevel 1 (
  echo.
  echo Update failed. Read Desktop Argus-update-report.txt
  pause
  exit /b 1
)

echo.
echo === Update finished ===
echo Hard-refresh Home (Ctrl+F5). Build must match Desktop Argus-update-report.txt
echo.
start "" "http://127.0.0.1:3000/today"
echo Window closes in 12 seconds (or press a key)...
timeout /t 12 >nul
exit /b 0
