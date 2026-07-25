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
  # Founder-friendly: Start Argus always loads the GitHub main Home UI (Start/Stop).
  # Never block startup if offline.
  if (-not (Test-Path (Join-Path $Root ".git"))) {
    Write-Host "Code update skipped (not a git checkout)."
    return $false
  }
  Write-Host "Updating Argus from GitHub main (Home Start/Stop)..."
  Push-Location $Root
  try {
    $null = git rev-parse --abbrev-ref HEAD 2>$null
    if ($LASTEXITCODE -ne 0) {
      Write-Host "WARN: git unavailable - continuing with local files."
      return $false
    }
    git fetch origin 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
      Write-Host "WARN: could not reach GitHub - continuing with local files."
      return $false
    }
    # Always use main. Local divergent UI work must not hide Start/Stop.
    git checkout -B main "origin/main" 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
      Write-Host "WARN: could not checkout origin/main - continuing with local files."
      return $false
    }
    git reset --hard "origin/main" 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
      Write-Host "WARN: could not reset to origin/main - continuing with local files."
      return $false
    }
    $sha = (git rev-parse --short HEAD).Trim()
    Write-Host "OK  Code on main @ $sha"
    return $true
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
    $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
    return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300)
  } catch {
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

function Start-ArgusWorkerProcess([string]$Root) {
  $workerLog = Join-Path (Get-ArgusRuntimeDir $Root) "worker.log"
  $py = Join-Path $Root "apps\api\.venv\Scripts\python.exe"
  if (-not (Test-Path $py)) {
    Write-Host "Worker venv python missing at $py - skip worker start"
    return $null
  }
  Write-Host "Starting health supervisor worker..."
  $cmd = @"
Set-Location '$Root'
`$env:PYTHONPATH = '$Root\apps\api;$Root'
& '$py' -m arq workers.health_supervisor.worker.WorkerSettings *> '$workerLog'
"@
  $proc = Start-Process -FilePath "powershell.exe" -PassThru -WindowStyle Minimized -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $cmd
  )
  return $proc.Id
}

function Test-ArgusWorkerFresh([string]$Root) {
  $pids = Read-ArgusPids $Root
  if ($pids.worker) {
    try {
      $null = Get-Process -Id ([int]$pids.worker) -ErrorAction Stop
      return $true
    } catch {
      return $false
    }
  }
  # Compose profile fallback
  try {
    $name = docker ps --filter "name=argus-health-supervisor" --format "{{.Names}}" 2>$null
    return [bool]$name
  } catch {
    return $false
  }
}
