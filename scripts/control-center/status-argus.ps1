# Argus Control Center status
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root

$apiUp = Test-HttpOk (Get-ArgusApiHealthUrl)
$readyUp = Test-HttpOk (Get-ArgusApiReadyUrl)
$eocUp = (Test-HttpOk "http://127.0.0.1:3000/login") -or (Test-HttpOk "http://127.0.0.1:3000/") -or (Test-HttpOk (Get-ArgusDashboardUrl))

$running = if ($apiUp -or $eocUp) { "Running" } else { "Stopped" }

Write-Host "=== Argus Status ==="
Write-Host ("State:            {0}" -f $running)
Write-Host ("API health:       {0}" -f ($(if ($apiUp) { "up" } else { "down" })))
Write-Host ("API ready:        {0}" -f ($(if ($readyUp) { "up" } else { "down" })))
Write-Host ("EOC:              {0}" -f ($(if ($eocUp) { "up" } else { "down" })))
Write-Host "Provider:         internal_paper (default / certified paper)"
Write-Host "Live trading:     DISABLED (not certified)"
Write-Host ("Dashboard URL:    {0}" -f (Get-ArgusDashboardUrl))

try {
  & "$Root\scripts\infra-status.ps1"
} catch {
  Write-Host "Infra status unavailable"
}
