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
    Invoke-WebRequest -Uri "$url?$(Get-Random)" -OutFile $self -UseBasicParsing -TimeoutSec 30
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

  # Car model: if Argus is already running, Start must not stall on git sync /
  # cache wipe / full recycle. Only force a heavy Start when unhealthy or
  # ARGUS_FORCE_SYNC=1 (explicit refresh from GitHub).
  $forceSync = $env:ARGUS_FORCE_SYNC -eq "1"
  $apiReadyNow = Test-HttpOk (Get-ArgusApiReadyUrl) 3
  $eocReadyNow = (Test-HttpOk "http://127.0.0.1:3000/login" 3) -or (Test-HttpOk "http://127.0.0.1:3000/" 3) -or (Test-HttpOk (Get-ArgusDashboardUrl) 3)
  $workerReadyNow = Test-ArgusWorkerFresh $Root
  if ($apiReadyNow -and $eocReadyNow -and $workerReadyNow -and -not $forceSync) {
    Write-Host "Argus is already running — fast Start (no git sync / no cache wipe)."
    # Collapse duplicate API/worker processes that make crons look stalled.
    try {
      $uvs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like "*uvicorn app.main:app*" })
      if ($uvs.Count -gt 1) {
        Write-Host "Removing duplicate API processes..."
        $uvs | Select-Object -Skip 1 | ForEach-Object {
          Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
      }
      $wps = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
          $_.CommandLine -and (
            $_.CommandLine -like "*workers.health_supervisor.worker*" -or
            $_.CommandLine -like "*workers.market_ops.worker*"
          )
        })
      if ($wps.Count -gt 1) {
        Write-Host "Removing duplicate worker processes..."
        $wps | Select-Object -Skip 1 | ForEach-Object {
          Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
      }
    } catch { }
    $sha = (git rev-parse --short HEAD).Trim()
    $buildIdFile = Join-Path $Root "apps\eoc\src\lib\build.ts"
    $buildId = "command-center"
    if (Test-Path $buildIdFile) {
      $m = Select-String -Path $buildIdFile -Pattern 'ARGUS_UI_BUILD\s*=\s*"([^"]+)"' | Select-Object -First 1
      if ($m) { $buildId = $m.Matches.Groups[1].Value }
    }
    Write-Host "Build $buildId @ $sha"
    if (-not $KeepDashboard) {
      Start-Process (Get-ArgusDashboardUrl)
    } else {
      Write-Host "REFRESH_HOME_SOFT"
    }
    Write-Host "=== Argus started ==="
    exit 0
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
  $buildIdFile = Join-Path $Root "apps\eoc\src\lib\build.ts"
  $buildId = "command-center"
  if (Test-Path $buildIdFile) {
    $m = Select-String -Path $buildIdFile -Pattern 'ARGUS_UI_BUILD\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($m) { $buildId = $m.Matches.Groups[1].Value }
  }
  $publicDir = Split-Path $buildMarker -Parent
  if (-not (Test-Path $publicDir)) {
    New-Item -ItemType Directory -Force -Path $publicDir | Out-Null
  }
  Set-Content -Path $buildMarker -Value "$buildId $sha" -Encoding ascii

  # Never wipe .next while the browser dashboard is serving Start.
  # Desktop Start (no keep) may clear cache after EOC is stopped below.
  if (-not $KeepDashboard) {
    $nextCache = Join-Path $Root "apps\eoc\.next"
    if (Test-Path $nextCache) {
      Write-Host "Clearing stale dashboard cache..."
      Remove-Item -LiteralPath $nextCache -Recurse -Force -ErrorAction SilentlyContinue
    }
  } else {
    Write-Host "Keeping live dashboard cache (browser Start)."
  }

  & "$Root\scripts\infra-up.ps1"
  & "$Root\scripts\migrate-up.ps1"

  $pids = Read-ArgusPids $Root
  $apiPid = $pids.api
  $eocPid = $pids.eoc
  $workerPid = $pids.worker

  # Recycle API after code update. Browser Start must leave the dashboard process up.
  Write-Host "Code refresh - recycling services..."
  Stop-PidIfRunning $pids.api "API launcher"
  if (-not $KeepDashboard) {
    Stop-PidIfRunning $pids.eoc "EOC launcher"
    Stop-ArgusPortListeners @(8000, 3000)
    $eocPid = $null
  } else {
    Stop-ArgusPortListeners @(8000)
    Write-Host "Dashboard left running so browser Start can finish."
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

  # Always recycle the worker on Start so market scan/price jobs load after code sync.
  # Leaving a stale worker up freezes Live Monitor on "Scan delayed / Next pass 0:00".
  Write-Host "Recycling Argus worker (health + market ops)..."
  Stop-PidIfRunning $pids.worker "Worker launcher"
  try {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object {
        $_.CommandLine -and (
          $_.CommandLine -like "*workers.health_supervisor.worker*" -or
          $_.CommandLine -like "*workers.market_ops.worker*"
        )
      } |
      ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
      }
  } catch { }
  $workerPid = Start-ArgusWorkerProcess $Root

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
  } else {
    # Browser Start: leave :3000 alone. Killing EOC here aborts the in-flight
    # Start action and leaves Home stuck on "Working…".
    Write-Host "Browser Start complete — dashboard left running for soft reload."
    Write-Host "REFRESH_HOME_SOFT"
  }
  Write-Host "=== Argus started ==="
} catch {
  Show-ArgusNotification -Title "Argus startup failed" -Message $_.Exception.Message -Level "critical"
  throw
}
