# Start Argus Control Center — infra, API, EOC; open Founder Dashboard.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root

Write-Host "=== Start Argus ==="
Write-Host "Provider: internal_paper (default)"
Write-Host "Live trading: DISABLED"

if (-not (Test-Path (Join-Path $Root ".env"))) {
  Write-Error "Missing .env. Copy .env.paper.example or .env.example to .env first."
}

& "$Root\scripts\infra-up.ps1"
& "$Root\scripts\migrate-up.ps1"

$pids = Read-ArgusPids $Root
$apiPid = $pids.api
$eocPid = $pids.eoc

if (-not (Test-HttpOk (Get-ArgusApiHealthUrl))) {
  Write-Host "Starting API on 127.0.0.1:8000..."
  $apiLog = Join-Path (Get-ArgusRuntimeDir $Root) "api.log"
  $apiProc = Start-Process -FilePath "powershell.exe" -PassThru -WindowStyle Minimized -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
    "Set-Location '$Root\apps\api'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 *> '$apiLog'"
  )
  $apiPid = $apiProc.Id
} else {
  Write-Host "API already responding"
}

if (-not (Test-HttpOk (Get-ArgusDashboardUrl) 2)) {
  # EOC may redirect; treat any HTTP response as up. Probe login page too.
  $eocUp = (Test-HttpOk "http://127.0.0.1:3000/login") -or (Test-HttpOk "http://127.0.0.1:3000/")
  if (-not $eocUp) {
    Write-Host "Starting EOC on 127.0.0.1:3000..."
    $eocLog = Join-Path (Get-ArgusRuntimeDir $Root) "eoc.log"
    $envBlock = "`$env:ARGUS_API_BASE_URL='http://127.0.0.1:8000'"
    $eocProc = Start-Process -FilePath "powershell.exe" -PassThru -WindowStyle Minimized -ArgumentList @(
      "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
      "Set-Location '$Root'; $envBlock; pnpm eoc:dev *> '$eocLog'"
    )
    $eocPid = $eocProc.Id
  } else {
    Write-Host "EOC already responding"
  }
} else {
  Write-Host "EOC already responding"
}

Write-ArgusPids -Root $Root -ApiPid $apiPid -EocPid $eocPid

$okApi = Wait-HttpOk (Get-ArgusApiReadyUrl) 120 "API /ready"
$okEoc = $false
$deadline = (Get-Date).AddSeconds(120)
while ((Get-Date) -lt $deadline) {
  if ((Test-HttpOk "http://127.0.0.1:3000/login") -or (Test-HttpOk "http://127.0.0.1:3000/") -or (Test-HttpOk (Get-ArgusDashboardUrl))) {
    $okEoc = $true
    Write-Host "OK  EOC ready (http://127.0.0.1:3000)"
    break
  }
  Start-Sleep -Seconds 2
}
if (-not $okEoc) {
  Write-Host "FAIL EOC not ready within 120s"
}

if (-not ($okApi -and $okEoc)) {
  Write-Error "Argus did not become healthy. Check runtime\control-center\*.log"
}

$dash = Get-ArgusDashboardUrl
Write-Host "Opening Founder Dashboard: $dash"
Start-Process $dash
Write-Host "=== Argus started ==="
