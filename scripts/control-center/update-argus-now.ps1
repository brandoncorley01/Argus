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
  # Canonical report location: %USERPROFILE%\Desktop (not OneDrive).
  $text = $ReportLines -join "`r`n"
  $dirs = @(
    (Join-Path $env:USERPROFILE "Desktop"),
    $env:USERPROFILE
  ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique
  # Also write to special-folder Desktop only if it is NOT OneDrive (duplicate).
  $special = [Environment]::GetFolderPath("Desktop")
  if ($special -and (Test-Path $special) -and ($special -notmatch '(?i)OneDrive')) {
    $dirs = @($dirs + $special) | Select-Object -Unique
  }
  $saved = $false
  foreach ($dir in $dirs) {
    $path = Join-Path $dir "Argus-update-report.txt"
    try {
      Set-Content -Path $path -Value $text -Encoding utf8
      Write-Host "REPORT SAVED: $path"
      $saved = $true
    } catch {
      Write-Host ("WARN: could not write {0}: {1}" -f $path, $_.Exception.Message)
    }
  }
  if (-not $saved) {
    Write-Host "WARN: could not write Argus-update-report.txt anywhere"
  }
}

function Get-ArgusLocalDesktop {
  # Canonical PC Desktop — NEVER [Environment]::GetFolderPath("Desktop"),
  # which returns OneDrive\Desktop when Files On-Demand is enabled.
  $d = Join-Path $env:USERPROFILE "Desktop"
  if (-not (Test-Path $d)) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
  }
  return $d
}

function Get-ArgusLocalRoot {
  return (Join-Path (Get-ArgusLocalDesktop) "Argus")
}

function Test-IsOneDrivePath([string]$Path) {
  if (-not $Path) { return $false }
  return [bool]($Path -match '(?i)[\\/]OneDrive([\\/]|$)')
}

function Get-BuildIdFromText([string]$Text) {
  if (-not $Text) { return $null }
  if ($Text -match 'ARGUS_UI_BUILD\s*=\s*"([^"]+)"') { return $Matches[1] }
  if ($Text -match 'ARGUS_UI_BUILD\s*=\s*''([^'']+)''') { return $Matches[1] }
  # Plain stamp file: "live-monitor-v2.50" or "live-monitor-v2.50 abc1234"
  $token = (($Text.Trim() -split '\s+')[0]).Trim()
  if ($token -match '^live-monitor-v[0-9]') { return $token }
  return $null
}

