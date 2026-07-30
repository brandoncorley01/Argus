# Keep Argus reachable while desired state is Running.
# Safe to run from Task Scheduler every 1-2 minutes, or on demand from EOC login.
# Does NOT git-sync. Does NOT start after intentional Stop (desired.running=false).
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root

$desired = Read-ArgusDesiredState $Root
if (-not $desired.running) {
  Write-Host "Desired state is Stopped - keepalive idle."
  exit 0
}

Write-Host "=== Argus keepalive (desired=Running) ==="

$runtime = Get-ArgusRuntimeDir $Root
$lockPath = Join-Path $runtime "keepalive.lock"
try {
  $lock = [System.IO.File]::Open(
    $lockPath,
    [System.IO.FileMode]::OpenOrCreate,
    [System.IO.FileAccess]::ReadWrite,
    [System.IO.FileShare]::None
  )
} catch {
  Write-Host "Another keepalive is already running - exiting."
  exit 0
}

try {
  $ok = Repair-ArgusRuntime -Root $Root -IncludeWorker
  if ($ok) {
    Write-Host "OK  Argus runtime healthy (API /ready)"
    exit 0
  }
  Show-ArgusNotification -Title "Argus recovery failed" -Message "Keepalive could not restore API /ready. Open Docker Desktop and press Start Argus." -Level "critical"
  Write-Host "FAIL keepalive could not restore API /ready"
  exit 1
} finally {
  if ($lock) { $lock.Close() }
}
