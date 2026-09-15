# Keep Argus reachable while desired state is Running.
# Hard rules:
# 1) If desired=Stopped, do nothing.
# 2) If API process + worker process are up, exit 0 (do not migrate/restart).
# 3) If down, run surgical Repair — never require GitHub; never thrash a live API.
# 4) Toast spam is forbidden — at most one critical notice per hour.
# Logs to file - never requires a visible console.
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_common.ps1"
$ErrorActionPreference = "Continue"

$Root = Get-ArgusRoot
Set-Location $Root
$runtime = Get-ArgusRuntimeDir $Root
$log = Join-Path $runtime "keepalive-task.log"

function Write-KeepAliveLog([string]$Message) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString("o"), $Message
  try {
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::AppendAllText($log, $line + [Environment]::NewLine, $utf8)
  } catch { }
}

function Show-KeepAliveCriticalOnce([string]$Detail) {
  $stampPath = Join-Path $runtime "keepalive-last-critical.txt"
  try {
    if (Test-Path $stampPath) {
      $stamp = [datetime]::Parse((Get-Content -Path $stampPath -ErrorAction Stop | Select-Object -First 1))
      if ((Get-Date) -lt $stamp.AddHours(1)) {
        Write-KeepAliveLog ("SUPPRESS critical toast (hourly limit): {0}" -f $Detail)
        return
      }
    }
  } catch { }
  try {
    (Get-Date).ToUniversalTime().ToString("o") | Set-Content -Path $stampPath -Encoding utf8
  } catch { }
  Show-ArgusNotification -Title "Argus recovery failed" -Message "Keepalive could not restore API+worker. Open Docker Desktop and run Boot-Argus.cmd. ($Detail)" -Level "critical"
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

$bootCooldownPath = Join-Path $runtime "keepalive-boot-cooldown.txt"
function Test-KeepAliveBootCooldown([int]$Minutes = 15) {
  if (-not (Test-Path $bootCooldownPath)) { return $false }
  try {
    $stamp = [datetime]::Parse((Get-Content -Path $bootCooldownPath -ErrorAction Stop | Select-Object -First 1))
    return ((Get-Date) -lt $stamp.AddMinutes($Minutes))
  } catch {
    return $false
  }
}
function Set-KeepAliveBootCooldown {
  try {
    (Get-Date).ToUniversalTime().ToString("o") | Set-Content -Path $bootCooldownPath -Encoding utf8
  } catch { }
}

try {
  try { Ensure-SingleArgusProcesses } catch { }

  $apiLive = Test-ArgusApiLiveness
  $apiProc = Test-ArgusApiProcessLive
  $workerOk = Test-ArgusWorkerFresh $Root
  $awakeOk = Test-ArgusKeepAwakeAlive $Root

  # Process-level success beats flaky HTTP under load — never restart a live stack.
  if (($apiLive -or $apiProc) -and $workerOk) {
    if (-not $awakeOk) {
      try {
        $null = Start-ArgusKeepAwake $Root
        $awakeOk = Test-ArgusKeepAwakeAlive $Root
        Write-KeepAliveLog "OK  keep-awake helper (re)started"
      } catch {
        Write-KeepAliveLog ("WARN keep-awake: {0}" -f $_.Exception.Message)
      }
    }
    Write-KeepAliveLog ("OK  Argus runtime healthy (api_http={0}; api_proc={1}; worker=up; keep-awake={2})" -f `
      $(if ($apiLive) { "up" } else { "busy" }), `
      $(if ($apiProc) { "up" } else { "down" }), `
      $(if ($awakeOk) { "up" } else { "down" }))
    exit 0
  }

  Write-KeepAliveLog ("Repair needed (api_http={0}; api_proc={1}; worker={2})" -f `
    $(if ($apiLive) { "up" } else { "down" }), `
    $(if ($apiProc) { "up" } else { "down" }), `
    $(if ($workerOk) { "up" } else { "down" }))

  if (Test-KeepAliveBootCooldown) {
    # Cooldown only suppresses a full Boot. A live API with a missing Micro
    # lane must still get a surgical worker restart.
    if (($apiLive -or $apiProc) -and $workerOk) {
      Write-KeepAliveLog "SKIP boot - cooldown active; full stack present"
      exit 0
    }
    if (-not $workerOk) {
      Write-KeepAliveLog "Cooldown active but worker lane missing - surgical worker restart"
      $ok = Repair-ArgusRuntime -Root $Root -IncludeWorker
      $workerOk = Test-ArgusWorkerFresh $Root
      $apiLive = Test-ArgusApiLiveness
      $apiProc = Test-ArgusApiProcessLive
      if (($apiLive -or $apiProc) -and $workerOk) {
        Write-KeepAliveLog ("OK  worker restored under cooldown (repair_ok={0})" -f $(if ($ok) { "true" } else { "false" }))
        exit 0
      }
      Write-KeepAliveLog ("WARN worker still down under cooldown (repair_ok={0})" -f $(if ($ok) { "true" } else { "false" }))
      exit 0
    }
    Write-KeepAliveLog "SKIP boot - cooldown active (API may be busy, not dead)"
    exit 0
  }

  $ok = $false
  Set-KeepAliveBootCooldown
  if ($apiLive -or $apiProc -or $workerOk) {
    Write-KeepAliveLog "Surgical repair (avoid duplicate Boot)"
    $ok = Repair-ArgusRuntime -Root $Root -IncludeWorker
    Write-KeepAliveLog ("Repair ok={0}" -f $(if ($ok) { "true" } else { "false" }))
  } else {
    $boot = Join-Path $PSScriptRoot "boot-argus.ps1"
    if (Test-Path $boot) {
      try {
        $env:ARGUS_KEEP_DASHBOARD = "1"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $boot
        $ok = ($LASTEXITCODE -eq 0)
        Write-KeepAliveLog ("Boot exit={0}" -f $LASTEXITCODE)
      } catch {
        Write-KeepAliveLog ("Boot threw: {0}" -f $_.Exception.Message)
        $ok = $false
      }
    } else {
      $ok = Repair-ArgusRuntime -Root $Root -IncludeWorker
    }
  }

  $apiLive = Test-ArgusApiLiveness
  $apiProc = Test-ArgusApiProcessLive
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

  if (($apiLive -or $apiProc) -and $workerOk) {
    Write-KeepAliveLog ("OK  Argus runtime healthy after repair (keep-awake={0})" -f $(if ($awakeOk) { "up" } else { "down" }))
    exit 0
  }

  $detail = "api_http={0}; api_proc={1}; worker={2}; keep-awake={3}; repair_ok={4}" -f `
    $(if ($apiLive) { "up" } else { "down" }), `
    $(if ($apiProc) { "up" } else { "down" }), `
    $(if ($workerOk) { "up" } else { "down" }), `
    $(if ($awakeOk) { "up" } else { "down" }), `
    $(if ($ok) { "true" } else { "false" })
  Show-KeepAliveCriticalOnce $detail
  Write-KeepAliveLog "FAIL keepalive could not restore full runtime ($detail)"
  # Exit 0 so Task Scheduler does not RestartCount-loop and thrash the PC.
  exit 0
} finally {
  if ($lock) { $lock.Close() }
}
