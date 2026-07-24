$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

# Thin wrapper — Control Center owns the Founder-facing script.
& "$Root\scripts\control-center\generate-daily-report.ps1" @args