function ConvertTo-ArgusUtf8Text($Content) {
  # Windows PowerShell 5.1 often returns [byte[]] for raw GitHub bodies.
  # [string]$bytes => "System.Byte[]" which broke TARGET parse on Founder PC.
  if ($null -eq $Content) { return $null }
  if ($Content -is [byte[]]) {
    return [System.Text.Encoding]::UTF8.GetString($Content)
  }
  if ($Content -is [System.Array] -and $Content.Length -gt 0 -and ($Content[0] -is [byte])) {
    return [System.Text.Encoding]::UTF8.GetString([byte[]]$Content)
  }
  $s = [string]$Content
  # If Accept: raw was ignored, Contents API returns JSON + base64 "content".
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

function Get-BuildIdFromRoot([string]$Root) {
  $p = Join-Path $Root "apps\eoc\src\lib\build.ts"
  if (-not (Test-Path $p)) { return $null }
  return Get-BuildIdFromText (Get-Content -Raw $p)
}

function Get-GitHubFileText([string]$RepoPath) {
  # GitHub Contents API — decode byte[] / JSON+base64 (WinPS 5.1 quirks).
  $api = "https://api.github.com/repos/brandoncorley01/Argus/contents/{0}?ref=main" -f $RepoPath.TrimStart('/')
  $resp = Invoke-WebRequest -Uri $api -Headers @{
    Accept = "application/vnd.github.raw"
    "User-Agent" = "ArgusUpdateNow"
  } -UseBasicParsing -TimeoutSec 45
  if (-not $resp.Content) { throw "empty GitHub API body for $RepoPath" }
  $text = ConvertTo-ArgusUtf8Text $resp.Content
  if (-not $text) { throw "could not decode GitHub body for $RepoPath" }
  return $text
}

function Get-GitHubTargetBuild {
  # Prefer plain public stamp (no regex on TypeScript).
  try {
    $stamp = Get-GitHubFileText "apps/eoc/public/argus-build.txt"
    $id = Get-BuildIdFromText "$stamp"
    if ($id) { return $id }
    Log ("WARN: public stamp unparseable, head={0}" -f ($(if ($stamp.Length -gt 80) { $stamp.Substring(0,80) } else { $stamp })))
  } catch {
    Log ("WARN: public stamp fetch failed: {0}" -f $_.Exception.Message)
  }
  $text = Get-GitHubFileText "apps/eoc/src/lib/build.ts"
  $id = Get-BuildIdFromText "$text"
  if (-not $id) {
    $head = if ($text -and $text.Length -gt 160) { $text.Substring(0, 160) } else { $text }
    throw "Could not read ARGUS_UI_BUILD from GitHub build.ts. Got: $head"
  }
  return $id
}

function Get-ShortcutArgusRoots {
  $roots = New-Object System.Collections.Generic.List[string]
  # Prefer real Desktop shortcuts; also check OneDrive Desktop for legacy links.
  foreach ($desktop in @((Get-ArgusLocalDesktop), (Join-Path $env:USERPROFILE "OneDrive\Desktop"), [Environment]::GetFolderPath("Desktop"))) {
    if (-not $desktop -or -not (Test-Path $desktop)) { continue }
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
  }
  return @($roots)
}

function Find-AllArgusRoots {
  $candidates = New-Object System.Collections.Generic.List[string]
  # Canonical first.
  $candidates.Add((Get-ArgusLocalRoot)) | Out-Null
  foreach ($r in (Get-ShortcutArgusRoots)) { $candidates.Add($r) | Out-Null }
  foreach ($c in @(
      (Join-Path $env:USERPROFILE "Desktop\Argus"),
      (Join-Path $env:USERPROFILE "Documents\Argus"),
      (Join-Path $env:USERPROFILE "Downloads\Argus"),
      (Join-Path $env:USERPROFILE "source\Argus"),
      (Join-Path $env:USERPROFILE "src\Argus"),
      (Join-Path $env:USERPROFILE "Argus"),
      "C:\Argus",
      "D:\Argus",
      # Legacy OneDrive trees — discovered so we can sync/migrate .env, never Start from here.
      (Join-Path $env:USERPROFILE "OneDrive\Desktop\Argus"),
      (Join-Path $env:USERPROFILE "OneDrive\Documents\Argus"),
      (Get-Location).Path
    )) {
    if ($c) { $candidates.Add($c) | Out-Null }
  }
  foreach ($base in @(
      (Join-Path $env:USERPROFILE "Desktop"),
      (Join-Path $env:USERPROFILE "Documents"),
      (Join-Path $env:USERPROFILE "Downloads"),
      (Join-Path $env:USERPROFILE "OneDrive\Desktop"),
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
      $tag = if (Test-IsOneDrivePath $c) { " [OneDrive-legacy]" } else { "" }
      Log ("Found Argus at: {0} | build={1} | sha={2}{3}" -f $c, $(if ($bid) { $bid } else { "?" }), $(if ($sha) { $sha } else { "?" }), $tag)
      $valid += [pscustomobject]@{ Root = $c; Build = $bid; Sha = $sha; OneDrive = (Test-IsOneDrivePath $c) }
    }
  }
  return $valid
}

function Find-LooseEocRoots {
  # Zip / copy trees that run Home but are not git checkouts ("cannot find file" / no .git).
  $hits = @()
  foreach ($base in @(
      (Join-Path $env:USERPROFILE "Desktop"),
      (Join-Path $env:USERPROFILE "OneDrive\Desktop"),
      (Join-Path $env:USERPROFILE "Documents"),
      (Join-Path $env:USERPROFILE "OneDrive\Documents"),
      (Join-Path $env:USERPROFILE "Downloads"),
      (Join-Path $env:USERPROFILE "Argus"),
      "C:\Argus",
      "D:\Argus"
    )) {
    if (-not (Test-Path $base)) { continue }
    $dirs = @($base)
    if ((Get-Item $base).PSIsContainer) {
      $dirs += @(Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    }
    foreach ($c in $dirs) {
      if ((Test-Path (Join-Path $c "apps\eoc")) -and -not (Test-Path (Join-Path $c ".git"))) {
        Log ("Found loose (non-git) Argus tree: {0}" -f $c)
        $hits += $c
      }
    }
  }
  return @($hits | Select-Object -Unique)
}

function New-ArgusCloneFromGitHub {
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is not installed. Install Git for Windows from https://git-scm.com/download/win then re-run this updater."
  }
  $dest = Get-ArgusLocalRoot
  if ((Test-Path $dest) -and -not (Test-Path (Join-Path $dest ".git"))) {
    $dest = Join-Path (Get-ArgusLocalDesktop) ("Argus-github-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
  }
  if ((Test-Path $dest) -and (Test-Path (Join-Path $dest ".git"))) {
    Log ("Using existing Desktop clone: {0}" -f $dest)
    return $dest
  }
  Log ("Cloning https://github.com/brandoncorley01/Argus.git -> {0} (Desktop only, not OneDrive)" -f $dest)
  $null = New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) -ErrorAction SilentlyContinue
  & git clone --branch main --single-branch "https://github.com/brandoncorley01/Argus.git" $dest 2>&1 | ForEach-Object { Log ("  $_") }
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $dest ".git"))) {
    throw "git clone failed (cannot find / create Argus folder). Install Git for Windows and ensure internet access, then re-run."
  }
  $envPath = Join-Path $dest ".env"
  $example = Join-Path $dest ".env.paper.example"
  if (-not (Test-Path $envPath) -and (Test-Path $example)) {
    Copy-Item -LiteralPath $example -Destination $envPath -Force
    Log "Created .env from .env.paper.example"
  }
  return $dest
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
  # WinPS + ErrorAction Stop treats git stderr ("From https://...") as fatal.
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  Push-Location $Root
  try {
    $output = & git @GitArgs 2>&1
    $code = $LASTEXITCODE
    foreach ($line in @($output)) {
      if ($null -eq $line) { continue }
      if ($line -is [System.Management.Automation.ErrorRecord]) {
        Log ("  {0}" -f $line.ToString())
      } else {
        Log ("  {0}" -f $line)
      }
    }
    return $code
  } finally {
    Pop-Location
    $ErrorActionPreference = $prev
  }
}

