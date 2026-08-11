@echo off
setlocal EnableExtensions
title FIX PC Argus — diagnose + GitHub pull
echo.
echo === FIX PC ARGUS ===
echo Cloud agents save ONLY to GitHub. This repairs / creates the ACTIVE Windows folder.
echo If no Argus folder exists, updater clones Desktop\Argus from GitHub.
echo.
echo TARGET after success: live-monitor-v2.51 or newer
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/diagnose-argus-folder.ps1?ref=main')"
echo.
echo --- Updating / cloning ACTIVE folder from GitHub ---
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/update-argus-now.ps1?ref=main')"
set "ERR=%ERRORLEVEL%"

echo.
echo Opening reports (Desktop and OneDrive Desktop and profile)...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$paths=@([Environment]::GetFolderPath('Desktop'), (Join-Path $env:USERPROFILE 'Desktop'), (Join-Path $env:USERPROFILE 'OneDrive\Desktop'), $env:USERPROFILE); foreach($d in ($paths|Select-Object -Unique)){ foreach($f in @('Argus-folder-report.txt','Argus-update-report.txt')){ $p=Join-Path $d $f; if(Test-Path $p){ Start-Process $p } } }"
start "" "http://127.0.0.1:3000/argus-build.txt"
start "" "http://127.0.0.1:3000/today"

if not "%ERR%"=="0" (
  echo.
  echo UPDATE FAILED. Look for Argus-update-report.txt on Desktop OR OneDrive Desktop OR %%USERPROFILE%%
  echo If it says git is missing: install Git for Windows, then re-run.
  pause
  exit /b %ERR%
)

echo.
echo UPDATE OK. Hard-refresh Home: Ctrl+F5
echo Confirm Build is live-monitor-v2.51 — and argus-build.txt matches.
echo.
timeout /t 15 >nul
exit /b 0
