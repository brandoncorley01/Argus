import { NextResponse } from "next/server";
import path from "node:path";

/**
 * Downloadable Windows installer for Founder desktop shortcuts.
 * Searches common Argus locations so the download works even if the
 * server-side path differs from this PC.
 */
export async function GET() {
  const root = process.env.ARGUS_REPO_ROOT
    ? process.env.ARGUS_REPO_ROOT
    : path.resolve(process.cwd(), "..", "..");
  const preferred = path
    .join(root, "scripts", "control-center", "install-desktop-shortcuts.ps1")
    .replace(/"/g, "");

  const cmd = `@echo off
setlocal EnableExtensions
title Install Argus Desktop Shortcuts
echo.
echo === Argus desktop installer ===
echo This puts Start Argus and Stop Argus on your Desktop.
echo.

set "INSTALLER="
if exist "${preferred}" set "INSTALLER=${preferred}"

if not defined INSTALLER if exist "%USERPROFILE%\\OneDrive\\Desktop\\Argus\\scripts\\control-center\\install-desktop-shortcuts.ps1" (
  set "INSTALLER=%USERPROFILE%\\OneDrive\\Desktop\\Argus\\scripts\\control-center\\install-desktop-shortcuts.ps1"
)
if not defined INSTALLER if exist "%USERPROFILE%\\Desktop\\Argus\\scripts\\control-center\\install-desktop-shortcuts.ps1" (
  set "INSTALLER=%USERPROFILE%\\Desktop\\Argus\\scripts\\control-center\\install-desktop-shortcuts.ps1"
)
if not defined INSTALLER if exist "%USERPROFILE%\\OneDrive\\Documents\\Argus\\scripts\\control-center\\install-desktop-shortcuts.ps1" (
  set "INSTALLER=%USERPROFILE%\\OneDrive\\Documents\\Argus\\scripts\\control-center\\install-desktop-shortcuts.ps1"
)

if not defined INSTALLER (
  echo Could not find Argus on this PC.
  echo Expected a folder named Argus with scripts\\control-center inside.
  echo.
  pause
  exit /b 1
)

echo Found: %INSTALLER%
echo Installing shortcuts...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%INSTALLER%"
if errorlevel 1 (
  echo.
  echo Install failed.
  pause
  exit /b 1
)

echo.
echo Done. Check your Desktop for:
echo   Start Argus
echo   Stop Argus
echo   Open Argus
echo   End Trading Day
echo.
pause
`;

  return new NextResponse(cmd, {
    status: 200,
    headers: {
      "Content-Type": "application/x-bat",
      "Content-Disposition": 'attachment; filename="Install-Argus-Desktop.cmd"',
      "Cache-Control": "no-store",
    },
  });
}
