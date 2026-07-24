# Generate yesterday's (UTC) Internal Paper daily report via the API.
# Requires API up and ARGUS_OPERATOR_USERNAME / ARGUS_OPERATOR_PASSWORD (or BOOTSTRAP_*) in env/.env
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
Set-Location $Root

function Get-DotEnvValue([string]$Key) {
  $envPath = Join-Path $Root ".env"
  if (-not (Test-Path $envPath)) { return $null }
  $line = Get-Content $envPath | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -First 1
  if (-not $line) { return $null }
  return ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
}

Write-Host "=== Generate daily paper report ==="

if (-not (Test-HttpOk (Get-ArgusApiReadyUrl))) {
  Show-ArgusNotification -Title "Argus startup failed" -Message "API not ready; cannot generate daily report." -Level "critical"
  Write-Error "API /ready is down. Start Argus first."
}

$user = $env:ARGUS_OPERATOR_USERNAME
if (-not $user) { $user = Get-DotEnvValue "ARGUS_OPERATOR_USERNAME" }
if (-not $user) { $user = Get-DotEnvValue "ARGUS_BOOTSTRAP_USERNAME" }

$pass = $env:ARGUS_OPERATOR_PASSWORD
if (-not $pass) { $pass = Get-DotEnvValue "ARGUS_OPERATOR_PASSWORD" }
if (-not $pass) { $pass = Get-DotEnvValue "ARGUS_BOOTSTRAP_PASSWORD" }

if (-not $user -or -not $pass) {
  Write-Error "Set ARGUS_OPERATOR_USERNAME and ARGUS_OPERATOR_PASSWORD (or BOOTSTRAP_*) in .env for CLI report generation. Or use the Founder Dashboard form."
}

$loginBody = @{ identifier = $user; password = $pass } | ConvertTo-Json
$session = $null
try {
  $login = Invoke-WebRequest -Method POST -Uri "http://127.0.0.1:8000/api/v1/auth/login" `
    -ContentType "application/json" -Body $loginBody -SessionVariable session -UseBasicParsing
} catch {
  Show-ArgusNotification -Title "Argus report failed" -Message "Login failed for daily report." -Level "critical"
  throw
}

$csrf = ($login.Content | ConvertFrom-Json).csrf_token
$genBody = "{}"
if ($args.Count -ge 1 -and $args[0]) {
  $genBody = (@{ report_date = [string]$args[0] } | ConvertTo-Json)
}

try {
  $res = Invoke-WebRequest -Method POST -Uri "http://127.0.0.1:8000/api/v1/operations/daily-reports/generate" `
    -WebSession $session -Headers @{ "X-CSRF-Token" = $csrf } `
    -ContentType "application/json" -Body $genBody -UseBasicParsing
  $report = $res.Content | ConvertFrom-Json
  Write-Host ("OK  Daily report generated for {0}" -f $report.report_date)
  Show-ArgusNotification -Title "Argus daily report" -Message ("Generated for {0}" -f $report.report_date) -Level "info"
} catch {
  $msg = $_.Exception.Message
  if ($_.ErrorDetails.Message) { $msg = $_.ErrorDetails.Message }
  Show-ArgusNotification -Title "Argus report failed" -Message $msg -Level "warning"
  throw
}

Write-Host "Live trading remains DISABLED. Provider: internal_paper."
