# End Trading Day - generate/confirm daily paper report, then backup.
# Does not stop Argus and does not liquidate positions.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root

Write-Host "=== End Trading Day ==="
Write-Host "Paper only. Live trading remains DISABLED."

$reportOk = $false
try {
  & "$PSScriptRoot\generate-daily-report.ps1"
  $reportOk = $true
} catch {
  $msg = $_.Exception.Message
  if ($msg -match "immutable|already exists|409") {
    Write-Host "A report already exists for this date - kept as-is."
    $reportOk = $true
  } else {
    Write-Host "REPORT ISSUE: $msg"
    Show-ArgusNotification -Title "Argus End Day" -Message "Report step failed." -Level "warning"
  }
}

$backupOk = $false
try {
  & "$PSScriptRoot\backup-argus.ps1"
  $backupOk = $true
} catch {
  Write-Host "BACKUP FAILED: $($_.Exception.Message)"
  Show-ArgusNotification -Title "Argus backup failure" -Message $_.Exception.Message -Level "critical"
}

if ($reportOk -and $backupOk) {
  Show-ArgusNotification -Title "Trading day closed" -Message "Report ready. Backup verified." -Level "info"
  Write-Host "=== End Trading Day complete ==="
  Write-Host "Next: Stop Argus if you are done for the day."
  exit 0
}

Write-Error "End Trading Day finished with issues (reportOk=$reportOk backupOk=$backupOk)."
