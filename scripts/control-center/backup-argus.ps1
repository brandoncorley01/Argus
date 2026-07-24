# Founder backup launcher — wraps paper backup + integrity verify.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root

Write-Host "=== Backup Argus ==="
try {
  & "$Root\scripts\backup\backup-paper.ps1"
  Show-ArgusNotification -Title "Argus backup complete" -Message "Paper DB backup verified." -Level "info"
} catch {
  Show-ArgusNotification -Title "Argus backup failure" -Message $_.Exception.Message -Level "critical"
  throw
}
