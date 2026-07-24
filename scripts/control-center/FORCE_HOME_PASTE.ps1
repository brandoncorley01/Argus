# Paste this ENTIRE block into PowerShell (no download / no cache).
$ErrorActionPreference = "Continue"
$Root = "C:\Users\brand\OneDrive\Desktop\Argus"
Set-Location $Root
Write-Host "=== Force Argus Home update (paste) ==="
Write-Host "Folder: $Root"

function Invoke-Git {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GitArgs)
  Write-Host ("> git " + ($GitArgs -join " "))
  & git @GitArgs
  return $LASTEXITCODE
}

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

$null = Invoke-Git clean -fd
$null = Invoke-Git checkout -f -B main origin/main
$code = Invoke-Git reset --hard origin/main
if ($code -ne 0) { throw "reset failed" }
$null = Invoke-Git clean -fd

$sha = (& git rev-parse --short HEAD).Trim()
Write-Host "OK  main @ $sha"

Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

& "$Root\scripts\control-center\start-argus.ps1"
Write-Host "Done. Look for Start/Stop and UI build: home-start-stop-v1"
