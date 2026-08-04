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
  $apiOk = Test-HttpOk (Get-ArgusApiReadyUrl) 3
  $workerOk = Test-ArgusWorkerFresh $Root
  $awakeOk = Test-ArgusKeepAwakeAlive $Root

  if (-not $awakeOk) {
    try {
      $null = Start-ArgusKeepAwake $Root
      $awakeOk = Test-ArgusKeepAwakeAlive $Root
      Write-KeepAliveLog "OK  keep-awake helper (re)started"
    } catch {
      Write-KeepAliveLog ("WARN keep-awake: {0}" -f $_.Exception.Message)
    }
  }

  if ($ok -and $apiOk -and $workerOk) {
    Write-KeepAliveLog ("OK  Argus runtime healthy (API + worker; keep-awake={0})" -f $(if ($awakeOk) { "up" } else { "down" }))
    exit 0
  }

  $detail = "api={0}; worker={1}; keep-awake={2}; repair_ok={3}" -f `
    $(if ($apiOk) { "up" } else { "down" }), `
    $(if ($workerOk) { "up" } else { "down" }), `
    $(if ($awakeOk) { "up" } else { "down" }), `
    $(if ($ok) { "true" } else { "false" })
  Show-ArgusNotification -Title "Argus recovery failed" -Message "Keepalive could not restore API+worker. Open Docker Desktop and press Start Argus. ($detail)" -Level "critical"
  Write-KeepAliveLog "FAIL keepalive could not restore full runtime ($detail)"
  exit 1
} finally {
  if ($lock) { $lock.Close() }
}
