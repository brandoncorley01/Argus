@echo off
setlocal EnableExtensions
title Stop Argus
echo.
echo === Stop Argus ===
echo.

set "ROOT=%~dp0"
set "STOPPER=%ROOT%scripts\control-center\stop-argus.ps1"

if not exist "%STOPPER%" (
  echo Could not find:
  echo   %STOPPER%
  echo Make sure this file is inside your Argus folder.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%STOPPER%"
if errorlevel 1 (
  echo.
  echo Stop failed. Read the messages above.
  pause
  exit /b 1
)