function Sync-OneRoot([string]$Root, [string]$TargetBuild) {
  Log ("---- Syncing {0} ----" -f $Root)
  Set-Location $Root
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is not installed. Install Git for Windows, then re-run."
  }
  $origin = (& git -C $Root remote get-url origin 2>$null)
  Log ("origin: {0}" -f $(if ($origin) { $origin } else { "?" }))
  if (-not $origin) {
    Log "No git origin — setting origin to brandoncorley01/Argus"
    $null = Invoke-GitAt $Root @("remote", "add", "origin", "https://github.com/brandoncorley01/Argus.git")
    $origin = "https://github.com/brandoncorley01/Argus.git"
  }
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
  Log "Script revision: update-argus-now-v15"
  Log "Uses GitHub API only (no raw CDN fallback)."
  Log "CANONICAL folder: %USERPROFILE%\Desktop\Argus (NOT OneDrive)."
  Log "If OneDrive\Desktop\Argus is serving :3000, it will be stopped; Start uses Desktop only."
  Log "Git stderr no longer aborts Start (WinPS NativeCommandError fix)."
  Log "TARGET read tolerates WinPS byte[] / JSON+base64 API quirks."

  $canonicalRoot = Get-ArgusLocalRoot
  Log ("Canonical Desktop Argus: {0}" -f $canonicalRoot)

  $TargetBuild = Get-GitHubTargetBuild
  Log ("GitHub TARGET build: {0}" -f $TargetBuild)

  # Capture serving folder BEFORE killing :3000.
  $servingRoot = Get-ServingArgusRoot
  if ($servingRoot) {
    Log ("LIVE :3000 folder: {0}" -f $servingRoot)
    if (Test-IsOneDrivePath $servingRoot) {
      Log "LIVE folder is OneDrive — Founder policy is Desktop only. Will Start from Desktop\Argus."
    }
  } else {
    Log "No live :3000 folder detected."
  }

  $found = @(Find-AllArgusRoots)

  # Always ensure canonical Desktop\Argus exists.
  $hasCanonical = @($found | Where-Object { $_.Root -eq $canonicalRoot }).Count -gt 0
  if (-not $hasCanonical) {
    Log "Canonical Desktop\Argus missing — cloning there from GitHub."
    $envSources = New-Object System.Collections.Generic.List[string]
    foreach ($item in $found) { $envSources.Add((Join-Path $item.Root ".env")) | Out-Null }
    foreach ($loose in (Find-LooseEocRoots)) { $envSources.Add((Join-Path $loose ".env")) | Out-Null }
    $envSources.Add((Join-Path $env:USERPROFILE "OneDrive\Desktop\Argus\.env")) | Out-Null
    $cloneRoot = New-ArgusCloneFromGitHub
    $newEnv = Join-Path $cloneRoot ".env"
    foreach ($oldEnv in $envSources) {
      if ((Test-Path $oldEnv) -and (-not (Test-Path $newEnv) -or ((Get-Item $newEnv).Length -lt 10))) {
        Copy-Item -LiteralPath $oldEnv -Destination $newEnv -Force
        Log ("Copied .env from {0}" -f $oldEnv)
        break
      }
    }
    $found = @(Find-AllArgusRoots)
    if (@($found | Where-Object { $_.Root -eq $canonicalRoot }).Count -eq 0) {
      $found = @(
        [pscustomobject]@{
          Root = $cloneRoot
          Build = (Get-BuildIdFromRoot $cloneRoot)
          Sha = ""
          OneDrive = $false
        }
      ) + @($found)
    }
  }

  if ($found.Count -eq 0) {
    throw "No Argus folder available after clone attempt."
  }

  # Sync order: canonical Desktop first, then other non-OneDrive, then OneDrive legacy.
  $ordered = New-Object System.Collections.Generic.List[object]
  foreach ($item in @($found | Where-Object { $_.Root -eq $canonicalRoot })) { $ordered.Add($item) | Out-Null }
  foreach ($item in @($found | Where-Object { $_.Root -ne $canonicalRoot -and -not $_.OneDrive })) { $ordered.Add($item) | Out-Null }
  foreach ($item in @($found | Where-Object { $_.OneDrive })) { $ordered.Add($item) | Out-Null }
  $found = @($ordered)
  Log ("Sync order (Desktop canonical first): {0}" -f (($found | ForEach-Object { $_.Root }) -join " | "))

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

  # Sync every found checkout (Desktop first). Start ONLY from canonical Desktop.
  $synced = @()
  foreach ($item in $found) {
    if ($item.OneDrive) {
      Log ("Syncing OneDrive legacy (will NOT Start from here): {0}" -f $item.Root)
    }
    try {
      $synced += (Sync-OneRoot -Root $item.Root -TargetBuild $TargetBuild)
    } catch {
      if ($item.Root -eq $canonicalRoot) { throw }
      Log ("WARN: skip sync for {0}: {1}" -f $item.Root, $_.Exception.Message)
    }
  }

  $primary = @($synced | Where-Object { $_.Root -eq $canonicalRoot } | Select-Object -First 1)
  if (-not $primary) {
    $primary = @($synced | Where-Object { -not (Test-IsOneDrivePath $_.Root) } | Select-Object -First 1)
  }
  if (-not $primary) { throw "No non-OneDrive Argus folder synced. Canonical should be $canonicalRoot" }
  $Root = $primary[0].Root
  $buildId = $primary[0].Build
  $sha = $primary[0].Sha
  Set-Location $Root
  Log ("Primary Start folder (Desktop only): {0}" -f $Root)
  Log ("Cloud agent does NOT write to this PC — only GitHub. This folder must pull main.")

  $env:ARGUS_FORCE_SYNC = "1"
  Remove-Item Env:ARGUS_START_SELF_UPDATED -ErrorAction SilentlyContinue
  Remove-Item Env:ARGUS_SKIP_START_SELF_UPDATE -ErrorAction SilentlyContinue
  Remove-Item Env:ARGUS_KEEP_DASHBOARD -ErrorAction SilentlyContinue
  Remove-Item Env:ARGUS_ALLOW_STALE -ErrorAction SilentlyContinue

  $starter = Join-Path $Root "scripts\control-center\start-argus.ps1"
  if (-not (Test-Path $starter)) { throw "Start script missing: $starter" }

  # Re-point Desktop shortcuts at canonical Desktop\Argus.
  try {
    $install = Join-Path $Root "scripts\control-center\install-desktop-shortcuts.ps1"
    if (Test-Path $install) {
      Log "Installing Desktop shortcuts aimed at canonical Desktop\Argus..."
      & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $install
    }
  } catch {
    Log ("WARN: shortcut install: {0}" -f $_.Exception.Message)
  }

  Log "Starting Argus from Desktop\Argus..."
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
  Log ("CANONICAL folder: {0}" -f $canonicalRoot)
  Log ("STARTED from:     {0}" -f $Root)
  Log ("TARGET build: {0}" -f $TargetBuild)
  Log ("LOCAL build:  {0}" -f $buildId)
  Log ("HTTP build:   {0}" -f $(if ($httpBuild) { $httpBuild } else { "?" }))
  Log ("API ready: {0}" -f $apiOk)
  Log "Open: http://127.0.0.1:3000/today"
  Log "Hard-refresh Home (Ctrl+F5)."
  Log "Do not Start from OneDrive\Desktop\Argus anymore."
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
