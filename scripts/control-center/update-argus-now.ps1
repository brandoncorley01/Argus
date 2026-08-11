# FORCE this PC onto current GitHub main (build stamp + dashboard).
# Paste this ENTIRE line in PowerShell (uses GitHub API — NOT raw CDN cache):
#   iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/update-argus-now.ps1?ref=main')
#
# Writes Desktop: Argus-update-report.txt
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ReportLines = New-Object System.Collections.Generic.List[string]
function Log([string]$msg) {
  Write-Host $msg
  $ReportLines.Add(("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg)) | Out-Null
}

function Save-Report {
  $desktop = [Environment]::GetFolderPath("Desktop")
  if (-not $desktop) { $desktop = $env:USERPROFILE }
  $path = Join-Path $desktop "Argus-update-report.txt"
  try {
    $ReportLines -join "`r`n" | Set-Content -Path $path -Encoding utf8
    Write-Host ""
    Write-Host "REPORT SAVED: $path"
  } catch {
    Write-Host "WARN: could not write Desktop report: $($_.Exception.Message)"
  }
}

function Get-BuildIdFromText([string]$Text) {
  if (-not $Text) { return $null }
  if ($Text -match 'ARGUS_UI_BUILD\s*=\s*"([^"]+)"') { return $Matches[1] }
  return $null
}

function Get-BuildIdFromRoot([string]$Root) {
  $p = Join-Path $Root "apps\eoc\src\lib\build.ts"
  if (-not (Test-Path $p)) { return $null }
  return Get-BuildIdFromText (Get-Content -Raw $p)
}

function Get-GitHubFileText([string]$RepoPath) {
  # GitHub Contents API only — never fall back to raw CDN (lag re-poisoned PCs).
  $api = "https://api.github.com/repos/brandoncorley01/Argus/contents/{0}?ref=main" -f $RepoPath.TrimStart('/')
  $resp = Invoke-WebRequest -Uri $api -Headers @{
    Accept = "application/vnd.github.raw"
    "User-Agent" = "ArgusUpdateNow"
  } -UseBasicParsing -TimeoutSec 45
  if (-not $resp.Content) { throw "empty GitHub API body for $RepoPath" }
  return [string]$resp.Content
}

function Get-GitHubTargetBuild {
  $text = Get-GitHubFileText "apps/eoc/src/lib/build.ts"
  $id = Get-BuildIdFromText "$text"
  if (-not $id) { throw "Could not read ARGUS_UI_BUILD from GitHub build.ts" }
  return $id
}

function Get-ShortcutArgusRoots {
  $roots = New-Object System.Collections.Generic.List[string]
  $desktop = [Environment]::GetFolderPath("Desktop")
  foreach ($name in @("Start Argus.lnk", "Update Argus Now.lnk")) {
    $lnk = Join-Path $desktop $name
    if (-not (Test-Path $lnk)) { continue }
    try {
      $w = New-Object -ComObject WScript.Shell
      $sc = $w.CreateShortcut($lnk)
      Log ("Shortcut {0} WorkDir: {1}" -f $name, $sc.WorkingDirectory)
      if ($sc.WorkingDirectory -and (Test-Path (Join-Path $sc.WorkingDirectory ".git"))) {
        $roots.Add($sc.WorkingDirectory) | Out-Null
      }
      if ($sc.Arguments -match '-File\s+"([^"]+\.ps1)"') {
        $scriptPath = $Matches[1]
        $cand = Resolve-Path (Join-Path (Split-Path $scriptPath -Parent) "..\..") -ErrorAction SilentlyContinue
        if ($cand -and (Test-Path (Join-Path $cand.Path ".git"))) {
          $roots.Add($cand.Path) | Out-Null
        }
      }
    } catch {
      Log ("WARN: shortcut read failed: {0}" -f $_.Exception.Message)
    }
  }
  return @($roots)
}

function Find-AllArgusRoots {
  $candidates = New-Object System.Collections.Generic.List[string]
  foreach ($r in (Get-ShortcutArgusRoots)) { $candidates.Add($r) | Out-Null }
  foreach ($c in @(
      (Join-Path $env:USERPROFILE "OneDrive\Desktop\Argus"),
      (Join-Path $env:USERPROFILE "Desktop\Argus"),
      (Join-Path $env:USERPROFILE "OneDrive\Documents\Argus"),
      (Join-Path $env:USERPROFILE "Documents\Argus"),
      (Join-Path $env:USERPROFILE "source\Argus"),
      (Join-Path $env:USERPROFILE "src\Argus"),
      (Join-Path $env:USERPROFILE "Argus"),
      (Get-Location).Path
    )) {
    if ($c) { $candidates.Add($c) | Out-Null }
  }
  foreach ($base in @(
      (Join-Path $env:USERPROFILE "Desktop"),
      (Join-Path $env:USERPROFILE "OneDrive\Desktop"),
      (Join-Path $env:USERPROFILE "Documents"),
      (Join-Path $env:USERPROFILE "OneDrive\Documents"),
      "C:\",
      "D:\"
    )) {
    if (-not (Test-Path $base)) { continue }
    Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -match 'argus' } |
      ForEach-Object { $candidates.Add($_.FullName) | Out-Null }
  }
  $valid = @()
  foreach ($c in ($candidates | Select-Object -Unique)) {
    if (-not $c) { continue }
    if ((Test-Path (Join-Path $c ".git")) -and (Test-Path (Join-Path $c "apps\eoc"))) {
      $bid = Get-BuildIdFromRoot $c
      $sha = ""
      try { $sha = (& git -C $c rev-parse --short HEAD 2>$null).Trim() } catch {}
      Log ("Found Argus at: {0} | build={1} | sha={2}" -f $c, $(if ($bid) { $bid } else { "?" }), $(if ($sha) { $sha } else { "?" }))
      $valid += [pscustomobject]@{ Root = $c; Build = $bid; Sha = $sha }
    }
  }
  return $valid
}

function Stop-PortListeners([int[]]$Ports) {
  foreach ($port in $Ports) {
    try {
      Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object {
          Log ("  kill PID {0} on port {1}" -f $_.OwningProcess, $port)
          Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    } catch {}
  }
}

function Invoke-GitAt([string]$Root, [string[]]$GitArgs) {
  Log ("> git " + ($GitArgs -join " "))
  Push-Location $Root
  try {
    & git @GitArgs 2>&1 | ForEach-Object { Log ("  $_") }
    return $LASTEXITCODE
  } finally {
    Pop-Location
  }
}

function Sync-OneRoot([string]$Root, [string]$TargetBuild) {
  Log ("---- Syncing {0} ----" -f $Root)
  Set-Location $Root
  $origin = (& git -C $Root remote get-url origin 2>$null)
  Log ("origin: {0}" -f $(if ($origin) { $origin } else { "?" }))
  if ($origin -and ($origin -notmatch "brandoncorley01/Argus")) {
    throw "Wrong git origin at $Root : $origin (expected brandoncorley01/Argus)"
  }
  $code = Invoke-GitAt $Root @("fetch", "origin")
  if ($code -ne 0) { throw "git fetch failed for $Root" }
  $null = Invoke-GitAt $Root @("checkout", "-f", "-B", "main", "origin/main")
  $code = Invoke-GitAt $Root @("reset", "--hard", "origin/main")
  if ($code -ne 0) { throw "git reset failed for $Root" }
  $null = Invoke-GitAt $Root @("clean", "-fd", "--exclude=.env", "--exclude=.env.*", "--exclude=runtime", "--exclude=backups")
  $sha = (& git -C $Root rev-parse --short HEAD).Trim()
  $buildId = Get-BuildIdFromRoot $Root
  Log ("OK  {0} @ {1} build={2}" -f $Root, $sha, $buildId)
  if ($buildId -ne $TargetBuild) {
    throw "After reset, build is '$buildId' but GitHub target is '$TargetBuild' at $Root"
  }
  $publicBuild = Join-Path $Root "apps\eoc\public\argus-build.txt"
  $publicDir = Split-Path $publicBuild -Parent
  if (-not (Test-Path $publicDir)) { New-Item -ItemType Directory -Force -Path $publicDir | Out-Null }
  Set-Content -Path $publicBuild -Value "$buildId $sha" -Encoding ascii
  $nextCache = Join-Path $Root "apps\eoc\.next"
  if (Test-Path $nextCache) {
    Log "Clearing Next.js cache..."
    Remove-Item -LiteralPath $nextCache -Recurse -Force -ErrorAction SilentlyContinue
  }
  return [pscustomobject]@{ Root = $Root; Build = $buildId; Sha = $sha }
}

function Get-ServingArgusRoot {
  # Which checkout is actually running the dashboard on :3000?
  try {
    $conns = @(Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)
    foreach ($c in $conns) {
      $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" -ErrorAction SilentlyContinue
      if (-not $proc -or -not $proc.CommandLine) { continue }
      Log ("Port 3000 PID {0}: {1}" -f $c.OwningProcess, $proc.CommandLine)
      if ($proc.CommandLine -match "Set-Location\s+'([^']+)'") {
        $cand = $Matches[1]
        if ((Test-Path (Join-Path $cand ".git")) -and (Test-Path (Join-Path $cand "apps\eoc"))) {
          return $cand
        }
      }
      if ($proc.CommandLine -match '-File\s+"([^"]+control-center\\[^"]+\.ps1)"') {
        $cand = (Resolve-Path (Join-Path (Split-Path $Matches[1] -Parent) "..\..") -ErrorAction SilentlyContinue).Path
        if ($cand -and (Test-Path (Join-Path $cand ".git"))) { return $cand }
      }
      if ($proc.CommandLine -match '([A-Za-z]:\\(?:Users|[^"\s]+)\\[^"]*?\\Argus)(?:\\|"|\s)') {
        $cand = $Matches[1]
        if ((Test-Path (Join-Path $cand ".git")) -and (Test-Path (Join-Path $cand "apps\eoc"))) {
          return $cand
        }
      }
    }
  } catch {
    Log ("WARN: could not inspect :3000 — {0}" -f $_.Exception.Message)
  }
  return $null
}

try {
  Log "=== Argus UPDATE NOW ==="
  Log "Script revision: update-argus-now-v9"
  Log "Uses GitHub API only (no raw CDN fallback)."
  Log "Prefers the folder currently serving http://127.0.0.1:3000."

  $TargetBuild = Get-GitHubTargetBuild
  Log ("GitHub TARGET build: {0}" -f $TargetBuild)

  # Capture serving folder BEFORE killing :3000.
  $servingRoot = Get-ServingArgusRoot
  if ($servingRoot) {
    Log ("ACTIVE dashboard folder (:3000): {0}" -f $servingRoot)
  } else {
    Log "No live :3000 folder detected — will use Start shortcut / first found."
  }

  $found = @(Find-AllArgusRoots)
  if ($found.Count -eq 0) {
    throw "No Argus folder found (.git + apps\eoc). Open PowerShell in your Argus folder and run again."
  }

  # Put the folder that is actually serving Home first.
  if ($servingRoot) {
    $found = @(
      ($found | Where-Object { $_.Root -eq $servingRoot }) +
      ($found | Where-Object { $_.Root -ne $servingRoot })
    )
  }

  Log "Stopping API/dashboard locks..."
  Stop-PortListeners @(3000, 8000)
  Get-Process -Name node -ErrorAction SilentlyContinue | ForEach-Object {
    try {
      $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
      if ($cmd -and ($cmd -like "*eoc*" -or $cmd -like "*next*" -or $cmd -like "*Argus*")) {
        Log ("  kill node PID {0}" -f $_.Id)
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
      }
    } catch {}
  }
  Start-Sleep -Seconds 2

  # Sync every found checkout (serving / shortcut first).
  $synced = @()
  foreach ($item in $found) {
    if ($item.Build -eq $TargetBuild) {
      Log ("Already on target: {0}" -f $item.Root)
      $synced += (Sync-OneRoot -Root $item.Root -TargetBuild $TargetBuild)
    } else {
      Log ("Behind target ({0} -> {1}): {2}" -f $(if ($item.Build) { $item.Build } else { "?" }), $TargetBuild, $item.Root)
      $synced += (Sync-OneRoot -Root $item.Root -TargetBuild $TargetBuild)
    }
  }

  $Root = $synced[0].Root
  $buildId = $synced[0].Build
  $sha = $synced[0].Sha
  Set-Location $Root
  Log ("Primary Start folder (will run Start here): {0}" -f $Root)
  Log ("Cloud agent does NOT write to this PC — only GitHub. This folder must pull main.")

  $env:ARGUS_FORCE_SYNC = "1"
  Remove-Item Env:ARGUS_START_SELF_UPDATED -ErrorAction SilentlyContinue
  Remove-Item Env:ARGUS_SKIP_START_SELF_UPDATE -ErrorAction SilentlyContinue
  Remove-Item Env:ARGUS_KEEP_DASHBOARD -ErrorAction SilentlyContinue
  Remove-Item Env:ARGUS_ALLOW_STALE -ErrorAction SilentlyContinue

  $starter = Join-Path $Root "scripts\control-center\start-argus.ps1"
  if (-not (Test-Path $starter)) { throw "Start script missing: $starter" }

  Log "Starting Argus from updated tree..."
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $starter
  $startExit = $LASTEXITCODE
  Log ("Start exit code: {0}" -f $startExit)

  . (Join-Path $Root "scripts\control-center\_common.ps1")
  $apiOk = Test-HttpOk (Get-ArgusApiReadyUrl) 5
  if (-not $apiOk) {
    Log "API /ready failed after Start — running repair..."
    Log (Get-ArgusApiLogTail $Root 40)
    if (Repair-ArgusRuntime -Root $Root -IncludeWorker) {
      $apiOk = $true
      $startExit = 0
      Log "OK  API repaired"
    } else {
      Log "FAIL API still down after repair"
      Log (Get-ArgusApiLogTail $Root 60)
    }
  } else {
    Log "OK  API /ready"
  }

  Start-Sleep -Seconds 6
  $httpBuild = $null
  try {
    $resp = Invoke-WebRequest -Uri ("http://127.0.0.1:3000/argus-build.txt?{0}" -f (Get-Random)) -UseBasicParsing -TimeoutSec 15
    $httpBuild = ($resp.Content.Trim() -split '\s+')[0]
    Log ("HTTP /argus-build.txt => {0}" -f $resp.Content.Trim())
  } catch {
    Log ("WARN: /argus-build.txt failed: {0}" -f $_.Exception.Message)
    try {
      $resp2 = Invoke-WebRequest -Uri ("http://127.0.0.1:3000/api/argus-build?{0}" -f (Get-Random)) -UseBasicParsing -TimeoutSec 15
      $httpBuild = ($resp2.Content.Trim() -split '\s+')[0]
      Log ("HTTP /api/argus-build => {0}" -f $resp2.Content.Trim())
    } catch {
      Log ("WARN: could not fetch build stamp from :3000: {0}" -f $_.Exception.Message)
    }
  }

  Log ""
  Log "=== DONE ==="
  Log ("TARGET build: {0}" -f $TargetBuild)
  Log ("LOCAL build:  {0}" -f $buildId)
  Log ("HTTP build:   {0}" -f $(if ($httpBuild) { $httpBuild } else { "?" }))
  Log ("API ready: {0}" -f $apiOk)
  Log "Open: http://127.0.0.1:3000/today"
  Log "Hard-refresh Home (Ctrl+F5)."
  if ($httpBuild -and ($httpBuild -ne $TargetBuild)) {
    Log "ERROR: browser still serving old build after update."
    Save-Report
    throw "HTTP build '$httpBuild' != target '$TargetBuild'. Wrong Argus folder may still be running on :3000."
  }
  if ($buildId -ne $TargetBuild) {
    Save-Report
    throw "Local build '$buildId' != target '$TargetBuild'."
  }
  Save-Report
  if (-not $apiOk) { exit 1 }
  if ($startExit -ne 0) { exit $startExit }
  exit 0
} catch {
  Log ("ERROR: {0}" -f $_.Exception.Message)
  Save-Report
  throw
}
