@echo off
setlocal EnableExtensions
title Update Argus Home
echo.
echo === Update Argus Home from GitHub ===
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/brandoncorley01/Argus/main/scripts/control-center/force-home-update.ps1 | iex"
if errorlevel 1 (
  echo.
  echo Update failed.
  pause
  exit /b 1
)

echo.
pause
