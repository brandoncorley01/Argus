# FORCE this PC onto current GitHub main (build stamp + dashboard).
# Run in PowerShell:
#   irm "https://raw.githubusercontent.com/brandoncorley01/Argus/main/scripts/control-center/update-argus-now.ps1?$(Get-Random)" | iex
#
# Writes a report to your Desktop: Argus-update-report.txt
$ErrorActionPreference = "Continue"
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

Log "=== Argus UPDATE NOW ==="
Log "Script revision: update-argus-now-v3"

function Get-BuildIdFromRoot([string]$Root) {
  $p = Join-Path $Root "apps\eoc\src\lib\build.ts"
  if (-not (Test-Path $p)) { return $null }
  $t = Get-Content -Raw $p
  if ($t -match 'ARGUS_UI_BUILD\s*=\s*"([^"]+)"') { return $Matches[1] }
  return $null
}

function Get-ShortcutArgusRoots {
  $roots = @()
  $desktop = [Environment]::GetFolderPath("Desktop")
  $lnk = Join-Path $desktop "Start Argus.lnk"
  if (-not (Test-Path $lnk)) { return $roots }
  try {
    $w = New-Object -ComObject WScript.Shell
    $sc = $w.CreateShortcut($lnk)
    Log ("Desktop shortcut Target: {0}" -f $sc.TargetPath)
    Log ("Desktop shortcut Args: {0}" -f $sc.Arguments)
    Log ("Desktop shortcut WorkDir: {0}" -f $sc.WorkingDirectory)
    if ($sc.WorkingDirectory -and (Test-Path (Join-Path $sc.WorkingDirectory ".git"))) {
      $roots += $sc.WorkingDirectory
    }
    if ($sc.Arguments -match '-File\s+"([^"]+start-argus\.ps1)"') {
      $scriptPath = $Matches[1]
      $cand = Resolve-Path (Join-Path (Split-Path $scriptPath -Parent) "..\..") -ErrorAction SilentlyContinue
      if ($cand -and (Test-Path (Join-Path $cand.Path ".git"))) {
        $roots += $cand.Path
      }
    }
  } catch {
    Log ("WARN: could not read Start Argus shortcut: {0}" -f $_.Exception.Message)
  }
  return $roots
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

$found = @(Find-AllArgusRoots)
if ($found.Count -eq 0) {
  Log "ERROR: No Argus folder found (.git + apps\eoc)."
  Save-Report
  throw "Could not find Argus folder. cd into Argus and run again."
}

# Prefer shortcut WorkingDirectory, else the newest git sha / first found.
$Root = $found[0].Root
Log ("Using Argus folder: $Root")
Set-Location $Root

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

$code = Invoke-GitAt $Root @("remote", "-v")
$code = Invoke-GitAt $Root @("fetch", "origin")
if ($code -ne 0) {
  Log "ERROR: git fetch failed — check internet / GitHub access / credentials."
  Save-Report
  throw "git fetch failed"
}

Log "Hard reset to origin/main..."
$null = Invoke-GitAt $Root @("checkout", "-f", "-B", "main", "origin/main")
$code = Invoke-GitAt $Root @("reset", "--hard", "origin/main")
if ($code -ne 0) {
  Log "ERROR: git reset failed"
  Save-Report
  throw "git reset --hard origin/main failed"
}
$null = Invoke-GitAt $Root @("clean", "-fd", "--exclude=.env", "--exclude=runtime", "--exclude=backups")

$sha = (& git -C $Root rev-parse --short HEAD).Trim()
$branch = (& git -C $Root rev-parse --abbrev-ref HEAD).Trim()
$buildId = Get-BuildIdFromRoot $Root
Log ("OK  Now on {0} @ {1}" -f $branch, $sha)
Log ("OK  build.ts stamp: {0}" -f $(if ($buildId) { $buildId } else { "MISSING" }))
if ($branch -ne "main") {
  Save-Report
  throw "Expected branch main, got $branch"
}
if (-not $buildId) {
  Save-Report
  throw "build.ts missing ARGUS_UI_BUILD after reset"
}

# Mirror stamp into public file (served without Next rebuild).
$publicBuild = Join-Path $Root "apps\eoc\public\argus-build.txt"
$publicDir = Split-Path $publicBuild -Parent
if (-not (Test-Path $publicDir)) { New-Item -ItemType Directory -Force -Path $publicDir | Out-Null }
Set-Content -Path $publicBuild -Value "$buildId $sha" -Encoding ascii
Log ("Wrote {0}" -f $publicBuild)

$nextCache = Join-Path $Root "apps\eoc\.next"
if (Test-Path $nextCache) {
  Log "Clearing Next.js cache..."
  Remove-Item -LiteralPath $nextCache -Recurse -Force -ErrorAction SilentlyContinue
}

$env:ARGUS_FORCE_SYNC = "1"
$env:ARGUS_START_SELF_UPDATED = $null
$env:ARGUS_SKIP_START_SELF_UPDATE = $null
$env:ARGUS_KEEP_DASHBOARD = $null

$starter = Join-Path $Root "scripts\control-center\start-argus.ps1"
if (-not (Test-Path $starter)) {
  Save-Report
  throw "Start script missing: $starter"
}

Log "Starting Argus from updated tree..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $starter
$startExit = $LASTEXITCODE
Log ("Start exit code: {0}" -f $startExit)

# Source helpers from the refreshed tree for API verification/repair.
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
    Log "Next: open Docker Desktop, then run repair-argus-api.ps1 via irm | iex"
  }
} else {
  Log "OK  API /ready"
}

# Verify what the browser will see.
Start-Sleep -Seconds 5
try {
  $resp = Invoke-WebRequest -Uri ("http://127.0.0.1:3000/argus-build.txt?{0}" -f (Get-Random)) -UseBasicParsing -TimeoutSec 10
  Log ("HTTP /argus-build.txt => {0}" -f $resp.Content.Trim())
} catch {
  Log ("WARN: could not fetch http://127.0.0.1:3000/argus-build.txt: {0}" -f $_.Exception.Message)
}

Log ""
Log "=== DONE ==="
Log ("Expected Home build after Ctrl+F5: {0}" -f $buildId)
Log ("API ready: {0}" -f $apiOk)
Log "Open: http://127.0.0.1:3000/today"
Log "If API failed: irm repair-argus-api.ps1 | iex (see Desktop report)."
Save-Report

if (-not $apiOk) { exit 1 }
if ($startExit -ne 0) { exit $startExit }
