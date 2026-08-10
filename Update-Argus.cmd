@echo off
setlocal EnableExtensions
title Update Argus from GitHub
echo.
echo === Update Argus (nuclear) ===
echo Hard-resets this folder to GitHub main, then Starts Argus.
echo Use when Home Build stays stuck on an old stamp after cloud merges.
echo.

set "ROOT=%~dp0"
set "UPDATER=%ROOT%scripts\control-center\update-argus-now.ps1"

if not exist "%UPDATER%" (
  echo Local updater missing — downloading from GitHub...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "irm \"https://raw.githubusercontent.com/brandoncorley01/Argus/main/scripts/control-center/update-argus-now.ps1?$(Get-Random)\" | iex"
  if errorlevel 1 (
    echo Update failed.
    pause
    exit /b 1
  )
  goto :done
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%UPDATER%"
if errorlevel 1 (
  echo.
  echo Update failed. Read the messages above.
  pause
  exit /b 1
)

:done
echo.
echo === Update finished ===
echo Hard-refresh Home (Ctrl+F5). Build must match Desktop Argus-update-report.txt
echo.
start "" "http://127.0.0.1:3000/today"
echo Window closes in 12 seconds (or press a key)...
timeout /t 12 >nul
exit /b 0
