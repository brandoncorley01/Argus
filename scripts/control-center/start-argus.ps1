# Start Argus Control Center - update code, infra, API, worker, dashboard; open Home.
$ErrorActionPreference = "Continue"

# ALWAYS refresh Start control-plane scripts from GitHub main BEFORE sourcing
# _common.ps1. Dirty local copies previously blocked self-update and left the
# Founder stuck on stale build stamps (e.g. v2.11). Control-center scripts are
# not founder data — Start means take GitHub's Start scripts.
if (-not $env:ARGUS_START_SELF_UPDATED) {
  $env:ARGUS_START_SELF_UPDATED = "1"
  $self = $MyInvocation.MyCommand.Path
  if (-not $self) { $self = Join-Path $PSScriptRoot "start-argus.ps1" }
  $scriptDir = Split-Path $self -Parent
  $skipSelfUpdate = $env:ARGUS_SKIP_START_SELF_UPDATE -eq "1"
  if ($skipSelfUpdate) {
    Write-Host "Skipping Start script self-update (ARGUS_SKIP_START_SELF_UPDATE=1)."
  } else {
    function ConvertTo-ArgusUtf8Text($Content) {
      if ($null -eq $Content) { return $null }
      if ($Content -is [byte[]]) {
        return [System.Text.Encoding]::UTF8.GetString($Content)
      }
      if ($Content -is [System.Array] -and $Content.Length -gt 0 -and ($Content[0] -is [byte])) {
        return [System.Text.Encoding]::UTF8.GetString([byte[]]$Content)
      }
      $s = [string]$Content
      if ($s.TrimStart().StartsWith('{') -and $s -match '"encoding"\s*:\s*"base64"' -and $s -match '"content"\s*:\s*"([^"]+)"') {
        $b64 = ($Matches[1] -replace '\\n', '')
        try {
          return [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64))
        } catch {
          return $s
        }
      }
      return $s
    }

    function Get-ArgusGitHubText([string]$RepoPath) {
      # GitHub Contents API — decode WinPS byte[] / JSON+base64 quirks.
      $api = "https://api.github.com/repos/brandoncorley01/Argus/contents/{0}?ref=main" -f $RepoPath.TrimStart('/')
      $resp = Invoke-WebRequest -Uri $api -Headers @{
        Accept = "application/vnd.github.raw"
        "User-Agent" = "ArgusStartSelfUpdate"
      } -UseBasicParsing -TimeoutSec 45
      if (-not $resp.Content) { throw "empty GitHub API body for $RepoPath" }
      $text = ConvertTo-ArgusUtf8Text $resp.Content
      if (-not $text) { throw "could not decode GitHub body for $RepoPath" }
      return $text
    }

    $files = @(
      @{ Name = "start-argus.ps1"; Path = "scripts/control-center/start-argus.ps1"; Required = $true },
      @{ Name = "_common.ps1"; Path = "scripts/control-center/_common.ps1"; Required = $true },
      @{ Name = "run-hidden.vbs"; Path = "scripts/control-center/run-hidden.vbs"; Required = $true },
      @{ Name = "install-keepalive-task.ps1"; Path = "scripts/control-center/install-keepalive-task.ps1"; Required = $true },
      @{ Name = "keep-argus-alive.ps1"; Path = "scripts/control-center/keep-argus-alive.ps1"; Required = $true },
      @{ Name = "keep-awake-argus.ps1"; Path = "scripts/control-center/keep-awake-argus.ps1"; Required = $true },
      @{ Name = "recycle-eoc.ps1"; Path = "scripts/control-center/recycle-eoc.ps1"; Required = $false },
      @{ Name = "update-argus-now.ps1"; Path = "scripts/control-center/update-argus-now.ps1"; Required = $false },
      @{ Name = "bring-argus-up.ps1"; Path = "scripts/control-center/bring-argus-up.ps1"; Required = $false },
      @{ Name = "diagnose-argus-folder.ps1"; Path = "scripts/control-center/diagnose-argus-folder.ps1"; Required = $false },
      @{ Name = "repair-argus-api.ps1"; Path = "scripts/control-center/repair-argus-api.ps1"; Required = $false },
      @{ Name = "install-desktop-shortcuts.ps1"; Path = "scripts/control-center/install-desktop-shortcuts.ps1"; Required = $false }
    )
    $changed = $false
    # Also refresh root launcher cmds so Founder gets Update-Argus.cmd + force-sync Start.
    try {
      $repoRoot = Split-Path $scriptDir -Parent | Split-Path -Parent
      foreach ($leaf in @("Start-Argus.cmd", "Update-Argus.cmd", "GET-LATEST.cmd", "Diagnose-Argus.cmd", "FIX-PC.cmd", "Bring-Argus-Up.cmd")) {
        $dest = Join-Path $repoRoot $leaf
        try {
          $remote = Get-ArgusGitHubText $leaf
          if ($remote) {
            $local = if (Test-Path $dest) { Get-Content -Raw $dest } else { "" }
            if ($remote -ne $local) {
              Set-Content -Path $dest -Value $remote -Encoding ascii
              $changed = $true
              Write-Host ("Updated {0}" -f $leaf)
            }
          }
        } catch {
          Write-Host ("WARN: could not refresh {0}: {1}" -f $leaf, $_.Exception.Message)
        }
      }
    } catch { }
    try {
      Write-Host "Downloading latest Start scripts from GitHub API (not CDN)..."
      foreach ($f in $files) {
        $dest = Join-Path $scriptDir $f.Name
        try {
          $remote = Get-ArgusGitHubText $f.Path
          if (-not $remote) { throw "empty download for $($f.Name)" }
          $local = if (Test-Path $dest) { Get-Content -Raw $dest } else { "" }
          if ($remote -ne $local) {
            # Preserve UTF-8 for .ps1; ascii for .vbs is fine via Set-Content utf8
            Set-Content -Path $dest -Value $remote -Encoding utf8
            $changed = $true
            Write-Host ("Updated {0}" -f $f.Name)
          }
        } catch {
          if ($f.Required) { throw }
          Write-Host ("WARN: optional {0} not downloaded: {1}" -f $f.Name, $_.Exception.Message)
        }
      }
      if ($changed) {
        Write-Host "Re-running updated Start script..."
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $self @args
        exit $LASTEXITCODE
      }
      Write-Host "Start scripts already current."
    } catch {
      Write-Host "ERROR: could not self-update Start scripts: $($_.Exception.Message)"
      Write-Host "Refusing to Fast-Start on stale local scripts (this is how PCs get stuck on v2.40)."
      Write-Host "Paste this in PowerShell, then Ctrl+F5 Home:"
      Write-Host '  iex (irm -Headers @{Accept=''application/vnd.github.raw''} ''https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/update-argus-now.ps1?ref=main'')'
      throw "Start aborted: self-update failed. Run update-argus-now via GitHub API irm | iex."
    }
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

  # Founder intent: Argus should stay up until Stop. Persist before repair so
  # keepalive can recover Docker sleep / API crash without another click.
  Write-ArgusDesiredState -Root $Root -Running $true
  try {
    & "$PSScriptRoot\install-keepalive-task.ps1"
  } catch {
    Write-Host "WARN: keepalive task not registered: $($_.Exception.Message)"
  }

  # Login/API cannot work without Docker postgres+redis. Ensure before any
  # "already running" / repair path so Start never leaves a hung :8000 listener.
  if (-not (Ensure-ArgusInfra $Root)) {
    throw "Docker infrastructure is not healthy. Open Docker Desktop and Start again."
  }

  # Cloud-agent merges only work if THIS PC hard-syncs to GitHub main on every
  # Start. Fast Start used to skip git while services were healthy — Founder
  # stayed on v2.40 while main already had v2.43+. Always force-sync unless
  # ARGUS_ALLOW_STALE=1 (emergency offline escape hatch).
  $publicBuildBefore = Get-ArgusPublicBuildId $Root
  $localBuild = Get-ArgusLocalBuildId $Root
  $allowStale = $env:ARGUS_ALLOW_STALE -eq "1"
  if ($allowStale) {
    Write-Host "ARGUS_ALLOW_STALE=1 — skipping GitHub hard-sync (emergency)."
    $forceSync = $false
    $env:ARGUS_FORCE_SYNC = "0"
    $updated = $false
  } else {
    $forceSync = $true
    $env:ARGUS_FORCE_SYNC = "1"
    Write-Host ("Hard-syncing this PC to GitHub main (was build {0})..." -f $(if ($localBuild) { $localBuild } else { "?" }))
    $updated = Sync-ArgusCode $Root
  }

  # Stamp + Desktop report BEFORE any fast-path exit so Founder can prove sync.
  $buildId = Write-ArgusPublicBuildStamp $Root
  $syncMatch = Write-ArgusStartReport -Root $Root -BuildId $buildId -Updated ([bool]$updated) -Outcome "synced"
  if ($syncMatch -eq "MISMATCH" -and -not $allowStale) {
    throw "GitHub sync MISMATCH after reset. Wrong folder or origin. See Desktop Argus-last-start.txt"
  }

  $apiReadyNow = Test-HttpOk (Get-ArgusApiReadyUrl) 3
  $eocReadyNow = (Test-HttpOk "http://127.0.0.1:3000/login" 3) -or (Test-HttpOk "http://127.0.0.1:3000/" 3) -or (Test-HttpOk (Get-ArgusDashboardUrl) 3)
  $workerReadyNow = Test-ArgusWorkerFresh $Root

  # CRITICAL: :3000 can be a different Argus checkout than $Root (e.g. shortcut
  # syncs Desktop\Argus while Documents\Argus still serves Home). Fast Start used
  # to treat "any :3000 up" as success and leave v2.40 on screen.
  $httpBuild = Get-ArgusHttpBuildId
  if ($eocReadyNow -and $buildId -and $httpBuild -and ($httpBuild -ne $buildId)) {
    Write-Host ("STALE/FOREIGN dashboard on :3000 — HTTP build={0}, this folder={1}." -f $httpBuild, $buildId)
    Write-Host ("Killing :3000 and starting dashboard from: {0}" -f $Root)
    $KeepDashboard = $false
    $env:ARGUS_KEEP_DASHBOARD = "0"
    $eocReadyNow = $false
    $updated = $true
    try { Stop-ArgusPortListeners @(3000) } catch { }
    try {
      Get-Process -Name node -ErrorAction SilentlyContinue | ForEach-Object {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
        if ($cmd -and ($cmd -like "*eoc*" -or $cmd -like "*next*" -or $cmd -like "*Argus*")) {
          Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        }
      }
    } catch { }
    Start-Sleep -Seconds 2
  } elseif ($eocReadyNow -and $buildId -and -not $httpBuild) {
    Write-Host "WARN: :3000 is up but /argus-build.txt missing — forcing dashboard recycle from this folder."
    $KeepDashboard = $false
    $env:ARGUS_KEEP_DASHBOARD = "0"
    $eocReadyNow = $false
    $updated = $true
    try { Stop-ArgusPortListeners @(3000) } catch { }
  }

  # Light repair: API + dashboard up, only worker missing — code already synced.
  if ($apiReadyNow -and $eocReadyNow -and -not $workerReadyNow -and -not $updated) {
    Write-Host "API + dashboard up; worker down — repairing worker only."
    $pids = Read-ArgusPids $Root
    if (-not (Test-HttpOk (Get-ArgusApiReadyUrl) 3)) {
      $apiPid = Start-ArgusApiProcess $Root
    } else {
      $apiPid = $pids.api
    }
    $workerPid = Start-ArgusWorkerProcess $Root
    Write-ArgusPids -Root $Root -ApiPid $apiPid -EocPid $pids.eoc -WorkerPid $workerPid
    Start-Sleep -Seconds 2
    Write-Host "OK  Worker repair attempted."
    $null = Write-ArgusPublicBuildStamp $Root
    $null = Start-ArgusKeepAwake $Root
    if (-not $KeepDashboard) { Start-Process (Get-ArgusDashboardUrl) } else { Write-Host "REFRESH_HOME_SOFT" }
    Write-Host "=== Argus started ==="
    exit 0
  }

  # Light repair: dashboard up, API down — code already synced.
  if ($eocReadyNow -and -not $apiReadyNow -and -not $updated) {
    Write-Host "Dashboard up; API down — repairing infra + API."
    if (-not (Ensure-ArgusInfra $Root)) {
      throw "Docker infrastructure is not healthy. Open Docker Desktop and Start again."
    }
    $pids = Read-ArgusPids $Root
    $apiPid = Start-ArgusApiProcess $Root
    if (-not (Test-ArgusWorkerFresh $Root)) {
      $workerPid = Start-ArgusWorkerProcess $Root
    } else {
      $workerPid = $pids.worker
    }
    Write-ArgusPids -Root $Root -ApiPid $apiPid -EocPid $pids.eoc -WorkerPid $workerPid
    if (-not (Wait-HttpOk (Get-ArgusApiReadyUrl) 90 "API /ready")) {
      throw "API /ready still failing after repair. Check Docker Desktop and Start again."
    }
    $null = Write-ArgusPublicBuildStamp $Root
    $null = Start-ArgusKeepAwake $Root
    if (-not $KeepDashboard) { Start-Process (Get-ArgusDashboardUrl) } else { Write-Host "REFRESH_HOME_SOFT" }
    Write-Host "=== Argus started ==="
    exit 0
  }

  # Fast path ONLY when already on the synced SHA (no code change this Start).
  # Never skip sync — that was the cloud-agent "rarely works" bug.
  if ($apiReadyNow -and $eocReadyNow -and $workerReadyNow -and -not $updated) {
    Write-Host ("Argus already running on GitHub main — build {0} (no recycle needed)." -f $buildId)
    $pids = Read-ArgusPids $Root
    # uvicorn/arq each spawn a child with the same cmdline. Count tree roots only —
    # never treat parent+child as "duplicates" (that killed the only worker).
    try {
      $uvs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
          $_.Name -eq "python.exe" -and
          $_.CommandLine -and
          $_.CommandLine -like "*uvicorn app.main:app*"
        })
      $uvIds = @($uvs | ForEach-Object { $_.ProcessId })
      $uvRoots = @($uvs | Where-Object { $uvIds -notcontains $_.ParentProcessId } | Sort-Object ProcessId)
      if ($uvRoots.Count -gt 1) {
        Write-Host "Removing duplicate API process trees..."
        $keepApi = $uvRoots[0].ProcessId
        $uvRoots | Where-Object { $_.ProcessId -ne $keepApi } | ForEach-Object {
          Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
      }
      $wps = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
          $_.Name -eq "python.exe" -and
          $_.CommandLine -and (
            $_.CommandLine -like "*workers.health_supervisor.worker*" -or
            $_.CommandLine -like "*workers.market_ops.worker*"
          )
        })
      $wpIds = @($wps | ForEach-Object { $_.ProcessId })
      $wpRoots = @($wps | Where-Object { $wpIds -notcontains $_.ParentProcessId })
      if ($wpRoots.Count -gt 1) {
        Write-Host "Multiple worker trees detected — recycling to a single worker..."
        $pids.worker = Start-ArgusWorkerProcess $Root
      }
    } catch { }
    # If /ready flipped down during Start, bring API back without a full sync.
    if (-not (Test-HttpOk (Get-ArgusApiReadyUrl) 3)) {
      Write-Host "API became unreachable — restarting detached API..."
      $apiPid = Start-ArgusApiProcess $Root
      $pids = Read-ArgusPids $Root
      Write-ArgusPids -Root $Root -ApiPid $apiPid -EocPid $pids.eoc -WorkerPid $pids.worker
      $null = Wait-HttpOk (Get-ArgusApiReadyUrl) 60 "API /ready"
    }
    # Fast path must never exit with a dead worker.
    if (-not (Test-ArgusWorkerFresh $Root)) {
      Write-Host "Worker missing after fast Start — repairing..."
      $pids = Read-ArgusPids $Root
      $pids.worker = Start-ArgusWorkerProcess $Root
      Write-ArgusPids -Root $Root -ApiPid $pids.api -EocPid $pids.eoc -WorkerPid $pids.worker
      Start-Sleep -Seconds 2
    } else {
      # Recycle if ARQ backlog is building again (silent starvation risk).
      try {
        $arqKeys = @(docker exec argus-redis redis-cli --scan --pattern "arq:*" 2>$null)
        if ($arqKeys.Count -gt 80) {
          Write-Host ("ARQ backlog {0} keys — recycling worker..." -f $arqKeys.Count)
          $pids = Read-ArgusPids $Root
          $pids.worker = Start-ArgusWorkerProcess $Root
          Write-ArgusPids -Root $Root -ApiPid $pids.api -EocPid $pids.eoc -WorkerPid $pids.worker
          Start-Sleep -Seconds 2
        }
      } catch { }
    }
    $null = Start-ArgusKeepAwake $Root
    if (-not $KeepDashboard) {
      Start-Process (Get-ArgusDashboardUrl)
    } else {
      # Still recycle dashboard if public stamp changed vs before sync.
      $publicNow = Get-ArgusPublicBuildId $Root
      if ($publicBuildBefore -and $publicNow -and ($publicBuildBefore -ne $publicNow)) {
        $recycle = Join-Path $PSScriptRoot "recycle-eoc.ps1"
        try {
          Start-ArgusHiddenPowerShell -ScriptPath $recycle -WorkingDirectory $Root -ExtraArgs @("5")
          Write-Host "Scheduled dashboard recycle for new build stamp."
        } catch { }
      }
      Write-Host "REFRESH_HOME_SOFT"
    }
    Write-Host "=== Argus started ==="
    exit 0
  }

  # Code changed (or services down) — full recycle path below.
  Write-Host "Continuing with full service recycle..."

  # Re-register keepalive after sync so the task action picks up run-hidden.vbs
  # (older installs still pointed at a flashing powershell.exe).
  try {
    & "$PSScriptRoot\install-keepalive-task.ps1"
  } catch {
    Write-Host "WARN: keepalive task refresh failed: $($_.Exception.Message)"
  }

  $buildId = Write-ArgusPublicBuildStamp $Root
  $sha = "local"
  try { $sha = (git rev-parse --short HEAD).Trim() } catch { }

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

  if (-not (Ensure-ArgusEnvFile $Root)) {
    throw "Missing .env. Copy .env.paper.example to .env, then Start again."
  }
  if (-not (Ensure-ArgusApiVenv $Root)) {
    throw "API Python environment failed. Install Python + uv, then Start again (or run repair-argus-api.ps1)."
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
    $apiPid = Start-ArgusApiProcess $Root
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
      # Hidden — do not leave a minimized PowerShell tile on the taskbar.
      $eocProc = Start-Process -FilePath "powershell.exe" -PassThru -WindowStyle Hidden -ArgumentList @(
        "-NoProfile", "-NoLogo", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-WindowStyle", "Hidden", "-Command",
        "Set-Location '$Root'; $envBlock; pnpm eoc:dev *> '$eocLog'"
      )
      $eocPid = $eocProc.Id
    }
  } else {
    Write-Host "EOC already responding"
  }

  Write-ArgusPids -Root $Root -ApiPid $apiPid -EocPid $eocPid -WorkerPid $workerPid

  $okApi = Wait-HttpOk (Get-ArgusApiReadyUrl) 120 "API /ready"
  if (-not $okApi) {
    Write-Host "API /ready failed — attempting one repair cycle..."
    if (Repair-ArgusRuntime -Root $Root -IncludeWorker) {
      $okApi = $true
      $pids = Read-ArgusPids $Root
      $apiPid = $pids.api
      $workerPid = $pids.worker
    } else {
      Write-Host "FAIL API repair. Log tail:"
      Write-Host (Get-ArgusApiLogTail $Root 60)
    }
  }
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
      throw "Argus API did not become healthy. Open Docker Desktop, then run: irm `"https://raw.githubusercontent.com/brandoncorley01/Argus/main/scripts/control-center/repair-argus-api.ps1`" | iex"
    }
  } elseif (-not ($okApi -and $okEoc)) {
    throw "Argus did not become healthy. Open Docker Desktop, then run repair-argus-api.ps1 via irm | iex. See runtime\control-center\api.err.log"
  }

  $null = Start-ArgusKeepAwake $Root

  if (-not $KeepDashboard) {
    $dash = Get-ArgusDashboardUrl
    Write-Host "Opening Home: $dash"
    Start-Process $dash
  } else {
    # Browser Start: leave :3000 alone during the in-flight action. If code
    # updated (or Home was advertising a stale public stamp), recycle so the
    # compile-time Build chip and /argus-build.txt both show the new id.
    $publicNow = Get-ArgusPublicBuildId $Root
    # forceSync is always on now — recycle only when code/stamp actually changed.
    $needsRecycle = $updated -or (
      $publicBuildBefore -and $publicNow -and ($publicBuildBefore -ne $publicNow)
    )
    if ($needsRecycle) {
      $recycle = Join-Path $PSScriptRoot "recycle-eoc.ps1"
      try {
        Start-ArgusHiddenPowerShell -ScriptPath $recycle -WorkingDirectory $Root -ExtraArgs @("8")
        Write-Host "Scheduled dashboard recycle so Home picks up the new build stamp."
      } catch {
        Write-Host "WARN: could not schedule dashboard recycle: $($_.Exception.Message)"
      }
    }
    Write-Host "Browser Start complete — dashboard left running for soft reload."
    Write-Host "REFRESH_HOME_SOFT"
  }
  Write-Host "=== Argus started ==="
} catch {
  Show-ArgusNotification -Title "Argus startup failed" -Message $_.Exception.Message -Level "critical"
  throw
}
