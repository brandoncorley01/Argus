# Open Founder Dashboard in the default browser.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"
$url = Get-ArgusDashboardUrl
Write-Host "Opening $url"
Start-Process $url
