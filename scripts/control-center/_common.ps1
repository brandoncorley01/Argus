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

function Get-ArgusBuildIdFromText([string]$Text) {
  if (-not $Text) { return $null }
  if ($Text -match 'ARGUS_UI_BUILD\s*=\s*"([^"]+)"') {
    return $Matches[1]
  }
  return $null
}

function Get-ArgusLocalBuildId([string]$Root) {
  $path = Join-Path $Root "apps\eoc\src\lib\build.ts"
  if (-not (Test-Path $path)) { return $null }
  return Get-ArgusBuildIdFromText (Get-Content -Raw $path)
}

function Get-ArgusPublicBuildId([string]$Root) {
  $path = Join-Path $Root "apps\eoc\public\argus-build.txt"
  if (-not (Test-Path $path)) { return $null }
  try {
    $raw = (Get-Content -Raw $path).Trim()
    if (-not $raw) { return $null }
    return ($raw -split '\s+')[0].Trim()
  } catch {
    return $null
  }
}

function Write-ArgusPublicBuildStamp([string]$Root) {
  # Home Build chip reads /argus-build.txt (no Next rebuild required).
  $buildId = Get-ArgusLocalBuildId $Root
  if (-not $buildId) { $buildId = "unknown" }
  $sha = "local"
  try {
    Push-Location $Root
    $sha = (git rev-parse --short HEAD 2>$null).Trim()
    if (-not $sha) { $sha = "local" }
  } catch {
    $sha = "local"
  } finally {
    Pop-Location -ErrorAction SilentlyContinue
  }
  $marker = Join-Path $Root "apps\eoc\public\argus-build.txt"
  $dir = Split-Path $marker -Parent
  if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
  }
  Set-Content -Path $marker -Value "$buildId $sha" -Encoding ascii
  Write-Host ("Build stamp file: {0} ({1})" -f $buildId, $sha)
  return $buildId
}

function Test-ArgusBehindOriginMain([string]$Root) {
  # Returns $true when origin/main SHA or build stamp differs from this PC (after fetch).
  if (-not (Test-Path (Join-Path $Root ".git"))) { return $false }
  Push-Location $Root
  try {
    git fetch origin 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { return $false }
    $local = (git rev-parse HEAD 2>$null).Trim()
    $remote = (git rev-parse "origin/main" 2>$null).Trim()
    if (-not $local -or -not $remote) { return $false }
    if ($local -ne $remote) { return $true }

    # Same SHA should match, but also catch a stale working tree / wrong build.ts.
    $localBuild = Get-ArgusLocalBuildId $Root
    $remoteBuildText = git show "origin/main:apps/eoc/src/lib/build.ts" 2>$null
    $remoteBuild = Get-ArgusBuildIdFromText "$remoteBuildText"
    if ($localBuild -and $remoteBuild -and ($localBuild -ne $remoteBuild)) {
      return $true
    }
    $publicBuild = Get-ArgusPublicBuildId $Root
    if ($remoteBuild -and $publicBuild -and ($publicBuild -ne $remoteBuild)) {
      # Code may already match, but Home is still advertising an old chip — refresh.
      return $true
    }
    return $false
  } catch {
    return $false
  } finally {
    Pop-Location
  }
}

