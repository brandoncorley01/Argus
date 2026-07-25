# Start Argus Control Center - update code, infra, API, worker, dashboard; open Home.
$ErrorActionPreference = "Continue"

# Self-update from GitHub first so browser Start cannot stay stuck on a stale script.
if (-not $env:ARGUS_START_SELF_UPDATED) {
  $env:ARGUS_START_SELF_UPDATED = "1"
  $self = $MyInvocation.MyCommand.Path
  if (-not $self) { $self = Join-Path $PSScriptRoot "start-argus.ps1" }
  $url = "https://raw.githubusercontent.com/brandoncorley01/Argus/main/scripts/control-center/start-argus.ps1"
  try {
    Write-Host "Downloading latest Start script from GitHub..."
    Invoke-WebRequest -Uri "$url?$(Get-Random)" -OutFile $self -UseBasicParsing
    Write-Host "Re-running updated Start script..."
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $self @args
    exit $LASTEXITCODE
  } catch {
    Write-Host "WARN: could not self-update Start script: $($_.Exception.Message)"
  }
}

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root

Write-Host "=== Start Argus ==="
Write-Host "Provider: internal_paper (default)"
Write-Host "Live trading: DISABLED"

# Browser Start/Stop must not kill the page serving the request.
$KeepDashboard = $env:ARGUS_KEEP_DASHBOARD -eq "1"

