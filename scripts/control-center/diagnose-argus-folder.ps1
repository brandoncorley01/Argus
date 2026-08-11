# Read-only: which Argus folder this PC is using vs GitHub TARGET.
# Paste in PowerShell:
#   iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/diagnose-argus-folder.ps1?ref=main')
#
# Writes Desktop: Argus-folder-report.txt
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$Report = New-Object System.Collections.Generic.List[string]
function Log([string]$m) {
  Write-Host $m
  $Report.Add($m) | Out-Null
}

function Save-Report {
  $desktop = [Environment]::GetFolderPath("Desktop")
  if (-not $desktop) { $desktop = $env:USERPROFILE }
  $path = Join-Path $desktop "Argus-folder-report.txt"
  ($Report -join "`r`n") | Set-Content -Path $path -Encoding utf8
  Write-Host ""
  Write-Host "REPORT SAVED: $path"
}

function Get-BuildIdFromText([string]$Text) {
  if ($Text -match 'ARGUS_UI_BUILD\s*=\s*"([^"]+)"') { return $Matches[1] }
  return $null
}

function Get-BuildIdFromRoot([string]$Root) {
  $p = Join-Path $Root "apps\eoc\src\lib\build.ts"
  if (-not (Test-Path $p)) { return $null }
  return Get-BuildIdFromText (Get-Content -Raw $p)
}

function Get-PublicBuildFromRoot([string]$Root) {
  $p = Join-Path $Root "apps\eoc\public\argus-build.txt"
  if (-not (Test-Path $p)) { return $null }
  $raw = (Get-Content -Raw $p).Trim()
  if (-not $raw) { return $null }
  return ($raw -split '\s+')[0]
}

function Get-GitHubTarget {
  $api = "https://api.github.com/repos/brandoncorley01/Argus/contents/apps/eoc/src/lib/build.ts?ref=main"
  try {
    $resp = Invoke-WebRequest -Uri $api -Headers @{
      Accept = "application/vnd.github.raw"
      "User-Agent" = "ArgusFolderDiagnose"
    } -UseBasicParsing -TimeoutSec 30
    return Get-BuildIdFromText ([string]$resp.Content)
  } catch {
    return $null
  }
}

Log "=== Argus FOLDER DIAGNOSE ==="
Log ("Time: {0:u}" -f (Get-Date).ToUniversalTime())
Log ("User: {0}" -f $env:USERNAME)
Log ("Profile: {0}" -f $env:USERPROFILE)

$target = Get-GitHubTarget
Log ("GitHub TARGET build (API): {0}" -f $(if ($target) { $target } else { "UNAVAILABLE" }))

Log ""
Log "--- Desktop shortcuts ---"
$desktop = [Environment]::GetFolderPath("Desktop")
Log ("Desktop folder: {0}" -f $desktop)
$shortcutRoots = @()
foreach ($name in @("Start Argus.lnk", "Update Argus Now.lnk", "Open Argus.lnk")) {
  $lnk = Join-Path $desktop $name
  if (-not (Test-Path $lnk)) {
    Log ("MISSING: {0}" -f $name)
    continue
  }
  try {
    $w = New-Object -ComObject WScript.Shell
    $sc = $w.CreateShortcut($lnk)
    Log ("{0}" -f $name)
    Log ("  Target: {0}" -f $sc.TargetPath)
    Log ("  Args:   {0}" -f $sc.Arguments)
    Log ("  WorkDir:{0}" -f $sc.WorkingDirectory)
    if ($sc.WorkingDirectory) { $shortcutRoots += $sc.WorkingDirectory }
    if ($sc.Arguments -match '-File\s+"([^"]+)"') {
      $scriptPath = $Matches[1]
      Log ("  Script: {0}" -f $scriptPath)
      $fromScript = Resolve-Path (Join-Path (Split-Path $scriptPath -Parent) "..\..") -ErrorAction SilentlyContinue
      if ($fromScript) {
        Log ("  Repo from script: {0}" -f $fromScript.Path)
        $shortcutRoots += $fromScript.Path
      }
    }
  } catch {
    Log ("ERROR reading {0}: {1}" -f $name, $_.Exception.Message)
  }
}

Log ""
Log "--- Process on :3000 (dashboard) ---"
$servingRoot = $null
try {
  $conns = @(Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)
  if ($conns.Count -eq 0) {
    Log "Nothing listening on 127.0.0.1:3000"
  } else {
    foreach ($c in $conns) {
      $procId = $c.OwningProcess
      $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
      Log ("PID {0} {1}" -f $procId, $(if ($proc) { $proc.Name } else { "?" }))
      if ($proc -and $proc.CommandLine) {
        Log ("  Cmd: {0}" -f $proc.CommandLine)
        if ($proc.CommandLine -match '([A-Za-z]:\\[^"]*?Argus[^"\\]*)' ) {
          $guess = $Matches[1]
          Log ("  Path guess from cmdline: {0}" -f $guess)
        }
        # Prefer Set-Location / pnpm from repo root patterns
        if ($proc.CommandLine -match "Set-Location\s+'([^']+)'") {
          $servingRoot = $Matches[1]
          Log ("  Set-Location root: {0}" -f $servingRoot)
        } elseif ($proc.CommandLine -match '-File\s+"([^"]+control-center\\[^"]+\.ps1)"') {
          $servingRoot = (Resolve-Path (Join-Path (Split-Path $Matches[1] -Parent) "..\..") -ErrorAction SilentlyContinue).Path
          Log ("  Repo from -File: {0}" -f $servingRoot)
        }
      }
    }
  }
} catch {
  Log ("WARN: port inspect failed: {0}" -f $_.Exception.Message)
}

