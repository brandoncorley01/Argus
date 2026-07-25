# Install Desktop shortcuts - Daily controls first, tools second.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
$Desktop = [Environment]::GetFolderPath("Desktop")
$Wsh = New-Object -ComObject WScript.Shell

function New-ArgusShortcut([string]$Name, [string]$ScriptLeaf, [string]$Description) {
  $scriptPath = Join-Path $PSScriptRoot $ScriptLeaf
  $lnkPath = Join-Path $Desktop "$Name.lnk"
  $sc = $Wsh.CreateShortcut($lnkPath)
  $sc.TargetPath = "powershell.exe"
  $sc.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
  $sc.WorkingDirectory = $Root
  $sc.WindowStyle = 1
  $sc.Description = $Description
  $sc.Save()
  Write-Host "Created: $lnkPath"
}

Write-Host "=== ARGUS - DAILY ==="
New-ArgusShortcut "Start Argus" "start-argus.ps1" "ARGUS DAILY - Start"
New-ArgusShortcut "Open Argus" "open-dashboard.ps1" "ARGUS DAILY - Open Home"
New-ArgusShortcut "End Trading Day" "end-trading-day.ps1" "ARGUS DAILY - Report + Backup"
New-ArgusShortcut "Stop Argus" "stop-argus.ps1" "ARGUS DAILY - Stop"

Write-Host "=== ARGUS - TOOLS ==="
New-ArgusShortcut "Argus Status" "status-argus.ps1" "ARGUS TOOLS - Status"
New-ArgusShortcut "Restart Argus" "restart-argus.ps1" "ARGUS TOOLS - Restart"
New-ArgusShortcut "Backup Argus" "backup-argus.ps1" "ARGUS TOOLS - Backup"
New-ArgusShortcut "Generate Argus Daily Report" "generate-daily-report.ps1" "ARGUS TOOLS - Report only"

# Keep legacy name pointing at Home for older muscle memory
New-ArgusShortcut "Open Argus Dashboard" "open-dashboard.ps1" "ARGUS DAILY - Open Home (alias)"

Write-Host ""
Write-Host "Desktop shortcuts installed."
Write-Host "Daily: Start / Open / End Trading Day / Stop"
Write-Host "Tools: Status / Restart / Backup / Generate Report"
Write-Host "Home URL: $(Get-ArgusDashboardUrl)"
Write-Host "Paper trading only · Live trading DISABLED"
