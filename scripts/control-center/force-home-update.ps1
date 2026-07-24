# Force this PC onto GitHub main Home UI (Start / Stop).
# Prefer this cache-busted command:
#   irm "https://raw.githubusercontent.com/brandoncorley01/Argus/main/scripts/control-center/force-home-update.ps1?$(Get-Random)" | iex
$ErrorActionPreference = "Continue"

Write-Host "=== Force Argus Home update ==="
Write-Host "Script revision: force-home-update-v3"

$candidates = @(
  (Join-Path $env:USERPROFILE "OneDrive\Desktop\Argus"),
  (Join-Path $env:USERPROFILE "Desktop\Argus"),
  (Join-Path $env:USERPROFILE "OneDrive\Documents\Argus"),
  (Join-Path $env:USERPROFILE "Documents\Argus"),
  (Get-Location).Path
)

$Root = $null
foreach ($c in $candidates) {
  if ($c -and (Test-Path (Join-Path $c ".git")) -and (Test-Path (Join-Path $c "apps\eoc"))) {
    $Root = $c
    break
  }
}

if (-not $Root) {
  throw "Could not find Argus folder. Open PowerShell in C:\Users\brand\OneDrive\Desktop\Argus and run again."
}

Write-Host "Argus folder: $Root"
Set-Location $Root

function Invoke-Git {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GitArgs)
  Write-Host ("> git " + ($GitArgs -join " "))
  & git @GitArgs
  return $LASTEXITCODE
}

# 1) Fetch GitHub main
$code = Invoke-Git fetch origin
if ($code -ne 0) { throw "git fetch failed — check internet / GitHub access." }

# 2) Delete known local UI leftovers that block checkout (tracked or untracked).
$killPaths = @(
  "ARGUS_FOUNDER_QUICKSTART.md",
  "apps\eoc\src\app\(app)\layout.tsx",
  "apps\eoc\src\app\(app)\today",
  "apps\eoc\src\app\(app)\trading",
  "apps\eoc\src\app\(app)\portfolio",
  "apps\eoc\src\app\(app)\reports",
  "apps\eoc\src\app\(app)\settings",
  "apps\eoc\src\app\globals.css",
  "apps\eoc\src\app\login\page.tsx",
  "apps\eoc\src\app\page.tsx",
  "apps\eoc\src\components\SideNav.tsx",
  "apps\eoc\src\components\founder",
  "apps\eoc\src\lib\actions\auth.ts",
  "apps\eoc\src\lib\actions\operations.ts",
  "apps\eoc\src\lib\actions\control.ts",
  "apps\eoc\src\lib\founder",
  "apps\eoc\src\lib\build.ts",
  "apps\eoc\src\middleware.ts",
  "scripts\control-center\_common.ps1",
  "scripts\control-center\install-desktop-shortcuts.ps1",
  "scripts\control-center\end-trading-day.ps1",
  "scripts\control-center\start-argus.ps1",
  "scripts\control-center\stop-argus.ps1"
)

Write-Host "Removing local conflicting files..."
foreach ($rel in $killPaths) {
  $full = Join-Path $Root $rel
  if (Test-Path $full) {
    Write-Host "  remove $rel"
    Remove-Item -LiteralPath $full -Recurse -Force -ErrorAction SilentlyContinue
  }
}

# 3) Clean any other untracked non-ignored junk, then hard-reset to origin/main.
$null = Invoke-Git clean -fd
$null = Invoke-Git checkout -f -B main origin/main
$code = Invoke-Git reset --hard origin/main
if ($code -ne 0) { throw "Could not reset to origin/main." }
$null = Invoke-Git clean -fd

$sha = (& git rev-parse --short HEAD).Trim()
$branch = (& git rev-parse --abbrev-ref HEAD).Trim()
Write-Host "OK  Now on $branch @ $sha"

if ($branch -ne "main") { throw "Expected branch main, got $branch" }

$today = Join-Path $Root "apps\eoc\src\app\(app)\today\page.tsx"
if (-not (Test-Path -LiteralPath $today)) {
  throw "Home page missing after update: $today"
}
$todayText = Get-Content -LiteralPath $today -Raw
if ($todayText -notmatch "ControlBar") {
  throw "Home page still missing Start/Stop ControlBar after update."
}
if ($todayText -notmatch "home-start-stop-v1") {
  Write-Host "WARN: build marker not found in today page text (may still be ok)."
}

# 4) Kill old dashboard process
foreach ($port in @(3000)) {
  try {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
      if ($c.OwningProcess) {
        Write-Host "Stopping old dashboard PID $($c.OwningProcess)"
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
      }
    }
  } catch {}
}

$starter = Join-Path $Root "scripts\control-center\start-argus.ps1"
if (-not (Test-Path $starter)) {
  throw "Start script missing after update: $starter"
}

Write-Host "Starting Argus with updated Home..."
& $starter

Write-Host ""
Write-Host "SUCCESS markers to look for on Home:"
Write-Host "  - Start Argus / Stop Argus at the top"
Write-Host "  - UI build: home-start-stop-v1 at the bottom"
Write-Host "If you still see ACTION NEEDED, hard-refresh the browser (Ctrl+F5)."
