$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

Write-Host "=== Argus paper backup ==="
Write-Host "Provider context: internal_paper operating data in Postgres"
try {
  & "$Root\scripts\backup-db.ps1"
  & "$Root\scripts\backup\verify-backup.ps1"
  & "$Root\scripts\validate-db-restore.ps1"
  Write-Host "Backup + integrity + table validation complete."
} catch {
  Write-Host "BACKUP FAILURE: $($_.Exception.Message)"
  $notify = Join-Path $Root "scripts\control-center\_notify.ps1"
  if (Test-Path $notify) {
    . $notify
    Show-ArgusNotification -Title "Argus backup failure" -Message $_.Exception.Message -Level "critical"
  }
  throw
}
