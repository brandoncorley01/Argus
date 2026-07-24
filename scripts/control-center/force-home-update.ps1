# Force this PC onto GitHub main Home UI (Start / Stop).
# Run from PowerShell (works even if local Argus is stale):
#   irm https://raw.githubusercontent.com/brandoncorley01/Argus/main/scripts/control-center/force-home-update.ps1 | iex
$ErrorActionPreference = "Stop"

Write-Host "=== Force Argus Home update ==="

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
  throw "Could not find Argus folder. Open PowerShell in your Argus folder and run this again."
}

Write-Host "Argus folder: $Root"
Set-Location $Root

# Keep secrets and local runtime; discard stale UI that blocks GitHub main.
$preserve = @(".env", ".env.paper", ".env.local")
foreach ($name in $preserve) {
  if (Test-Path (Join-Path $Root $name)) {
    Write-Host "Keeping $name"
  }
}

git fetch origin
if ($LASTEXITCODE -ne 0) { throw "git fetch failed — check internet / GitHub access." }

Write-Host "Clearing local UI conflicts so GitHub main can load..."
# Drop modified tracked files and untracked Founder pages that blocked checkout.
git reset --hard HEAD 2>&1 | Out-Host
git clean -fd 2>&1 | Out-Host

git checkout -f -B main origin/main
if ($LASTEXITCODE -ne 0) {
  # Last resort: point branch at origin/main even if checkout complained.
  git symbolic-ref HEAD refs/heads/main 2>&1 | Out-Host
  git reset --hard origin/main
  if ($LASTEXITCODE -ne 0) { throw "Could not reset to origin/main." }
} else {
  git reset --hard origin/main
  if ($LASTEXITCODE -ne 0) { throw "Could not reset to origin/main." }
}

git clean -fd 2>&1 | Out-Host

$sha = (git rev-parse --short HEAD).Trim()
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
Write-Host "OK  Now on $branch @ $sha"

# Stop anything on the dashboard port so the new UI can load.
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
Write-Host "When Home opens, you must see:"
Write-Host "  - Start Argus / Stop Argus buttons at the top"
Write-Host "  - UI build: home-start-stop-v1 at the bottom"
Write-Host "If you still see ACTION NEEDED cards, you are not on this update."
