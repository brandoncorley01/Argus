@echo off
setlocal EnableExtensions
title Start Argus
echo.
echo === Start Argus ===
echo This brings the dashboard back when the browser says
echo "127.0.0.1 refused to connect".
echo.
echo When finished, open:  http://127.0.0.1:3000/today
echo (must include :3000)
echo.

set "ROOT=%~dp0"
set "STARTER=%ROOT%scripts\control-center\start-argus.ps1"

REM Browser KeepDashboard must stay unset here so desktop Start can
REM start / restart the dashboard on port 3000.
set "ARGUS_KEEP_DASHBOARD="
set "ARGUS_START_SELF_UPDATED="

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
  pause
  exit /b 1
)

echo.
echo === Start finished ===
echo Open this exact address in the browser:
echo   http://127.0.0.1:3000/today
echo.
start "" "http://127.0.0.1:3000/today"
echo Window closes in 12 seconds (or press a key)...
timeout /t 12 >nul
exit /b 0
