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

function Get-ArgusDesiredStatePath([string]$Root) {
  return Join-Path (Get-ArgusRuntimeDir $Root) "desired-state.json"
}

function Read-ArgusDesiredState([string]$Root) {
  $path = Get-ArgusDesiredStatePath $Root
  if (-not (Test-Path $path)) {
    return [pscustomobject]@{ running = $false; updated_at = $null }
  }
  try {
    # Strip UTF-8 BOM if an older writer left one (Node JSON.parse rejects BOM).
    $raw = [System.IO.File]::ReadAllText($path)
    if ($raw.Length -gt 0 -and [int][char]$raw[0] -eq 0xFEFF) {
      $raw = $raw.Substring(1)
    }
    $obj = $raw | ConvertFrom-Json
    $running = $false
    if ($null -ne $obj.running) { $running = [bool]$obj.running }
    return [pscustomobject]@{
      running = $running
      updated_at = $obj.updated_at
    }
  } catch {
    return [pscustomobject]@{ running = $false; updated_at = $null }
  }
}

function Write-ArgusDesiredState([string]$Root, [bool]$Running) {
  $path = Get-ArgusDesiredStatePath $Root
  $obj = [ordered]@{
    running = $Running
    updated_at = (Get-Date).ToUniversalTime().ToString("o")
  }
  # UTF-8 without BOM so Node JSON.parse on the login page does not fail.
  $json = ($obj | ConvertTo-Json)
  [System.IO.File]::WriteAllText($path, $json + "`n", [System.Text.UTF8Encoding]::new($false))
}

function Test-DockerEngineReady {
  try {
    $null = docker info 2>$null
    return ($LASTEXITCODE -eq 0)
  } catch {
    return $false
  }
}

