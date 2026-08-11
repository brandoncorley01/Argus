@echo off
setlocal EnableExtensions
title FIX PC Argus — Desktop only
echo.
echo === FIX PC ARGUS ===
echo Canonical folder: %%USERPROFILE%%\Desktop\Argus  (NOT OneDrive)
echo.
echo TARGET after success: live-monitor-v2.54 or newer
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/update-argus-now.ps1?ref=main')"
set "ERR=%ERRORLEVEL%"

echo.
echo Opening %%USERPROFILE%%\Desktop reports...
if exist "%USERPROFILE%\Desktop\Argus-update-report.txt" start "" "%USERPROFILE%\Desktop\Argus-update-report.txt"
if exist "%USERPROFILE%\Desktop\Argus-folder-report.txt" start "" "%USERPROFILE%\Desktop\Argus-folder-report.txt"
start "" "http://127.0.0.1:3000/argus-build.txt"
start "" "http://127.0.0.1:3000/today"

if not "%ERR%"=="0" (
  echo.
  echo UPDATE FAILED. Read %%USERPROFILE%%\Desktop\Argus-update-report.txt
  pause
  exit /b %ERR%
)

echo.
echo UPDATE OK. Hard-refresh Home: Ctrl+F5
echo Confirm Build is live-monitor-v2.54
echo Folder must be: %%USERPROFILE%%\Desktop\Argus
echo.
timeout /t 15 >nul
exit /b 0
