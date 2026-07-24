# Install Desktop shortcuts for Argus Control Center (Windows).
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
$Desktop = [Environment]::GetFolderPath("Desktop")
$Wsh = New-Object -ComObject WScript.Shell

function New-ArgusShortcut([string]$Name, [string]$ScriptLeaf) {
  $scriptPath = Join-Path $PSScriptRoot $ScriptLeaf
  $lnkPath = Join-Path $Desktop "$Name.lnk"
  $sc = $Wsh.CreateShortcut($lnkPath)
  $sc.TargetPath = "powershell.exe"
  $sc.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
  $sc.WorkingDirectory = $Root
  $sc.WindowStyle = 1
  $sc.Description = $Name
  $sc.Save()
  Write-Host "Created: $lnkPath"
}

New-ArgusShortcut "Start Argus" "start-argus.ps1"
New-ArgusShortcut "Stop Argus" "stop-argus.ps1"
New-ArgusShortcut "Restart Argus" "restart-argus.ps1"
New-ArgusShortcut "Argus Status" "status-argus.ps1"
New-ArgusShortcut "Backup Argus" "backup-argus.ps1"
New-ArgusShortcut "Generate Argus Daily Report" "generate-daily-report.ps1"
New-ArgusShortcut "Open Argus Dashboard" "open-dashboard.ps1"

Write-Host "Desktop shortcuts installed."
Write-Host "Dashboard URL: $(Get-ArgusDashboardUrl)"
Write-Host "Provider: internal_paper · Live trading: DISABLED"
Write-Host "Milestone: Founder RC1 (Sprint 5)"
