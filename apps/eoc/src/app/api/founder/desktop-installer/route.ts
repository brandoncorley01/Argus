import { NextResponse } from "next/server";
import path from "node:path";

/**
 * Downloadable Windows installer for Founder desktop shortcuts.
 * Embeds the absolute repo path so double-click works from Downloads.
 */
export async function GET() {
  const root = process.env.ARGUS_REPO_ROOT
    ? process.env.ARGUS_REPO_ROOT
    : path.resolve(process.cwd(), "..", "..");
  const installer = path.join(root, "scripts", "control-center", "install-desktop-shortcuts.ps1");
  // CMD-safe quoted path (escape embedded double-quotes if any)
  const quoted = `"${installer.replace(/"/g, "")}"`;

  const cmd = `@echo off
title Install Argus Desktop Shortcuts
echo Installing Argus Start / Stop / Open / End Trading Day shortcuts...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ${quoted}
if errorlevel 1 (
  echo.
  echo Install failed. Open PowerShell in the Argus folder and run:
  echo   .\\scripts\\control-center\\install-desktop-shortcuts.ps1
  pause
  exit /b 1
)
echo.
echo Done. Check your Desktop for Start Argus and Stop Argus.
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