function Sync-ArgusCode([string]$Root) {
  # Founder cadence: Start Argus pulls GitHub main. Returns $true only when SHA changed.
  # Never hard-resets a dirty tree unless ARGUS_FORCE_SYNC=1 (explicit wipe).
  # When this PC is behind origin/main, Start enables force sync so Founder
  # is never stuck on a stale build stamp (e.g. v2.11 while main is newer).
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
  if (-not (Ensure-ArgusEnvFile $Root)) {
    return $false
  }
  if (-not (Ensure-ArgusInfra $Root)) {
    return $false
  }
  if (-not (Ensure-ArgusApiVenv $Root)) {
    return $false
  }
  try {
    & "$Root\scripts\migrate-up.ps1"
  } catch {
    Write-Host "WARN: migrate-up during repair: $($_.Exception.Message)"
  }
  $pids = Read-ArgusPids $Root
  $apiPid = $pids.api
  $workerPid = $pids.worker
  $apiReady = Test-HttpOk (Get-ArgusApiReadyUrl) 3
  if (-not $apiReady) {
    Write-Host "API not ready — starting detached uvicorn..."
    $apiPid = Start-ArgusApiProcess $Root
    if (-not (Wait-HttpOk (Get-ArgusApiReadyUrl) 90 "API /ready")) {
      Write-Host "FAIL API /ready after repair. Last log lines:"
      Write-Host (Get-ArgusApiLogTail $Root 50)
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
      Start-Sleep -Seconds 3
    }
    # Keep-awake is the only guard against the host sleeping mid-session.
    # Restart whenever the helper died — even if API was briefly down.
    if (-not (Test-ArgusKeepAwakeAlive $Root)) {
      Write-Host "Keep-awake missing - restoring sleep protection..."
      $null = Start-ArgusKeepAwake $Root
    }
  }
  Write-ArgusPids -Root $Root -ApiPid $apiPid -EocPid $pids.eoc -WorkerPid $workerPid
  $apiOk = Test-HttpOk (Get-ArgusApiReadyUrl) 3
  if (-not $IncludeWorker) {
    return $apiOk
  }
  # Unattended mode requires BOTH API and worker. API-only "healthy" left
  # Founder with no scans / no data for days while Home still looked Running.
  $workerOk = Test-ArgusWorkerFresh $Root
  if ($apiOk -and -not $workerOk) {
    Write-Host "WARN: API up but worker still down after repair"
  }
  return ($apiOk -and $workerOk)
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

function Ensure-ArgusEnvFile([string]$Root) {
  $envPath = Join-Path $Root ".env"
  if (Test-Path $envPath) { return $true }
  $paper = Join-Path $Root ".env.paper.example"
  $example = Join-Path $Root ".env.example"
  $src = $null
  if (Test-Path $paper) { $src = $paper }
  elseif (Test-Path $example) { $src = $example }
  if (-not $src) {
    Write-Host "FAIL Missing .env and no example to copy."
    return $false
  }
  Copy-Item -LiteralPath $src -Destination $envPath -Force
  Write-Host "Created .env from $(Split-Path $src -Leaf). Edit POSTGRES_PASSWORD if needed."
  return $true
}

function Ensure-ArgusApiVenv([string]$Root) {
  # Recreate apps/api/.venv when missing or unable to import uvicorn.
  $apiDir = Join-Path $Root "apps\api"
  $py = Join-Path $apiDir ".venv\Scripts\python.exe"
  if (Test-Path $py) {
    & $py -c "import uvicorn" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { return $true }
    Write-Host "API venv present but uvicorn import failed — rebuilding..."
  } else {
    Write-Host "API venv missing — creating with uv sync..."
  }
  Push-Location $apiDir
  try {
    $synced = $false
    if (Get-Command uv -ErrorAction SilentlyContinue) {
      uv sync 2>&1 | Out-Host
      $synced = ($LASTEXITCODE -eq 0)
    }
    if (-not $synced) {
      python -m uv sync 2>&1 | Out-Host
      $synced = ($LASTEXITCODE -eq 0)
    }
    if (-not (Test-Path $py)) {
      Write-Host "FAIL API venv still missing after uv sync at $py"
      return $false
    }
    & $py -c "import uvicorn" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
      Write-Host "FAIL API venv cannot import uvicorn after sync."
      return $false
    }
    Write-Host "OK  API venv ready"
    return $true
  } catch {
    Write-Host "FAIL Ensure-ArgusApiVenv: $($_.Exception.Message)"
    return $false
  } finally {
    Pop-Location
  }
}

function Get-ArgusApiLogTail([string]$Root, [int]$Lines = 40) {
  $runtime = Get-ArgusRuntimeDir $Root
  $chunks = @()
  foreach ($name in @("api.err.log", "api.log")) {
    $path = Join-Path $runtime $name
    if (Test-Path $path) {
      $chunks += "--- $name ---"
      try {
        $chunks += Get-Content -Path $path -Tail $Lines -ErrorAction SilentlyContinue
      } catch { }
    }
  }
  return ($chunks -join "`n")
}

function Start-ArgusApiProcess([string]$Root) {
  $runtime = Get-ArgusRuntimeDir $Root
  $apiLog = Join-Path $runtime "api.log"
  $apiErr = Join-Path $runtime "api.err.log"
  $apiDir = Join-Path $Root "apps\api"
  if (-not (Ensure-ArgusApiVenv $Root)) {
    Write-Host "API venv unavailable — cannot start API"
    return $null
  }
  $py = Join-Path $apiDir ".venv\Scripts\python.exe"
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
        $_.CommandLine -and (
          (
            $_.Name -eq "powershell.exe" -and
            $_.CommandLine -like "*keep-awake-argus.ps1*"
          ) -or (
            ($_.Name -eq "wscript.exe" -or $_.Name -eq "cscript.exe") -and
            $_.CommandLine -like "*run-hidden.vbs*" -and
            $_.CommandLine -like "*keep-awake-argus.ps1*"
          )
        )
      } |
      ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
      }
  } catch { }
}

function Start-ArgusHiddenPowerShell {
  # Launch a .ps1 with no console window. Prefer wscript + run-hidden.vbs
  # (window style 0). CreateNoWindow alone still flashes on some Windows builds.
  param(
    [Parameter(Mandatory = $true)][string]$ScriptPath,
    [string]$WorkingDirectory = $null,
    [string[]]$ExtraArgs = @()
  )
  if (-not (Test-Path $ScriptPath)) {
    throw "Script missing: $ScriptPath"
  }
  $work = if ($WorkingDirectory) { $WorkingDirectory } else { Split-Path -Parent $ScriptPath }
  $vbs = Join-Path $PSScriptRoot "run-hidden.vbs"
  if (Test-Path $vbs) {
    # Fire-and-forget via VBS so keep-awake can stay resident; VBS waits on PS,
    # so launch VBS itself without waiting (CreateNoWindow on wscript).
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = (Get-Command wscript.exe).Source
    $argList = @(
      "//B", "//nologo",
      ('"{0}"' -f ($vbs -replace '"', '""')),
      ('"{0}"' -f ($ScriptPath -replace '"', '""'))
    )
    foreach ($a in $ExtraArgs) {
      if ($null -eq $a) { continue }
      $argList += ('"{0}"' -f ([string]$a -replace '"', '""'))
    }
    $psi.Arguments = [string]::Join(" ", $argList)
    $psi.WorkingDirectory = $work
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    return [System.Diagnostics.Process]::Start($psi)
  }

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