try {
  if (-not (Test-Path (Join-Path $Root ".env"))) {
    throw "Missing .env. Copy .env.paper.example or .env.example to .env first."
  }

  # Force GitHub main onto this PC (Founder browser cadence).
  $updated = Sync-ArgusCode $Root

  # Also force-reset even if Sync helper returned false on a dirty tree.
  try {
    git fetch origin 2>&1 | Out-Host
    git checkout -f -B main origin/main 2>&1 | Out-Host
    git reset --hard origin/main 2>&1 | Out-Host
    $updated = $true
  } catch {
    Write-Host "WARN: extra force-sync skipped: $($_.Exception.Message)"
  }

  $sha = (git rev-parse --short HEAD).Trim()
  $buildMarker = Join-Path $Root "apps\eoc\public\argus-build.txt"
  $publicDir = Split-Path $buildMarker -Parent
  if (-not (Test-Path $publicDir)) {
    New-Item -ItemType Directory -Force -Path $publicDir | Out-Null
  }
  Set-Content -Path $buildMarker -Value "home-start-stop-v4 $sha" -Encoding ascii

  # Drop stale Next.js cache so Home Start/Stop cannot be masked by old builds.
  $nextCache = Join-Path $Root "apps\eoc\.next"
  if (Test-Path $nextCache) {
    Write-Host "Clearing stale dashboard cache..."
    Remove-Item -LiteralPath $nextCache -Recurse -Force -ErrorAction SilentlyContinue
  }

  & "$Root\scripts\infra-up.ps1"
  & "$Root\scripts\migrate-up.ps1"

  $pids = Read-ArgusPids $Root
  $apiPid = $pids.api
  $eocPid = $pids.eoc
  $workerPid = $pids.worker

  # After a code update, recycle API. From browser Start, always reload dashboard.
  $reloadDashboard = $KeepDashboard
  Write-Host "Code refresh - recycling services..."
  Stop-PidIfRunning $pids.api "API launcher"
  if (-not $KeepDashboard) {
    Stop-PidIfRunning $pids.eoc "EOC launcher"
    Stop-ArgusPortListeners @(8000, 3000)
    $eocPid = $null
  } else {
    Stop-ArgusPortListeners @(8000)
    Write-Host "Dashboard will reload after Start finishes so Home picks up the update."
  }
  $apiPid = $null

  if (-not (Test-HttpOk (Get-ArgusApiHealthUrl))) {
    Write-Host "Starting API on 127.0.0.1:8000..."
    $apiLog = Join-Path (Get-ArgusRuntimeDir $Root) "api.log"
    $apiProc = Start-Process -FilePath "powershell.exe" -PassThru -WindowStyle Minimized -ArgumentList @(
      "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
      "Set-Location '$Root\apps\api'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 *> '$apiLog'"
    )
    $apiPid = $apiProc.Id
  } else {
    Write-Host "API already responding"
  }

  if (-not (Test-ArgusWorkerFresh $Root)) {
    $workerPid = Start-ArgusWorkerProcess $Root
  } else {
    Write-Host "Worker already running"
  }

  $eocUp = (Test-HttpOk "http://127.0.0.1:3000/login") -or (Test-HttpOk "http://127.0.0.1:3000/") -or (Test-HttpOk (Get-ArgusDashboardUrl) 2)
  if ($KeepDashboard) {
    Write-Host "Dashboard left running until end-of-Start reload"
  } elseif ($updated -or -not $eocUp) {
    if ($eocUp -and -not $updated) {
      Write-Host "EOC already responding"
    } else {
      if ($eocUp) {
        Stop-ArgusPortListeners @(3000)
      }
      Write-Host "Starting dashboard on 127.0.0.1:3000..."
      $eocLog = Join-Path (Get-ArgusRuntimeDir $Root) "eoc.log"
      $envBlock = "`$env:ARGUS_API_BASE_URL='http://127.0.0.1:8000'; `$env:ARGUS_REPO_ROOT='$Root'"
      $eocProc = Start-Process -FilePath "powershell.exe" -PassThru -WindowStyle Minimized -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "Set-Location '$Root'; $envBlock; pnpm eoc:dev *> '$eocLog'"
      )
      $eocPid = $eocProc.Id
    }
  } else {
    Write-Host "EOC already responding"
  }

  Write-ArgusPids -Root $Root -ApiPid $apiPid -EocPid $eocPid -WorkerPid $workerPid

  $okApi = Wait-HttpOk (Get-ArgusApiReadyUrl) 120 "API /ready"
  $okEoc = $false
  $deadline = (Get-Date).AddSeconds(120)
  while ((Get-Date) -lt $deadline) {
    if ((Test-HttpOk "http://127.0.0.1:3000/login") -or (Test-HttpOk "http://127.0.0.1:3000/") -or (Test-HttpOk (Get-ArgusDashboardUrl))) {
      $okEoc = $true
      Write-Host "OK  Dashboard ready ($(Get-ArgusDashboardUrl))"
      break
    }
    Start-Sleep -Seconds 2
  }
  if (-not $okEoc) {
    Write-Host "FAIL Dashboard not ready within 120s"
  }

  if ($KeepDashboard) {
    if (-not $okApi) {
      throw "Argus API did not become healthy. Check runtime\control-center\*.log"
    }
  } elseif (-not ($okApi -and $okEoc)) {
    throw "Argus did not become healthy. Check runtime\control-center\*.log"
  }

  if (-not $KeepDashboard) {
    $dash = Get-ArgusDashboardUrl
    Write-Host "Opening Home: $dash"
    Start-Process $dash
  } elseif ($reloadDashboard) {
    Write-Host "Reloading dashboard for updated Home..."
    $eocLog = Join-Path (Get-ArgusRuntimeDir $Root) "eoc.log"
    $restart = @"
Start-Sleep -Seconds 5
try {
  Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id `$_.OwningProcess -Force -ErrorAction SilentlyContinue }
} catch {}
Start-Sleep -Seconds 2
Set-Location '$Root'
`$env:ARGUS_API_BASE_URL = 'http://127.0.0.1:8000'
`$env:ARGUS_REPO_ROOT = '$Root'
pnpm eoc:dev *> '$eocLog'
"@
    $eocProc = Start-Process -FilePath "powershell.exe" -PassThru -WindowStyle Minimized -ArgumentList @(
      "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $restart
    )
    Write-ArgusPids -Root $Root -ApiPid $apiPid -EocPid $eocProc.Id -WorkerPid $workerPid
    Write-Host "REFRESH_HOME_AFTER_UPDATE"
  }
  Write-Host "=== Argus started ==="
} catch {
  Show-ArgusNotification -Title "Argus startup failed" -Message $_.Exception.Message -Level "critical"
  throw
}
