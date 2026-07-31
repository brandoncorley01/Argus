# FORCE this PC onto current GitHub main (build stamp + dashboard).
# Run in PowerShell (works even when Start is stuck on an old build):
#   irm "https://raw.githubusercontent.com/brandoncorley01/Argus/main/scripts/control-center/update-argus-now.ps1?$(Get-Random)" | iex
#
# Preserves .env and runtime/ (gitignored). Stops ports 3000/8000, hard-resets
# to origin/main, clears .next, then runs Start Argus.
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

Write-Host "=== Argus UPDATE NOW (force GitHub main) ==="
Write-Host "Script revision: update-argus-now-v1"

function Find-ArgusRoot {
  $candidates = @(
    (Join-Path $env:USERPROFILE "OneDrive\Desktop\Argus"),
    (Join-Path $env:USERPROFILE "Desktop\Argus"),
    (Join-Path $env:USERPROFILE "OneDrive\Documents\Argus"),
    (Join-Path $env:USERPROFILE "Documents\Argus"),
    (Join-Path $env:USERPROFILE "source\Argus"),
    (Join-Path $env:USERPROFILE "src\Argus"),
    (Get-Location).Path
  )
  # Also search common Desktop/OneDrive trees one level deep.
  foreach ($base in @(
      (Join-Path $env:USERPROFILE "Desktop"),
      (Join-Path $env:USERPROFILE "OneDrive\Desktop"),
      (Join-Path $env:USERPROFILE "Documents"),
      (Join-Path $env:USERPROFILE "OneDrive\Documents")
    )) {
    if (Test-Path $base) {
      Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match 'argus' } |
        ForEach-Object { $candidates += $_.FullName }
    }
  }
  foreach ($c in ($candidates | Select-Object -Unique)) {
    if (-not $c) { continue }
    if ((Test-Path (Join-Path $c ".git")) -and (Test-Path (Join-Path $c "apps\eoc"))) {
      return $c
    }
  }
  return $null
}

function Stop-PortListeners([int[]]$Ports) {
  foreach ($port in $Ports) {
    try {
      Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object {
          Write-Host "  kill PID $($_.OwningProcess) on port $port"
          Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    } catch {}
  }
}

function Invoke-GitAt([string]$Root, [string[]]$GitArgs) {
  Write-Host ("> git " + ($GitArgs -join " "))
  Push-Location $Root
  try {
    & git @GitArgs
    return $LASTEXITCODE
  } finally {
    Pop-Location
  }
}

$Root = Find-ArgusRoot
if (-not $Root) {
  throw "Could not find Argus folder (.git + apps\eoc). cd into Argus and run again."
}

Write-Host "Argus folder: $Root"
Set-Location $Root

Write-Host "Stopping API/dashboard locks..."
Stop-PortListeners @(3000, 8000)
Get-Process -Name node, pnpm, npm -ErrorAction SilentlyContinue | ForEach-Object {
  try {
    if ($_.Path -and $_.Path -like "*Argus*") {
      Write-Host "  kill $($_.ProcessName) PID $($_.Id)"
      Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
  } catch {}
}
Start-Sleep -Seconds 2

$code = Invoke-GitAt $Root @("fetch", "origin")
if ($code -ne 0) { throw "git fetch failed — check internet / GitHub access." }

Write-Host "Hard reset to origin/main (preserves .env / runtime)..."
$null = Invoke-GitAt $Root @("checkout", "-f", "-B", "main", "origin/main")
$code = Invoke-GitAt $Root @("reset", "--hard", "origin/main")
if ($code -ne 0) { throw "git reset --hard origin/main failed." }
$null = Invoke-GitAt $Root @("clean", "-fd", "--exclude=.env", "--exclude=runtime", "--exclude=backups")

$sha = (& git -C $Root rev-parse --short HEAD).Trim()
$branch = (& git -C $Root rev-parse --abbrev-ref HEAD).Trim()
Write-Host "OK  Now on $branch @ $sha"

$buildFile = Join-Path $Root "apps\eoc\src\lib\build.ts"
if (-not (Test-Path $buildFile)) { throw "Missing build.ts after reset." }
$buildText = Get-Content -Raw $buildFile
if ($buildText -notmatch 'ARGUS_UI_BUILD\s*=\s*"([^"]+)"') {
  throw "Could not read ARGUS_UI_BUILD from build.ts"
}
$buildId = $Matches[1]
Write-Host "OK  Build stamp on disk: $buildId"

$nextCache = Join-Path $Root "apps\eoc\.next"
if (Test-Path $nextCache) {
  Write-Host "Clearing Next.js cache..."
  Remove-Item -LiteralPath $nextCache -Recurse -Force -ErrorAction SilentlyContinue
}

# Force Start to sync even if something races.
$env:ARGUS_FORCE_SYNC = "1"
$env:ARGUS_START_SELF_UPDATED = $null
$env:ARGUS_SKIP_START_SELF_UPDATE = $null
$env:ARGUS_KEEP_DASHBOARD = $null

$starter = Join-Path $Root "scripts\control-center\start-argus.ps1"
if (-not (Test-Path $starter)) { throw "Start script missing: $starter" }

Write-Host "Starting Argus from updated tree..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $starter
$startExit = $LASTEXITCODE

Write-Host ""
Write-Host "=== UPDATE NOW finished (exit $startExit) ==="
Write-Host "Expected on Home after Ctrl+F5: Build $buildId"
Write-Host "If still old: wrong Argus folder, or browser tab not hard-refreshed."
if ($startExit -ne 0) { exit $startExit }
