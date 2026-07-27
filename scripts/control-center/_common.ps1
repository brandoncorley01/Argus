# Shared paths for Argus Control Center launchers (sourced by other scripts).
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\_notify.ps1"

function Get-ArgusRoot {
  # scripts/control-center -> repo root
  return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Get-ArgusRuntimeDir([string]$Root) {
  $dir = Join-Path $Root "runtime\control-center"
  if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
  }
  return $dir
}

function Get-ArgusPidFile([string]$Root) {
  return Join-Path (Get-ArgusRuntimeDir $Root) "pids.json"
}

function Get-ArgusDashboardUrl {
  return "http://127.0.0.1:3000/today"
}

function Get-ArgusApiHealthUrl {
  return "http://127.0.0.1:8000/health"
}

function Get-ArgusApiReadyUrl {
  return "http://127.0.0.1:8000/ready"
}

function Sync-ArgusCode([string]$Root) {
  # Founder cadence: Start Argus pulls GitHub main. Returns $true only when SHA changed.
  if (-not (Test-Path (Join-Path $Root ".git"))) {
    Write-Host "Code update skipped (not a git checkout)."
    return $false
  }
  Write-Host "Updating Argus from GitHub main..."
  Push-Location $Root
  try {
    $null = git rev-parse --abbrev-ref HEAD 2>$null
    if ($LASTEXITCODE -ne 0) {
      Write-Host "WARN: git unavailable - continuing with local files."
      return $false
    }
    $before = (git rev-parse HEAD).Trim()
    git fetch origin 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
      Write-Host "WARN: could not reach GitHub - continuing with local files."
      return $false
    }
    git checkout -f -B main "origin/main" 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
      Write-Host "WARN: could not checkout origin/main - continuing with local files."
      return $false
    }
    git reset --hard "origin/main" 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
      Write-Host "WARN: could not reset to origin/main - continuing with local files."
      return $false
    }
    $after = (git rev-parse HEAD).Trim()
    $sha = (git rev-parse --short HEAD).Trim()
    if ($before -ne $after) {
      Write-Host "OK  Updated to main @ $sha"
      return $true
    }
    Write-Host "OK  Already on main @ $sha"
    return $false
  } catch {
    Write-Host "WARN: code update skipped: $($_.Exception.Message)"
    return $false
  } finally {
    Pop-Location
  }
}

function Stop-ArgusPortListeners([int[]]$Ports) {
  foreach ($port in $Ports) {
    try {
      $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
      foreach ($c in $conns) {
        if ($c.OwningProcess) {
          Write-Host "Recycling process on port $port (PID $($c.OwningProcess))"
          Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
      }
    } catch {
      # Ignore when Get-NetTCPConnection is unavailable
    }
  }
  Start-Sleep -Milliseconds 600
}

function Test-HttpOk([string]$Url, [int]$TimeoutSec = 3) {
  try {
    # Allow redirects (e.g. /today -> /login) as "up"
    $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec -MaximumRedirection 5
    return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400)
  } catch {
    # Some hosts throw on 3xx; treat as reachable if a response existed
    if ($_.Exception.Response) { return $true }
    return $false
  }
}

function Wait-HttpOk([string]$Url, [int]$TimeoutSec = 90, [string]$Label = "service") {
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date).AddSeconds(0) -lt $deadline) {
    if (Test-HttpOk $Url) {
      Write-Host "OK  $Label ready ($Url)"
      return $true
    }
    Start-Sleep -Seconds 2
  }
  Write-Host "FAIL $Label not ready within ${TimeoutSec}s ($Url)"
  return $false
}

function Read-ArgusPids([string]$Root) {
  $path = Get-ArgusPidFile $Root
  if (-not (Test-Path $path)) {
    return [pscustomobject]@{ api = $null; eoc = $null; worker = $null }
  }
  try {
    $obj = Get-Content -Raw $path | ConvertFrom-Json
    if (-not ($obj.PSObject.Properties.Name -contains "worker")) {
      $obj | Add-Member -NotePropertyName worker -NotePropertyValue $null -Force
    }
    return $obj
  } catch {
    return [pscustomobject]@{ api = $null; eoc = $null; worker = $null }
  }
}