Log ""
Log "--- HTTP stamp browser sees ---"
try {
  $resp = Invoke-WebRequest -Uri ("http://127.0.0.1:3000/argus-build.txt?{0}" -f (Get-Random)) -UseBasicParsing -TimeoutSec 8
  Log ("http://127.0.0.1:3000/argus-build.txt => {0}" -f $resp.Content.Trim())
} catch {
  $msg = $_.Exception.Message
  Log ("HTTP stamp unavailable: {0}" -f $msg)
  if ($msg -match '404' -or $msg -match 'Not Found') {
    Log "404 on /argus-build.txt = this dashboard tree is OLD (missing public stamp)."
    Log "Cloud agent did save to GitHub — THIS folder never got the pull. Run updater next."
  }
  try {
    $resp2 = Invoke-WebRequest -Uri ("http://127.0.0.1:3000/api/argus-build?{0}" -f (Get-Random)) -UseBasicParsing -TimeoutSec 8
    Log ("http://127.0.0.1:3000/api/argus-build => {0}" -f $resp2.Content.Trim())
  } catch {
    Log ("API stamp also unavailable: {0}" -f $_.Exception.Message)
  }
}

Log ""
Log "--- All Argus folders found ---"
$candidates = New-Object System.Collections.Generic.List[string]
foreach ($r in $shortcutRoots) { if ($r) { $candidates.Add($r) | Out-Null } }
if ($servingRoot) { $candidates.Add($servingRoot) | Out-Null }
foreach ($c in @(
    (Join-Path $env:USERPROFILE "OneDrive\Desktop\Argus"),
    (Join-Path $env:USERPROFILE "Desktop\Argus"),
    (Join-Path $env:USERPROFILE "OneDrive\Documents\Argus"),
    (Join-Path $env:USERPROFILE "Documents\Argus"),
    (Join-Path $env:USERPROFILE "Argus"),
    (Get-Location).Path
  )) { if ($c) { $candidates.Add($c) | Out-Null } }
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

$rows = @()
foreach ($c in ($candidates | Select-Object -Unique)) {
  if (-not $c) { continue }
  if (-not ((Test-Path (Join-Path $c ".git")) -and (Test-Path (Join-Path $c "apps\eoc")))) { continue }
  $bid = Get-BuildIdFromRoot $c
  $pub = Get-PublicBuildFromRoot $c
  $sha = ""
  $origin = ""
  try { $sha = (& git -C $c rev-parse --short HEAD 2>$null).Trim() } catch {}
  try { $origin = (& git -C $c remote get-url origin 2>$null).Trim() } catch {}
  $isShortcut = $shortcutRoots -contains $c
  $isServing = $servingRoot -and ($servingRoot -eq $c)
  $matchTarget = ($target -and $bid -eq $target)
  Log ("FOLDER: {0}" -f $c)
  Log ("  build.ts:     {0}" -f $(if ($bid) { $bid } else { "?" }))
  Log ("  public stamp: {0}" -f $(if ($pub) { $pub } else { "?" }))
  Log ("  git sha:      {0}" -f $(if ($sha) { $sha } else { "?" }))
  Log ("  origin:       {0}" -f $(if ($origin) { $origin } else { "?" }))
  Log ("  Start shortcut points here: {0}" -f $isShortcut)
  Log ("  Likely serving :3000:       {0}" -f $isServing)
  Log ("  Matches GitHub TARGET:      {0}" -f $matchTarget)
  $rows += [pscustomobject]@{
    Root = $c
    Build = $bid
    Shortcut = $isShortcut
    Serving = $isServing
    Match = $matchTarget
  }
}

Log ""
Log "--- Verdict ---"
$primary = $rows | Where-Object { $_.Serving } | Select-Object -First 1
if (-not $primary) { $primary = $rows | Where-Object { $_.Shortcut } | Select-Object -First 1 }
if (-not $primary) { $primary = $rows | Select-Object -First 1 }
if (-not $primary) {
  Log "NO Argus git folder found on this PC."
  Log "Cloud agent only saves to GitHub. This PC has nothing to pull into."
} else {
  Log ("ACTIVE folder (use this): {0}" -f $primary.Root)
  Log ("ACTIVE build: {0}" -f $(if ($primary.Build) { $primary.Build } else { "?" }))
  if ($target -and $primary.Build -ne $target) {
    Log "STALE: active folder is behind GitHub. Run updater (GitHub API), not browser refresh."
    Log '  iex (irm -Headers @{Accept=''application/vnd.github.raw''} ''https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/update-argus-now.ps1?ref=main'')'
  } elseif ($target -and $primary.Build -eq $target) {
    Log "ACTIVE folder matches GitHub TARGET. If Home still shows old Build, hard-refresh Ctrl+F5 or recycle dashboard."
  }
  $others = @($rows | Where-Object { $_.Root -ne $primary.Root })
  if ($others.Count -gt 0) {
    Log "WARNING: multiple Argus folders exist. Updating the wrong one leaves Home stuck."
    foreach ($o in $others) {
      Log ("  extra: {0} build={1}" -f $o.Root, $(if ($o.Build) { $o.Build } else { "?" }))
    }
  }
}

Log ""
Log "Cloud agent saves ONLY to github.com/brandoncorley01/Argus (main)."
Log "This PC must pull that into the ACTIVE folder above."
Save-Report