function Ensure-DockerEngine {
  # Start Docker Desktop if the engine is down; wait until `docker info` works.
  if (Test-DockerEngineReady) {
    Write-Host "OK  Docker engine ready"
    return $true
  }

  $candidates = @(
    (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe"),
    (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
  ) | Where-Object { $_ -and (Test-Path $_) }

  if ($candidates.Count -eq 0) {
    Write-Host "FAIL Docker Desktop not found. Install Docker Desktop, then Start Argus again."
    return $false
  }

  Write-Host "Docker engine not ready — launching Docker Desktop..."
  try {
    Start-Process -FilePath $candidates[0] -ErrorAction SilentlyContinue | Out-Null
  } catch {
    Write-Host "WARN: could not launch Docker Desktop: $($_.Exception.Message)"
  }

  $deadline = (Get-Date).AddSeconds(180)
  while ((Get-Date) -lt $deadline) {
    if (Test-DockerEngineReady) {
      Write-Host "OK  Docker engine ready"
      return $true
    }
    Start-Sleep -Seconds 3
  }
  Write-Host "FAIL Docker engine did not become ready within 180s"
  Write-Host "Open Docker Desktop (sign in if prompted), wait until it says Running, then Start Argus again."
  return $false
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

function Test-ArgusGitDirty([string]$Root) {
  Push-Location $Root
  try {
    $porcelain = @(git status --porcelain 2>$null)
    return ($LASTEXITCODE -eq 0 -and $porcelain.Count -gt 0)
  } catch {
    return $false
  } finally {
    Pop-Location
  }
}

function Sync-ArgusCode([string]$Root) {
  # Founder cadence: Start Argus pulls GitHub main. Returns $true only when SHA changed.
  # Never hard-resets a dirty tree unless ARGUS_FORCE_SYNC=1 (explicit wipe).
  if (-not (Test-Path (Join-Path $Root ".git"))) {
    Write-Host "Code update skipped (not a git checkout)."
    return $false
  }
  $forceSync = $env:ARGUS_FORCE_SYNC -eq "1"
  if (-not $forceSync -and (Test-ArgusGitDirty $Root)) {
    Write-Host "WARN: local git changes present — skipping GitHub sync (set ARGUS_FORCE_SYNC=1 to overwrite)."
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
    if ($forceSync) {
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
    } else {
      git checkout main 2>&1 | Out-Host
      if ($LASTEXITCODE -ne 0) {
        git checkout -B main "origin/main" 2>&1 | Out-Host
      }
      git merge --ff-only "origin/main" 2>&1 | Out-Host
      if ($LASTEXITCODE -ne 0) {
        Write-Host "WARN: could not fast-forward to origin/main - continuing with local files."
        return $false
      }
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

function Test-ArgusInfraHealthy {
  try {
    $rows = @(docker ps --format "{{.Names}} {{.Status}}" 2>$null)
    $pg = $false
    $redis = $false
    foreach ($row in $rows) {
      if ($row -match "^argus-postgres\b" -and $row -match "\(healthy\)") { $pg = $true }
      if ($row -match "^argus-redis\b" -and $row -match "\(healthy\)") { $redis = $true }
    }
    return ($pg -and $redis)
  } catch {
    return $false
  }
}

function Ensure-ArgusInfra([string]$Root) {
  # Lightweight: Docker engine + postgres/redis only. Never git-sync here.
  if (-not (Ensure-DockerEngine)) {
    return $false
  }
  if (Test-ArgusInfraHealthy) {
    Write-Host "OK  Postgres + Redis healthy"
    return $true
  }
  Write-Host "Postgres/Redis not healthy — starting Docker infra..."
  Push-Location $Root
  try {
    # Explicit start recovers containers left Exited after Stop / engine sleep.
    docker compose up -d postgres redis | Out-Host
    if ($LASTEXITCODE -ne 0) {
      Write-Host "WARN: compose up exited $LASTEXITCODE — retrying start..."
      docker start argus-postgres argus-redis 2>$null | Out-Host
    }
  } catch {
    Write-Host "FAIL Could not start Docker infra: $($_.Exception.Message)"
    Write-Host "Open Docker Desktop, then press Start Argus again."
    Pop-Location
    return $false
  }
  Pop-Location
  $deadline = (Get-Date).AddSeconds(90)
  while ((Get-Date) -lt $deadline) {
    if (Test-ArgusInfraHealthy) {
      Write-Host "OK  Postgres + Redis healthy"
      return $true
    }
    Start-Sleep -Seconds 2
  }
  Write-Host "FAIL Postgres/Redis did not become healthy within 90s"
  Write-Host "Open Docker Desktop, then press Start Argus again."
  return $false
}

function Test-ArgusApiProcessLive {
  try {
    $live = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object {
        $_.Name -eq "python.exe" -and
        $_.CommandLine -and
        $_.CommandLine -like "*uvicorn app.main:app*"
      })
    return ($live.Count -gt 0)
  } catch {
    return $false
  }
}

function Repair-ArgusRuntime([string]$Root, [switch]$IncludeWorker) {
  # Bring infra + API (+ optional worker) back without git sync.
  if (-not (Ensure-ArgusInfra $Root)) {
    return $false
  }
  $pids = Read-ArgusPids $Root
  $apiPid = $pids.api
  $workerPid = $pids.worker
  $apiReady = Test-HttpOk (Get-ArgusApiReadyUrl) 3
  if (-not $apiReady) {
    Write-Host "API not ready — starting detached uvicorn..."
    $apiPid = Start-ArgusApiProcess $Root
    if (-not (Wait-HttpOk (Get-ArgusApiReadyUrl) 90 "API /ready")) {
      Write-ArgusPids -Root $Root -ApiPid $apiPid -EocPid $pids.eoc -WorkerPid $workerPid
      return $false
    }
  } elseif (-not (Test-ArgusApiProcessLive)) {
    # Rare: something else answering on :8000 — leave it, still record readiness.
    Write-Host "OK  API /ready responding"
  }
  if ($IncludeWorker) {
    if (-not (Test-ArgusWorkerFresh $Root)) {
      Write-Host "Worker missing — starting health supervisor / market ops..."
      $workerPid = Start-ArgusWorkerProcess $Root
      Start-Sleep -Seconds 2
    }
    # Keep-awake is the only guard against the host sleeping mid-session, and
    # nothing else restarts it once it exits.
    if (-not (Test-ArgusKeepAwakeAlive $Root)) {
      Write-Host "Keep-awake missing - restoring sleep protection..."
      $null = Start-ArgusKeepAwake $Root
    }
  }
  Write-ArgusPids -Root $Root -ApiPid $apiPid -EocPid $pids.eoc -WorkerPid $workerPid
  return (Test-HttpOk (Get-ArgusApiReadyUrl) 3)
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

function Clear-ArgusArqBacklog {
  # Drop stale ARQ jobs so minute scans are not buried under multi-hour backlog.
  try {
    $keys = @(docker exec argus-redis redis-cli --scan --pattern "arq:*" 2>$null)
    if ($keys.Count -eq 0) {
      Write-Host "OK  ARQ queue empty"
      return
    }
    Write-Host ("Clearing {0} ARQ redis keys (stale job backlog)..." -f $keys.Count)
    foreach ($batch in (0..([math]::Ceiling($keys.Count / 100) - 1))) {
      $slice = $keys[($batch * 100)..([math]::Min(($batch + 1) * 100 - 1, $keys.Count - 1))]
      if ($slice) {
        docker exec argus-redis redis-cli DEL @slice 2>$null | Out-Null
      }
    }
    Write-Host "OK  ARQ backlog cleared"
  } catch {
    Write-Host "WARN: could not clear ARQ backlog: $($_.Exception.Message)"
  }
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
  Clear-ArgusArqBacklog
  Write-Host "Starting Argus worker (health + market ops, max_jobs=3)..."
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

function Get-ArgusKeepAwakePidFile([string]$Root) {
  return Join-Path (Get-ArgusRuntimeDir $Root) "keep-awake.pid"
}

function Stop-ArgusKeepAwake([string]$Root) {
  # Release OS stay-awake request and stop the helper process.
  $pidPath = Get-ArgusKeepAwakePidFile $Root
  if (Test-Path $pidPath) {
    try {
      $keepPid = [int](Get-Content -Path $pidPath -ErrorAction Stop | Select-Object -First 1)
      if ($keepPid -gt 0) {
        Stop-Process -Id $keepPid -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped keep-awake (PID $keepPid)"
      }
    } catch {
      Write-Host "Keep-awake PID file unreadable — sweeping by command line"
    }
    Remove-Item -Path $pidPath -Force -ErrorAction SilentlyContinue
  }
  try {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object {
        $_.Name -eq "powershell.exe" -and
        $_.CommandLine -and
        $_.CommandLine -like "*keep-awake-argus.ps1*"
      } |
      ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
      }
  } catch { }
}

function Start-ArgusHiddenPowerShell {
  # Launch a .ps1 with no console window (CreateNoWindow). Prefer this over
  # Start-Process -WindowStyle Hidden, which still flashes on many Windows builds.
  param(
    [Parameter(Mandatory = $true)][string]$ScriptPath,
    [string]$WorkingDirectory = $null,
    [string[]]$ExtraArgs = @()
  )
  if (-not (Test-Path $ScriptPath)) {
    throw "Script missing: $ScriptPath"
  }
  $work = if ($WorkingDirectory) { $WorkingDirectory } else { Split-Path -Parent $ScriptPath }
  $argParts = @(
    "-NoProfile",
    "-NoLogo",
    "-NonInteractive",
    "-ExecutionPolicy", "Bypass",
    "-WindowStyle", "Hidden",
    "-File", $ScriptPath
  ) + $ExtraArgs
  $quoted = foreach ($a in $argParts) {
    if ($null -eq $a) { continue }
    $s = [string]$a
    if ($s -match '[\s"]') { '"' + ($s -replace '"', '\"') + '"' } else { $s }
  }
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = (Get-Command powershell.exe).Source
  $psi.Arguments = [string]::Join(" ", $quoted)
  $psi.WorkingDirectory = $work
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
  $psi.RedirectStandardOutput = $false
  $psi.RedirectStandardError = $false
  return [System.Diagnostics.Process]::Start($psi)
}

function Start-ArgusKeepAwake([string]$Root) {
  # One helper process: prevents automatic sleep/hibernate while Argus is Running.
  Stop-ArgusKeepAwake $Root
  $script = Join-Path $PSScriptRoot "keep-awake-argus.ps1"
  if (-not (Test-Path $script)) {
    Write-Host "WARN: keep-awake script missing at $script"
    return $null
  }
  Write-Host "Starting Argus keep-awake (blocks automatic sleep/hibernate until Stop)..."
  try {
    $proc = Start-ArgusHiddenPowerShell -ScriptPath $script -WorkingDirectory $Root
  } catch {
    Write-Host "WARN: keep-awake launch failed: $($_.Exception.Message)"
    return $null
  }
  # PID file is also written by the script; seed it immediately for Stop races.
  $pidPath = Get-ArgusKeepAwakePidFile $Root
  try {
    $proc.Id | Set-Content -Path $pidPath -Encoding utf8
  } catch { }

  # A parse error or a failed Add-Type kills the helper before it writes its own
  # log, so the only reliable signal is whether the process is still alive.
  Start-Sleep -Seconds 3
  if (-not (Test-ArgusKeepAwakeAlive $Root)) {
    Remove-Item -Path $pidPath -Force -ErrorAction SilentlyContinue
    Write-Host "WARN: keep-awake exited immediately - automatic sleep is NOT blocked."
    Write-Host "      Diagnose with: powershell -NoProfile -ExecutionPolicy Bypass -File `"$script`""
    Show-ArgusNotification -Title "Argus sleep protection failed" -Message "The keep-awake helper could not start. Windows may sleep and pause scanning." -Level "critical"
    return $null
  }
  return $proc.Id
}

function Test-ArgusKeepAwakeAlive([string]$Root) {
  $pidPath = Get-ArgusKeepAwakePidFile $Root
  if (-not (Test-Path $pidPath)) { return $false }
  try {
    $keepPid = [int](Get-Content -Path $pidPath -ErrorAction Stop | Select-Object -First 1)
    $null = Get-Process -Id $keepPid -ErrorAction Stop
    return $true
  } catch {
    return $false
  }
}
