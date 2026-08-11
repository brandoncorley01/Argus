# Install Desktop shortcuts on %USERPROFILE%\Desktop (NOT OneDrive).
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
# Canonical Desktop — GetFolderPath("Desktop") often returns OneDrive\Desktop.
$Desktop = Join-Path $env:USERPROFILE "Desktop"
if (-not (Test-Path $Desktop)) {
  New-Item -ItemType Directory -Force -Path $Desktop | Out-Null
}
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

function New-ArgusApiShortcut([string]$Name, [string]$RepoPath, [string]$Description) {
  $lnkPath = Join-Path $Desktop "$Name.lnk"
  $sc = $Wsh.CreateShortcut($lnkPath)
  $sc.TargetPath = "powershell.exe"
  $cmd = @"
`$ErrorActionPreference='Stop'; iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/$RepoPath?ref=main')
"@
  $sc.Arguments = "-NoProfile -ExecutionPolicy Bypass -Command `"$cmd`""
  $sc.WorkingDirectory = $Root
  $sc.WindowStyle = 1
  $sc.Description = $Description
  $sc.Save()
  Write-Host "Created (API): $lnkPath"
}

function New-ArgusCmdShortcut([string]$Name, [string]$CmdLeaf, [string]$Description) {
  $cmdPath = Join-Path $Root $CmdLeaf
  if (-not (Test-Path $cmdPath)) {
    Write-Host "SKIP shortcut $Name — missing $CmdLeaf"
    return
  }
  $lnkPath = Join-Path $Desktop "$Name.lnk"
  $sc = $Wsh.CreateShortcut($lnkPath)
  $sc.TargetPath = $cmdPath
  $sc.WorkingDirectory = $Root
  $sc.WindowStyle = 1
  $sc.Description = $Description
  $sc.Save()
  Write-Host "Created: $lnkPath"
}

Write-Host "=== ARGUS - DAILY ==="
Write-Host ("Shortcuts Desktop: {0}" -f $Desktop)
Write-Host ("WorkingDirectory:  {0}" -f $Root)
New-ArgusShortcut "Start Argus" "start-argus.ps1" "ARGUS DAILY - Start (hard-syncs GitHub main)"
New-ArgusShortcut "Open Argus" "open-dashboard.ps1" "ARGUS DAILY - Open Home"
New-ArgusShortcut "End Trading Day" "end-trading-day.ps1" "ARGUS DAILY - Report + Backup"
New-ArgusShortcut "Stop Argus" "stop-argus.ps1" "ARGUS DAILY - Stop"

Write-Host "=== ARGUS - TOOLS ==="
New-ArgusApiShortcut "Update Argus Now" "scripts/control-center/update-argus-now.ps1" "ARGUS TOOLS - Nuclear hard-reset via GitHub API (Desktop only)"
New-ArgusApiShortcut "Bring Argus Up" "scripts/control-center/bring-argus-up.ps1" "ARGUS TOOLS - Find Desktop\Argus and Start"
New-ArgusApiShortcut "Diagnose Argus Folder" "scripts/control-center/diagnose-argus-folder.ps1" "ARGUS TOOLS - Prove which folder Home uses"
New-ArgusCmdShortcut "GET LATEST Argus" "GET-LATEST.cmd" "ARGUS TOOLS - Diagnose then update from GitHub"
New-ArgusCmdShortcut "FIX PC Argus" "FIX-PC.cmd" "ARGUS TOOLS - Nuclear PC repair"
New-ArgusShortcut "Argus Status" "status-argus.ps1" "ARGUS TOOLS - Status"
New-ArgusShortcut "Restart Argus" "restart-argus.ps1" "ARGUS TOOLS - Restart"
New-ArgusShortcut "Backup Argus" "backup-argus.ps1" "ARGUS TOOLS - Backup"
New-ArgusShortcut "Generate Argus Daily Report" "generate-daily-report.ps1" "ARGUS TOOLS - Report only"
New-ArgusShortcut "Open Argus Dashboard" "open-dashboard.ps1" "ARGUS DAILY - Open Home (alias)"

Write-Host ""
Write-Host "Installing Argus keepalive scheduled task..."
try {
  & "$PSScriptRoot\install-keepalive-task.ps1"
} catch {
  Write-Host "WARN: keepalive task not registered: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "Desktop shortcuts installed on %USERPROFILE%\Desktop (not OneDrive)."
Write-Host "Home URL: $(Get-ArgusDashboardUrl)"
Write-Host "Paper trading only · Live trading DISABLED"
