# Restart failed health-supervisor workers only. Never mutates trading history.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root

Write-Host "=== Restart failed workers only ==="
Write-Host "Preserving Postgres/Redis volumes and paper trading history."

$pids = Read-ArgusPids $Root
$fresh = Test-ArgusWorkerFresh $Root

if ($fresh) {
  Write-Host "Worker process appears healthy - no restart."
  exit 0
}

Write-Host "Worker unhealthy or missing - restarting worker only."
Show-ArgusNotification -Title "Argus worker stopped" -Message "Restarting health supervisor worker only." -Level "warning"

Stop-PidIfRunning $pids.worker "Worker launcher"
# Also stop compose worker if present (does not remove volumes)
try {
  docker compose --profile workers stop health_supervisor 2>$null | Out-Null
} catch {}

$workerPid = Start-ArgusWorkerProcess $Root
Write-ArgusPids -Root $Root -ApiPid $pids.api -EocPid $pids.eoc -WorkerPid $workerPid
Start-Sleep -Seconds 3

if (Test-ArgusWorkerFresh $Root) {
  Write-Host "OK  Worker restarted (PID $workerPid)"
  exit 0
}

Show-ArgusNotification -Title "Argus worker recovery failed" -Message "Worker did not stay up after restart." -Level "critical"
Write-Error "Worker restart failed. See runtime\control-center\worker.log"