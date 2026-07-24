# Paste this ENTIRE block into PowerShell (no download / no cache).
$ErrorActionPreference = "Continue"
$Root = "C:\Users\brand\OneDrive\Desktop\Argus"
Set-Location $Root
Write-Host "=== Force Argus Home update (paste v4) ==="
Write-Host "Folder: $Root"

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
  # git clean can prompt forever on locked OneDrive dirs — never answer interactively.
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = "git"
  $psi.Arguments = "clean -fd"
  $psi.WorkingDirectory = $Root
  $psi.RedirectStandardInput = $true
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.UseShellExecute = $false
  $p = [System.Diagnostics.Process]::Start($psi)
  # Answer "n" to any retry prompts so clean cannot hang.
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
if ($code -ne 0) { throw "git fetch failed" }

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
if ($code -ne 0) { throw "reset failed" }
Clear-GitCleanInteractive

# If advanced/ still exists and is junk, rename it out of the way.
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
Write-Host "OK  $branch @ $sha"
if ($branch -ne "main") { throw "Expected main" }

$today = Join-Path $Root "apps\eoc\src\app\(app)\today\page.tsx"
if (-not (Test-Path -LiteralPath $today)) { throw "Home page missing after reset" }

Stop-ArgusLocks
& "$Root\scripts\control-center\start-argus.ps1"
Write-Host "Done. Look for Start/Stop and UI build: home-start-stop-v1"
