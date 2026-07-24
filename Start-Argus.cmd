@echo off
setlocal EnableExtensions
title Start Argus
echo.
echo === Start Argus ===
echo Updating and starting. A browser window will open when ready.
echo.

set "ROOT=%~dp0"
set "STARTER=%ROOT%scripts\control-center\start-argus.ps1"

if not exist "%STARTER%" (
  echo Could not find Start script inside this Argus folder.
  echo Expected:
  echo   %STARTER%
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%STARTER%"
if errorlevel 1 (
  echo.
  echo Start failed. Read the messages above.
  pause
  exit /b 1
)
