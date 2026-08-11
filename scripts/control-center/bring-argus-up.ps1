# BRING ARGUS BACK UP on this PC (find or clone folder, then Start).
# Paste in PowerShell:
#   iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/bring-argus-up.ps1?ref=main')
#
# Writes Desktop/OneDrive/profile: Argus-bringup-report.txt
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Report = New-Object System.Collections.Generic.List[string]
function Log([string]$m) {
  Write-Host $m
  $Report.Add(("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m)) | Out-Null
}

function Save-Report {
  $text = $Report -join "`r`n"
  $dirs = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path $env:USERPROFILE "Desktop"),
    (Join-Path $env:USERPROFILE "OneDrive\Desktop"),
    $env:USERPROFILE
  ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique
  foreach ($dir in $dirs) {
    $path = Join-Path $dir "Argus-bringup-report.txt"
    try {
      Set-Content -Path $path -Value $text -Encoding utf8
      Write-Host "REPORT SAVED: $path"
    } catch {}
  }
}

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
    try { return [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64)) } catch { return $s }
  }
  return $s
}

function Find-ArgusRoot {
  $candidates = @(
    (Join-Path $env:USERPROFILE "OneDrive\Desktop\Argus"),
    (Join-Path $env:USERPROFILE "Desktop\Argus"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Argus"),
    (Join-Path $env:USERPROFILE "Documents\Argus"),
    (Join-Path $env:USERPROFILE "OneDrive\Documents\Argus"),
    (Join-Path $env:USERPROFILE "Argus"),
    "C:\Argus",
    "D:\Argus",
    (Get-Location).Path
  )
  foreach ($base in @(
      (Join-Path $env:USERPROFILE "Desktop"),
      (Join-Path $env:USERPROFILE "OneDrive\Desktop"),
      (Join-Path $env:USERPROFILE "Documents"),
      (Join-Path $env:USERPROFILE "Downloads")
    )) {
    if (Test-Path $base) {
      Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match 'argus' } |
        ForEach-Object { $candidates += $_.FullName }
    }
  }
  foreach ($c in ($candidates | Select-Object -Unique)) {
    if (-not $c) { continue }
    $starter = Join-Path $c "scripts\control-center\start-argus.ps1"
    if ((Test-Path (Join-Path $c ".git")) -and (Test-Path $starter)) {
      return $c
    }
  }
  return $null
}

function New-ArgusClone {
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is not installed. Install Git for Windows: https://git-scm.com/download/win — then re-run."
  }
  $desktop = [Environment]::GetFolderPath("Desktop")
  if (-not $desktop -or -not (Test-Path $desktop)) {
    $desktop = Join-Path $env:USERPROFILE "Desktop"
  }
  if (-not (Test-Path $desktop)) { $desktop = $env:USERPROFILE }
  $dest = Join-Path $desktop "Argus"
  if ((Test-Path $dest) -and -not (Test-Path (Join-Path $dest ".git"))) {
    $dest = Join-Path $desktop ("Argus-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
  }
  if ((Test-Path $dest) -and (Test-Path (Join-Path $dest ".git"))) {
    return $dest
  }
  Log ("Cloning Argus into {0} ..." -f $dest)
  & git clone --branch main --single-branch "https://github.com/brandoncorley01/Argus.git" $dest 2>&1 | ForEach-Object { Log ("  $_") }
  if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
  return $dest
}

try {
  Log "=== BRING ARGUS UP ==="
  Log "Script revision: bring-argus-up-v1"

  $Root = Find-ArgusRoot
  if (-not $Root) {
    Log "No local Argus git folder — cloning from GitHub."
    $Root = New-ArgusClone
  }
  Log ("Using folder: {0}" -f $Root)
  Set-Location $Root

  if (-not (Test-Path (Join-Path $Root ".env"))) {
    $example = Join-Path $Root ".env.paper.example"
    if (Test-Path $example) {
      Copy-Item $example (Join-Path $Root ".env") -Force
      Log "Created .env from .env.paper.example"
    }
  }

  $starter = Join-Path $Root "scripts\control-center\start-argus.ps1"
  if (-not (Test-Path $starter)) { throw "Start script missing at $starter" }

  # Refresh Start script from GitHub API so PC is not stuck on stale Start.
  try {
    $api = "https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/start-argus.ps1?ref=main"
    $resp = Invoke-WebRequest -Uri $api -Headers @{
      Accept = "application/vnd.github.raw"
      "User-Agent" = "ArgusBringUp"
    } -UseBasicParsing -TimeoutSec 45
    $text = ConvertTo-ArgusUtf8Text $resp.Content
    if ($text -and $text.Length -gt 200) {
      Set-Content -Path $starter -Value $text -Encoding utf8
      Log "Refreshed start-argus.ps1 from GitHub"
    }
  } catch {
    Log ("WARN: could not refresh Start script: {0}" -f $_.Exception.Message)
  }

  $env:ARGUS_FORCE_SYNC = "1"
  Remove-Item Env:ARGUS_KEEP_DASHBOARD -ErrorAction SilentlyContinue
  Remove-Item Env:ARGUS_START_SELF_UPDATED -ErrorAction SilentlyContinue
  Remove-Item Env:ARGUS_SKIP_START_SELF_UPDATE -ErrorAction SilentlyContinue
  Remove-Item Env:ARGUS_ALLOW_STALE -ErrorAction SilentlyContinue

  Log "Starting Argus (Docker must be running)..."
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $starter
  $code = $LASTEXITCODE
  Log ("Start exit code: {0}" -f $code)

  Start-Sleep -Seconds 5
  $stamp = "?"
  foreach ($url in @(
      "http://127.0.0.1:3000/argus-build.txt",
      "http://127.0.0.1:3000/api/argus-build",
      "http://127.0.0.1:3000/today"
    )) {
    try {
      $r = Invoke-WebRequest -Uri ("{0}?{1}" -f $url, (Get-Random)) -UseBasicParsing -TimeoutSec 8
      Log ("OK  {0} => {1}" -f $url, ($r.Content.ToString().Trim().Substring(0, [Math]::Min(80, $r.Content.ToString().Trim().Length))))
      if ($url -match 'argus-build') { $stamp = ($r.Content.ToString().Trim() -split '\s+')[0] }
    } catch {
      Log ("WAIT {0}: {1}" -f $url, $_.Exception.Message)
    }
  }

  try { Start-Process "http://127.0.0.1:3000/today" } catch {}
  Log ""
  Log "=== DONE ==="
  Log ("Folder: {0}" -f $Root)
  Log ("Build stamp: {0}" -f $stamp)
  Log "Open: http://127.0.0.1:3000/today"
  Log "If Start failed: open Docker Desktop, then re-run this script."
  Save-Report
  if ($code -ne 0) { exit $code }
  exit 0
} catch {
  Log ("ERROR: {0}" -f $_.Exception.Message)
  Save-Report
  throw
}
