# Recycle the dashboard after a browser Start finished (so Next.js picks up a new build stamp).
# Invoked delayed/hidden by start-argus.ps1 — never flash a console window.
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root

$delaySec = 6
if ($args.Count -ge 1) {
  try { $delaySec = [int]$args[0] } catch { $delaySec = 6 }
}
Write-Host "Waiting ${delaySec}s before dashboard recycle..."
Start-Sleep -Seconds $delaySec

$nextCache = Join-Path $Root "apps\eoc\.next"
if (Test-Path $nextCache) {
  Write-Host "Clearing dashboard cache..."
  Remove-Item -LiteralPath $nextCache -Recurse -Force -ErrorAction SilentlyContinue
}

$pids = Read-ArgusPids $Root
Stop-PidIfRunning $pids.eoc "EOC launcher"
Stop-ArgusPortListeners @(3000)

Write-Host "Starting dashboard on 127.0.0.1:3000..."
$eocLog = Join-Path (Get-ArgusRuntimeDir $Root) "eoc.log"
$envBlock = "`$env:ARGUS_API_BASE_URL='http://127.0.0.1:8000'; `$env:ARGUS_REPO_ROOT='$Root'"
$eocProc = Start-Process -FilePath "powershell.exe" -PassThru -WindowStyle Hidden -ArgumentList @(
  "-NoProfile", "-NoLogo", "-NonInteractive", "-ExecutionPolicy", "Bypass",
  "-WindowStyle", "Hidden", "-Command",
  "Set-Location '$Root'; $envBlock; pnpm eoc:dev *> '$eocLog'"
)
Write-ArgusPids -Root $Root -ApiPid $pids.api -EocPid $eocProc.Id -WorkerPid $pids.worker

$deadline = (Get-Date).AddSeconds(120)
while ((Get-Date) -lt $deadline) {
  if ((Test-HttpOk "http://127.0.0.1:3000/login") -or (Test-HttpOk "http://127.0.0.1:3000/") -or (Test-HttpOk (Get-ArgusDashboardUrl))) {
    Write-Host "OK  Dashboard recycled ($(Get-ArgusDashboardUrl))"
    exit 0
  }
  Start-Sleep -Seconds 2
}
Write-Host "WARN: dashboard did not become ready within 120s after recycle"
exit 1
