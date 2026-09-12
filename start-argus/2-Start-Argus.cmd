@echo off
setlocal EnableExtensions
title Start Argus
echo.
echo === Step 2 of 3: Start Argus ===
echo Target Build:  live-monitor-v2.96
if exist "%~dp0BUILD.txt" (
  echo Folder BUILD.txt:
  type "%~dp0BUILD.txt"
)
echo Docker must already say Running.
echo This boots THIS PC. It will not reset to GitHub 2.76.
echo.

call "%~dp0_find-argus.cmd"
if not defined ARGUS (
  echo Could not find your Argus folder.
  echo Expected: %USERPROFILE%\Desktop\Argus
  pause
  exit /b 1
)

set "BOOT=%ARGUS%\Boot-Argus.cmd"
if not exist "%BOOT%" (
  echo Could not find Boot-Argus.cmd
  echo Expected: %BOOT%
  pause
  exit /b 1
)

set "ARGUS_KEEP_DASHBOARD="
set "ARGUS_FORCE_SYNC="
set "ARGUS_ALLOW_STALE=1"
set "ARGUS_START_SELF_UPDATED=1"
set "ARGUS_SKIP_START_SELF_UPDATE=1"
set "ARGUS_RECYCLE_DASHBOARD=1"

call "%BOOT%"
exit /b %ERRORLEVEL%
