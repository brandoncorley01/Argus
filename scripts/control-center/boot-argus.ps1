# HARD BOOT Argus - the simple, reliable path.
# No GitHub sync. No self-update. No nuclear updater.
# Brings Docker + API + worker + dashboard + keep-awake up and leaves desired=Running.
#
# Desktop: Boot-Argus.cmd
# PowerShell:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\control-center\boot-argus.ps1
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root
$runtime = Get-ArgusRuntimeDir $Root
$log = Join-Path $runtime "boot-argus.log"

function Write-BootLog([string]$Message) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString("o"), $Message
  Write-Host $Message
  try {
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::AppendAllText($log, $line + [Environment]::NewLine, $utf8)
  } catch { }
}

Write-BootLog "=== HARD BOOT Argus ==="
Write-BootLog "Folder: $Root"
Write-BootLog "Live trading: LOCKED (paper only)"

# 1) Intent first so keepalive knows to recover if we crash mid-boot.
Write-ArgusDesiredState -Root $Root -Running $true

# 2) Env + infra (Docker Postgres/Redis) - hard requirement.
if (-not (Ensure-ArgusEnvFile $Root)) {
  Write-BootLog "FAIL Missing .env"
  exit 1
}
if (-not (Ensure-ArgusInfra $Root)) {
  Write-BootLog "FAIL Docker/Postgres/Redis not healthy. Open Docker Desktop, wait until green, re-run Boot."
  exit 1
}
Write-BootLog "OK  Infra (Postgres + Redis)"

# 3) API venv + API process.
if (-not (Ensure-ArgusApiVenv $Root)) {
  Write-BootLog "FAIL API Python venv. Install Python 3.12+ and uv, then Boot again."
  exit 1
}

# Migrate is best-effort; never block boot if schema is already fine.
try {
  & "$Root\scripts\migrate-up.ps1"
  Write-BootLog "OK  Migrations"
} catch {
  Write-BootLog ("WARN migrate: {0}" -f $_.Exception.Message)
}

$apiLive = Test-HttpOk (Get-ArgusApiHealthUrl) 3
if (-not $apiLive) {
  Write-BootLog "Starting API on :8000..."
  $apiPid = Start-ArgusApiProcess $Root
  if (-not (Wait-HttpOk (Get-ArgusApiHealthUrl) 90 "API /health")) {
    Write-BootLog "FAIL API /health. See runtime\control-center\api.err.log"
    Write-BootLog (Get-ArgusApiLogTail $Root 40)
    exit 1
  }
} else {
  $apiPid = Get-ArgusPortListenerPid 8000
  if (-not $apiPid) {
    $apiPid = (Read-ArgusPids $Root).api
  }
  Write-BootLog "OK  API already live"
}
# Prefer /health for boot success; /ready may lag under load.
$ready = Test-HttpOk (Get-ArgusApiReadyUrl) 5
Write-BootLog ("OK  API health (ready={0})" -f $(if ($ready) { "yes" } else { "busy" }))

# 4) Worker (scans / exits / discovery).
$workerPid = $null
if (-not (Test-ArgusWorkerFresh $Root)) {
  Write-BootLog "Starting worker..."
  $workerPid = Start-ArgusWorkerProcess $Root
  Start-Sleep -Seconds 3
} else {
  Write-BootLog "OK  Worker already live"
  $workerPid = (Read-ArgusPids $Root).worker
}
if (-not (Test-ArgusWorkerFresh $Root)) {
  Write-BootLog "FAIL Worker did not stay up. See runtime\control-center\worker.err.log"
  exit 1
}
Write-BootLog "OK  Worker"

# 5) Keep-awake so Windows sleep cannot kill the desk.
try {
  $null = Start-ArgusKeepAwake $Root
  if (Test-ArgusKeepAwakeAlive $Root) {
    Write-BootLog "OK  Keep-awake (sleep blocked)"
  } else {
    Write-BootLog "WARN Keep-awake not confirmed - Windows may sleep"
  }
} catch {
  Write-BootLog ("WARN keep-awake: {0}" -f $_.Exception.Message)
}

# 6) Dashboard on :3000 (paper desk UI).
$eocPid = (Read-ArgusPids $Root).eoc
$eocUp = (Test-HttpOk "http://127.0.0.1:3000/login" 3) -or (Test-HttpOk "http://127.0.0.1:3000/" 3) -or (Test-HttpOk (Get-ArgusDashboardUrl) 3)
$localBuild = Get-ArgusLocalBuildId $Root
$httpBuild = $null
if ($eocUp) {
  try { $httpBuild = Get-ArgusHttpBuildId } catch { $httpBuild = $null }
}
$mustRecycle = $env:ARGUS_RECYCLE_DASHBOARD -eq "1"
if ($eocUp -and $localBuild -and $httpBuild -and ($httpBuild -ne $localBuild)) {
  Write-BootLog ('Dashboard stamp mismatch HTTP={0} local={1} - recycling Home.' -f $httpBuild, $localBuild)
  $mustRecycle = $true
}
if ($eocUp -and $mustRecycle) {
  Write-BootLog "Recycling dashboard so Home shows this PC's build..."
  try { Stop-ArgusPortListeners @(3000) } catch { }
  $eocUp = $false
}
if (-not $eocUp) {
  Write-BootLog "Starting dashboard on :3000..."
  try {
    $null = Ensure-ArgusEocDeps $Root
  } catch {
    Write-BootLog ("WARN eoc deps: {0}" -f $_.Exception.Message)
  }
  try { Stop-ArgusPortListeners @(3000) } catch { }
  $eocLog = Join-Path $runtime "eoc.log"
  $envBlock = "`$env:ARGUS_API_BASE_URL='http://127.0.0.1:8000'; `$env:ARGUS_REPO_ROOT='$Root'"
  $eocProc = Start-Process -FilePath "powershell.exe" -PassThru -WindowStyle Hidden -ArgumentList @(
    "-NoProfile", "-NoLogo", "-NonInteractive", "-ExecutionPolicy", "Bypass",
    "-WindowStyle", "Hidden", "-Command",
    "Set-Location '$Root'; $envBlock; pnpm eoc:dev *> '$eocLog'"
  )
  $eocPid = $eocProc.Id
  $null = Wait-HttpOk (Get-ArgusDashboardUrl) 120 "Dashboard"
} else {
  Write-BootLog "OK  Dashboard already up"
}

# 7) Persist PIDs + re-register keepalive task.
Write-ArgusPids -Root $Root -ApiPid $apiPid -EocPid $eocPid -WorkerPid $workerPid
try {
  & "$PSScriptRoot\install-keepalive-task.ps1"
  Write-BootLog "OK  Keepalive task"
} catch {
  Write-BootLog ("WARN keepalive task: {0}" -f $_.Exception.Message)
}

# Stamp build for Home chip (local, no GitHub required).
try {
  $null = Write-ArgusPublicBuildStamp $Root
} catch { }

Write-BootLog "=== BOOT COMPLETE ==="
Write-BootLog "Home: http://127.0.0.1:3000/today"
Write-BootLog "Status: paper trading ON. Live trading remains LOCKED until you explicitly approve unlock."
Write-BootLog "Scans run about every minute while Running. Hard-refresh Home if Last scan looks old."

# Open Home unless caller asked us not to (browser Start keeps the page).
if ($env:ARGUS_KEEP_DASHBOARD -ne "1") {
  try { Start-Process (Get-ArgusDashboardUrl) } catch { }
}

exit 0
