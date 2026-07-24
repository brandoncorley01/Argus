# Force this PC onto GitHub main Home UI (Start / Stop).
#   irm "https://raw.githubusercontent.com/brandoncorley01/Argus/main/scripts/control-center/force-home-update.ps1?$(Get-Random)" | iex
$ErrorActionPreference = "Continue"

Write-Host "=== Force Argus Home update ==="
Write-Host "Script revision: force-home-update-v4"

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
  throw "Could not find Argus folder. Open PowerShell in your Argus folder and run again."
}

Write-Host "Argus folder: $Root"
Set-Location $Root

function Invoke-Git {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GitArgs)
  Write-Host ("> git " + ($GitArgs -join " "))
  & git @GitArgs
  return $LASTEXITCODE
}

function Stop-ArgusLocks {
  Write-Host "Stopping processes that lock Argus files..."
  foreach ($port in @(3000, 8000)) {
    try {
      Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object {
          Write-Host "  kill PID $($_.OwningProcess) on port $port"
          Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    } catch {}
  }
  Get-Process -Name node, "pnpm", "npm" -ErrorAction SilentlyContinue |
    ForEach-Object {
      Write-Host "  kill $($_.ProcessName) PID $($_.Id)"
      Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
  Start-Sleep -Seconds 2
}

function Clear-GitCleanInteractive {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = "git"
  $psi.Arguments = "clean -fd"
  $psi.WorkingDirectory = $Root
  $psi.RedirectStandardInput = $true
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.UseShellExecute = $false
  $p = [System.Diagnostics.Process]::Start($psi)
  1..20 | ForEach-Object { try { $p.StandardInput.WriteLine("n") } catch {} }
  try { $p.StandardInput.Close() } catch {}
  $out = $p.StandardOutput.ReadToEnd()
  $err = $p.StandardError.ReadToEnd()
  $p.WaitForExit(60000) | Out-Null
  if ($out) { Write-Host $out }
  if ($err) { Write-Host $err }
}

Stop-ArgusLocks

$code = Invoke-Git fetch origin
if ($code -ne 0) { throw "git fetch failed — check internet / GitHub access." }

$killPaths = @(
  "ARGUS_FOUNDER_QUICKSTART.md",
  "apps\eoc\src\app\(app)\layout.tsx",
  "apps\eoc\src\app\(app)\today",
  "apps\eoc\src\app\(app)\trading",
  "apps\eoc\src\app\(app)\portfolio",
  "apps\eoc\src\app\(app)\reports",
  "apps\eoc\src\app\(app)\settings",
  "apps\eoc\src\app\(app)\advanced",
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
  if (Test-Path -LiteralPath $full) {
    Write-Host "  remove $rel"
    Remove-Item -LiteralPath $full -Recurse -Force -ErrorAction SilentlyContinue
  }
}

Clear-GitCleanInteractive
$null = Invoke-Git checkout -f -B main origin/main
$code = Invoke-Git reset --hard origin/main
if ($code -ne 0) { throw "Could not reset to origin/main." }
Clear-GitCleanInteractive

$advanced = Join-Path $Root "apps\eoc\src\app\(app)\advanced"
if (Test-Path -LiteralPath $advanced) {
  $stash = Join-Path $Root ("_trash_advanced_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
  Write-Host "Moving locked advanced folder aside -> $stash"
  try { Move-Item -LiteralPath $advanced -Destination $stash -Force } catch {
    Write-Host "WARN: could not move advanced folder (OneDrive lock). Continuing."
  }
}

$sha = (& git rev-parse --short HEAD).Trim()
$branch = (& git rev-parse --abbrev-ref HEAD).Trim()
Write-Host "OK  Now on $branch @ $sha"
if ($branch -ne "main") { throw "Expected branch main, got $branch" }

$today = Join-Path $Root "apps\eoc\src\app\(app)\today\page.tsx"
if (-not (Test-Path -LiteralPath $today)) {
  throw "Home page missing after update: $today"
}

Stop-ArgusLocks
$starter = Join-Path $Root "scripts\control-center\start-argus.ps1"
if (-not (Test-Path $starter)) { throw "Start script missing after update: $starter" }
Write-Host "Starting Argus with updated Home..."
& $starter

Write-Host ""
Write-Host "SUCCESS markers on Home:"
Write-Host "  - Start Argus / Stop Argus at the top"
Write-Host "  - UI build: home-start-stop-v1 at the bottom"
Write-Host "Hard-refresh browser with Ctrl+F5 if needed."
