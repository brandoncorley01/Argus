# Stop Argus Control Center processes; preserve Docker volumes / DB state.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root

Write-Host "=== Stop Argus ==="
Write-Host "Preserving Postgres/Redis volumes (paper state)."
Write-Host "Live trading remains DISABLED."

$pids = Read-ArgusPids $Root
Stop-PidIfRunning $pids.eoc "EOC launcher"
Stop-PidIfRunning $pids.api "API launcher"
Stop-PidIfRunning $pids.worker "Worker launcher"

# Best-effort: stop listeners on known ports if still held by python/node
foreach ($port in @(8000, 3000)) {
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
Write-ArgusPids -Root $Root -ApiPid $null -EocPid $null -WorkerPid $null
Write-Host "=== Argus stopped (data preserved) ==="
