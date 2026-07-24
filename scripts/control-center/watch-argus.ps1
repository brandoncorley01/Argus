# One-shot operational watch: notify on critical runtime / backup / recon issues.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root

Write-Host "=== Argus operational watch ==="

if (-not (Test-HttpOk (Get-ArgusApiHealthUrl))) {
  Show-ArgusNotification -Title "Argus critical health issue" -Message "API health endpoint is down." -Level "critical"
  Write-Host "API down — notified"
  exit 1
}

try {
  $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/operations/system-health" -TimeoutSec 10 -ErrorAction Stop
} catch {
  # Unauthenticated read may 401 — fall back to process probes only.
  Write-Host "system-health requires auth; using local probes"
  $health = $null
}

if (-not (Test-ArgusWorkerFresh $Root)) {
  Show-ArgusNotification -Title "Argus worker stopped" -Message "Health supervisor worker is not running." -Level "critical"
  & "$PSScriptRoot\restart-failed-workers.ps1"
}

if ($null -ne $health) {
  $monitor = $health.runtime_monitor
  if ($monitor) {
    foreach ($name in @("api", "worker", "scheduler", "reconciliation")) {
      $probe = $monitor.$name
      if ($probe -and $probe.status -eq "failed") {
        $level = if ($name -eq "reconciliation") { "warning" } else { "critical" }
        $title = switch ($name) {
          "api" { "Argus critical health issue" }
          "worker" { "Argus worker stopped" }
          "scheduler" { "Argus scheduler failure" }
          "reconciliation" { "Argus reconciliation failure" }
          default { "Argus alert" }
        }
        Show-ArgusNotification -Title $title -Message ([string]$probe.detail) -Level $level
      }
    }
  }
  $backup = $health.backup
  if ($backup -and $backup.integrity_ok -eq $false) {
    Show-ArgusNotification -Title "Argus backup failure" -Message "Last backup failed integrity verification." -Level "critical"
  }
}

Write-Host "Watch complete."
