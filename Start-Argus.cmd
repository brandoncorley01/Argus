@echo off
setlocal EnableExtensions
title Start Argus
echo.
echo === Start Argus ===
echo Pulls latest GitHub main (cloud-agent merges), then starts Argus.
echo Dashboard:  http://127.0.0.1:3000/today
echo.

set "ROOT=%~dp0"
set "STARTER=%ROOT%scripts\control-center\start-argus.ps1"

REM Browser KeepDashboard must stay unset here so desktop Start can
REM start / restart the dashboard on port 3000.
set "ARGUS_KEEP_DASHBOARD="
set "ARGUS_START_SELF_UPDATED="
REM Always hard-sync GitHub main — Fast Start must never skip cloud merges.
set "ARGUS_FORCE_SYNC=1"
set "ARGUS_ALLOW_STALE="

if not exist "%STARTER%" (
  echo Could not find Start script inside this Argus folder.
  echo Expected:
  echo   %STARTER%
  echo.
  echo Open your Argus folder and run Start-Argus.cmd from there.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%STARTER%"
if errorlevel 1 (
  echo.
  echo Start failed. Read the messages above.
  echo If Docker is not running, start Docker Desktop, then try again.
  echo Nuclear update:
  echo   Update-Argus.cmd
  pause
  exit /b 1
)

echo.
echo === Start finished ===
echo Confirm Build on Home matches Desktop Argus-last-start.txt
echo Open this exact address in the browser:
echo   http://127.0.0.1:3000/today
echo.
start "" "http://127.0.0.1:3000/today"
echo Window closes in 12 seconds (or press a key)...
timeout /t 12 >nul
exit /b 0
