# Stop Argus trading services; keep the Founder dashboard up so Start/Stop remain available.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root

Write-Host "=== Stop Argus ==="
Write-Host "Stopping API and worker. Dashboard stays open."
Write-Host "Preserving Postgres/Redis volumes (paper state)."
Write-Host "Live trading remains DISABLED."

$pids = Read-ArgusPids $Root
Stop-PidIfRunning $pids.api "API launcher"
Stop-PidIfRunning $pids.worker "Worker launcher"

# Stop API port only — do NOT kill the dashboard on port 3000.
foreach ($port in @(8000)) {
  try {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
      if ($c.OwningProcess) {
        Write-Host "Stopping process on port $port (PID $($c.OwningProcess))"
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
      }
    }
  } catch {
    # Get-NetTCPConnection may be unavailable; ignore
  }
}

& "$Root\scripts\infra-stop.ps1"
Write-ArgusPids -Root $Root -ApiPid $null -EocPid $pids.eoc -WorkerPid $null
Write-Host "=== Argus stopped (dashboard still available) ==="
