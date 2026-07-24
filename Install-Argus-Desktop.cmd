@echo off
setlocal EnableExtensions
title Install Argus Desktop Shortcuts
echo.
echo === Argus desktop installer ===
echo Puts Start Argus and Stop Argus on your Desktop.
echo No browser needed.
echo.

rem This file lives at the Argus repo root.
set "ROOT=%~dp0"
set "INSTALLER=%ROOT%scripts\control-center\install-desktop-shortcuts.ps1"

if not exist "%INSTALLER%" (
  echo Could not find:
  echo   %INSTALLER%
  echo.
  echo Make sure this file is inside your Argus folder.
  pause
  exit /b 1
)

echo Found Argus at:
echo   %ROOT%
echo.
echo Installing shortcuts...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%INSTALLER%"
if errorlevel 1 (
  echo.
  echo Install failed.
  pause
  exit /b 1
)

echo.
echo Done. On your Desktop you should see:
echo   Start Argus
echo   Stop Argus
echo   Open Argus
echo   End Trading Day
echo.
echo Next: double-click Start Argus, then open the dashboard.
echo.
pause
