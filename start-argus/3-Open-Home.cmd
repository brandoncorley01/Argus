@echo off
setlocal EnableExtensions
title Open Argus Home
echo.
echo === Step 3 of 3: Open Home ===
echo Opening http://127.0.0.1:3000/today
echo Sign in, then confirm Build is live-monitor-v2.96
echo Hard-refresh if needed: Ctrl+F5
echo.
start "" "http://127.0.0.1:3000/today"
timeout /t 4 >nul
exit /b 0
