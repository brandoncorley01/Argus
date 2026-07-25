# Start Argus Control Center - update code, infra, API, worker, dashboard; open Today.
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

  # You should not need to run git yourself - Start keeps the Founder UI current.
  $updated = Sync-ArgusCode $Root

  # Drop stale Next.js cache so Home Start/Stop cannot be masked by old builds.
  $nextCache = Join-Path $Root "apps\eoc\.next"
  if ($updated -and (Test-Path $nextCache)) {
    Write-Host "Clearing stale dashboard cache..."
    Remove-Item -LiteralPath $nextCache -Recurse -Force -ErrorAction SilentlyContinue
  }

  & "$Root\scripts\infra-up.ps1"
  & "$Root\scripts\migrate-up.ps1"

  $pids = Read-ArgusPids $Root
  $apiPid = $pids.api
  $eocPid = $pids.eoc
  $workerPid = $pids.worker

  # After a code update, recycle API (and dashboard only when not started from the browser).
  if ($updated) {
    Write-Host "Code changed - refreshing services..."
    Stop-PidIfRunning $pids.api "API launcher"
    if (-not $KeepDashboard) {
      Stop-PidIfRunning $pids.eoc "EOC launcher"
      Stop-ArgusPortListeners @(8000, 3000)
      $eocPid = $null
    } else {
      Stop-ArgusPortListeners @(8000)
      Write-Host "Keeping dashboard running (browser Start)."
    }
    $apiPid = $null
  }

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

  # Dashboard: keep as-is from browser Start; otherwise start/recycle as needed.
  $eocUp = (Test-HttpOk "http://127.0.0.1:3000/login") -or (Test-HttpOk "http://127.0.0.1:3000/") -or (Test-HttpOk (Get-ArgusDashboardUrl) 2)
  if ($KeepDashboard) {
    Write-Host "Dashboard left running for browser control"
  } elseif ($updated -or -not $eocUp) {
    if ($eocUp -and -not $updated) {
      Write-Host "EOC already responding"
    } else {
      if ($eocUp) {
        Stop-ArgusPortListeners @(3000)
      }
      Write-Host "Starting dashboard on 127.0.0.1:3000..."
      $eocLog = Join-Path (Get-ArgusRuntimeDir $Root) "eoc.log"
      $envBlock = "`$env:ARGUS_API_BASE_URL='http://127.0.0.1:8000'"
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
  }
  Write-Host "=== Argus started ==="
} catch {
  Show-ArgusNotification -Title "Argus startup failed" -Message $_.Exception.Message -Level "critical"
  throw
}
