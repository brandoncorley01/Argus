@echo off
setlocal EnableExtensions
title Open Docker Desktop
echo.
echo === Step 1 of 3: Open Docker ===
echo Sign in if Docker asks. Wait until it says Running.
echo Then come back here and double-click 2-Start-Argus.
echo.

set "DOCKER=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if not exist "%DOCKER%" set "DOCKER=%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe"
if not exist "%DOCKER%" set "DOCKER=%LOCALAPPDATA%\Docker\Docker Desktop.exe"
if exist "%DOCKER%" (
  start "" "%DOCKER%"
  echo Docker Desktop is opening.
) else (
  echo Docker Desktop was not found. Install it, then try again.
)
echo.
echo When Docker Desktop says Running, close this window
echo and double-click 2-Start-Argus.
pause
exit /b 0