function Write-ArgusPids([string]$Root, $ApiPid, $EocPid, $WorkerPid = $null) {
  $path = Get-ArgusPidFile $Root
  $obj = [ordered]@{
    api = $ApiPid
    eoc = $EocPid
    worker = $WorkerPid
    updated_at = (Get-Date).ToUniversalTime().ToString("o")
  }
  ($obj | ConvertTo-Json) | Set-Content -Path $path -Encoding utf8
}

function Stop-PidIfRunning([object]$PidValue, [string]$Label) {
  if ($null -eq $PidValue -or "$PidValue" -eq "") { return }
  $procId = [int]$PidValue
  try {
    $null = Get-Process -Id $procId -ErrorAction Stop
    Write-Host "Stopping $Label (PID $procId)..."
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 400
  } catch {
    Write-Host "$Label PID $procId not running"
  }
}

function Start-ArgusApiProcess([string]$Root) {
  $runtime = Get-ArgusRuntimeDir $Root
  $apiLog = Join-Path $runtime "api.log"
  $apiErr = Join-Path $runtime "api.err.log"
  $py = Join-Path $Root "apps\api\.venv\Scripts\python.exe"
  $apiDir = Join-Path $Root "apps\api"
  if (-not (Test-Path $py)) {
    Write-Host "API venv python missing at $py - skip API start"
    return $null
  }
  # Kill any existing uvicorn first (python process, not a transient PowerShell wrapper).
  try {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object {
        $_.Name -eq "python.exe" -and
        $_.CommandLine -and
        $_.CommandLine -like "*uvicorn app.main:app*"
      } |
      ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
      }
  } catch { }
  Start-Sleep -Milliseconds 500
  Write-Host "Starting API on 127.0.0.1:8000 (detached python)..."
  # Launch python.exe directly so killing a PowerShell wrapper cannot take down the API.
  $proc = Start-Process -FilePath $py -PassThru -WindowStyle Hidden `
    -WorkingDirectory $apiDir `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -RedirectStandardOutput $apiLog `
    -RedirectStandardError $apiErr
  return $proc.Id
}

function Start-ArgusWorkerProcess([string]$Root) {
  $runtime = Get-ArgusRuntimeDir $Root
  $workerLog = Join-Path $runtime "worker.log"
  $workerErr = Join-Path $runtime "worker.err.log"
  $py = Join-Path $Root "apps\api\.venv\Scripts\python.exe"
  if (-not (Test-Path $py)) {
    Write-Host "Worker venv python missing at $py - skip worker start"
    return $null
  }
  # Never leave duplicate ARQ workers — they queue-delay scans by many minutes.
  try {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object {
        $_.Name -eq "python.exe" -and
        $_.CommandLine -and (
          $_.CommandLine -like "*workers.health_supervisor.worker*" -or
          $_.CommandLine -like "*workers.market_ops.worker*"
        )
      } |
      ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
      }
  } catch { }
  Start-Sleep -Milliseconds 400
  Write-Host "Starting Argus worker (health + market ops)..."
  $env:PYTHONPATH = "$Root\apps\api;$Root"
  $proc = Start-Process -FilePath $py -PassThru -WindowStyle Hidden `
    -WorkingDirectory $Root `
    -ArgumentList @("-m", "arq", "workers.health_supervisor.worker.WorkerSettings") `
    -RedirectStandardOutput $workerLog `
    -RedirectStandardError $workerErr
  return $proc.Id
}

function Test-ArgusWorkerFresh([string]$Root) {
  # Prefer a live ARQ python process over a stale PID file.
  try {
    $live = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object {
        $_.Name -eq "python.exe" -and
        $_.CommandLine -and (
          $_.CommandLine -like "*workers.health_supervisor.worker*" -or
          $_.CommandLine -like "*workers.market_ops.worker*"
        )
      })
    if ($live.Count -gt 0) { return $true }
  } catch { }
  $pids = Read-ArgusPids $Root
  if ($pids.worker) {
    try {
      $null = Get-Process -Id ([int]$pids.worker) -ErrorAction Stop
      return $true
    } catch {
      return $false
    }
  }
  try {
    $name = docker ps --filter "name=argus-health-supervisor" --format "{{.Names}}" 2>$null
    return [bool]$name
  } catch {
    return $false
  }
}
