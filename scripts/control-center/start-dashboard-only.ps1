# Minimal dashboard start for Founder Home verification (ASCII only).
# Does not run git sync. Starts API + dashboard if needed.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root

Write-Host "=== Start dashboard only ==="
Write-Host "Root: $Root"

$today = Join-Path $Root "apps\eoc\src\app\(app)\today\page.tsx"
$bar = Join-Path $Root "apps\eoc\src\components\founder\CommandStatusBar.tsx"
if (-not (Test-Path -LiteralPath $today)) { throw "Missing Home page: $today" }
if (-not (Test-Path -LiteralPath $bar)) { throw "Missing CommandStatusBar: $bar" }
$todayText = Get-Content -LiteralPath $today -Raw
$barText = Get-Content -LiteralPath $bar -Raw
if ($todayText -notmatch "CommandStatusBar") { throw "Home page does not include CommandStatusBar" }
if ($barText -notmatch "Start Argus") { throw "CommandStatusBar missing Start Argus button" }
Write-Host "OK  Home Command Center controls are present"

if (-not (Test-Path (Join-Path $Root ".env"))) {
  throw "Missing .env"
}

& "$Root\scripts\infra-up.ps1"

$pids = Read-ArgusPids $Root
$apiPid = $pids.api
$eocPid = $pids.eoc
$workerPid = $pids.worker

if (-not (Test-HttpOk (Get-ArgusApiHealthUrl))) {
  $apiPid = Start-ArgusApiProcess $Root
} else {
  Write-Host "API already up"
}

if (-not (Test-ArgusWorkerFresh $Root)) {
  $workerPid = Start-ArgusWorkerProcess $Root
}

$nextCache = Join-Path $Root "apps\eoc\.next"
if (Test-Path $nextCache) {
  Write-Host "Clearing .next cache..."
  Remove-Item -LiteralPath $nextCache -Recurse -Force -ErrorAction SilentlyContinue
}

foreach ($port in @(3000)) {
  try {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
      ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
  } catch {}
}

Write-Host "Starting dashboard..."
$eocLog = Join-Path (Get-ArgusRuntimeDir $Root) "eoc.log"
$envBlock = "`$env:ARGUS_API_BASE_URL='http://127.0.0.1:8000'"
$eocProc = Start-Process -FilePath "powershell.exe" -PassThru -WindowStyle Hidden -ArgumentList @(
  "-NoProfile", "-NoLogo", "-NonInteractive", "-ExecutionPolicy", "Bypass",
  "-WindowStyle", "Hidden", "-Command",
  "Set-Location '$Root'; $envBlock; pnpm eoc:dev *> '$eocLog'"
)
$eocPid = $eocProc.Id
Write-ArgusPids -Root $Root -ApiPid $apiPid -EocPid $eocPid -WorkerPid $workerPid

$okApi = Wait-HttpOk (Get-ArgusApiReadyUrl) 120 "API /ready"
$okEoc = $false
$deadline = (Get-Date).AddSeconds(120)
while ((Get-Date) -lt $deadline) {
  if ((Test-HttpOk "http://127.0.0.1:3000/login") -or (Test-HttpOk "http://127.0.0.1:3000/today")) {
    $okEoc = $true
    break
  }
  Start-Sleep -Seconds 2
}

if (-not ($okApi -and $okEoc)) {
  Write-Host "API ok=$okApi dashboard ok=$okEoc"
  Write-Host "Check logs: runtime\control-center\api.log and eoc.log"
  throw "Dashboard did not become ready"
}

Write-Host "Opening Home..."
Start-Process "http://127.0.0.1:3000/today"
Write-Host "=== Dashboard started ==="
Write-Host "Look for Start Argus / Stop Argus and UI build: market-command-v1"
