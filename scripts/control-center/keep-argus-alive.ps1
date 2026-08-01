# Keep Argus reachable while desired state is Running.
# Safe to run from Task Scheduler every 1-2 minutes (via run-hidden.vbs), or on demand.
# Does NOT git-sync. Does NOT start after intentional Stop (desired.running=false).
# Logs to file — never requires a visible console.
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root
$runtime = Get-ArgusRuntimeDir $Root
$log = Join-Path $runtime "keepalive-task.log"

function Write-KeepAliveLog([string]$Message) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString("o"), $Message
  Add-Content -Path $log -Value $line -Encoding utf8 -ErrorAction SilentlyContinue
}

$desired = Read-ArgusDesiredState $Root
if (-not $desired.running) {
  Write-KeepAliveLog "Desired state is Stopped - keepalive idle."
  exit 0
}

Write-KeepAliveLog "=== Argus keepalive (desired=Running) ==="

$lockPath = Join-Path $runtime "keepalive.lock"
try {
  $lock = [System.IO.File]::Open(
    $lockPath,
    [System.IO.FileMode]::OpenOrCreate,
    [System.IO.FileAccess]::ReadWrite,
    [System.IO.FileShare]::None
  )
} catch {
  Write-KeepAliveLog "Another keepalive is already running - exiting."
  exit 0
}

try {
  $ok = Repair-ArgusRuntime -Root $Root -IncludeWorker
  if ($ok) {
    Write-KeepAliveLog "OK  Argus runtime healthy (API /ready)"
    # Keep sleep-block helper alive while desired=Running (no console).
    try {
      if (-not (Test-ArgusKeepAwakeAlive $Root)) {
        $null = Start-ArgusKeepAwake $Root
        Write-KeepAliveLog "OK  keep-awake helper (re)started"
      }
    } catch {
      Write-KeepAliveLog ("WARN keep-awake: {0}" -f $_.Exception.Message)
    }
    exit 0
  }
  Show-ArgusNotification -Title "Argus recovery failed" -Message "Keepalive could not restore API /ready. Open Docker Desktop and press Start Argus." -Level "critical"
  Write-KeepAliveLog "FAIL keepalive could not restore API /ready"
  exit 1
} finally {
  if ($lock) { $lock.Close() }
}
