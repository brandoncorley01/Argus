@echo off
REM Sets ARGUS to the canonical PC folder. Called from the other launchers.
set "ARGUS="
if exist "%~dp0..\scripts\control-center\boot-argus.ps1" (
  for %%I in ("%~dp0..") do set "ARGUS=%%~fI"
)
if not defined ARGUS if exist "%USERPROFILE%\Desktop\Argus\scripts\control-center\boot-argus.ps1" (
  set "ARGUS=%USERPROFILE%\Desktop\Argus"
)
if not defined ARGUS if exist "%USERPROFILE%\Argus\scripts\control-center\boot-argus.ps1" (
  set "ARGUS=%USERPROFILE%\Argus"
)
if not defined ARGUS if exist "C:\Argus\scripts\control-center\boot-argus.ps1" (
  set "ARGUS=C:\Argus"
)
