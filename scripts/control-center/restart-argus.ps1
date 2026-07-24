# Full Argus restart — stop then start. Preserves Docker volumes / paper history.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root

Write-Host "=== Restart Argus ==="
Write-Host "Preserving Postgres/Redis volumes. Live trading remains DISABLED."

& "$PSScriptRoot\stop-argus.ps1"
Start-Sleep -Seconds 2
& "$PSScriptRoot\start-argus.ps1"
