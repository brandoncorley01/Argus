@echo off
REM Shows which PC folder Home is using vs which folder GitHub update will sync.
REM Report: Desktop\Argus-folder-report.txt
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\control-center\diagnose-argus-folder.ps1"
echo.
pause
