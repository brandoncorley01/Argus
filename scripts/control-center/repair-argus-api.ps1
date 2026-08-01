# Repair Argus API when Home shows API failure / Unable to reach API.
#   irm "https://raw.githubusercontent.com/brandoncorley01/Argus/main/scripts/control-center/repair-argus-api.ps1?$(Get-Random)" | iex
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

Write-Host "=== Argus API repair ==="
Write-Host "Script revision: repair-argus-api-v1"

$candidates = @(
  (Join-Path $env:USERPROFILE "OneDrive\Desktop\Argus"),
  (Join-Path $env:USERPROFILE "Desktop\Argus"),
  (Join-Path $env:USERPROFILE "OneDrive\Documents\Argus"),
  (Join-Path $env:USERPROFILE "Documents\Argus"),
  (Get-Location).Path
)
try {
  $desktop = [Environment]::GetFolderPath("Desktop")
  $lnk = Join-Path $desktop "Start Argus.lnk"
  if (Test-Path $lnk) {
    $w = New-Object -ComObject WScript.Shell
    $sc = $w.CreateShortcut($lnk)
    if ($sc.WorkingDirectory) { $candidates = @($sc.WorkingDirectory) + $candidates }
  }
} catch {}

$Root = $null
foreach ($c in ($candidates | Select-Object -Unique)) {
  if ($c -and (Test-Path (Join-Path $c ".git")) -and (Test-Path (Join-Path $c "apps\api"))) {
    $Root = $c
    break
  }
}
if (-not $Root) { throw "Could not find Argus folder." }

Write-Host "Argus folder: $Root"
Set-Location $Root

# Pull latest control scripts so Ensure-ArgusApiVenv exists.
$baseUrl = "https://raw.githubusercontent.com/brandoncorley01/Argus/main/scripts/control-center"
foreach ($name in @("_common.ps1", "start-argus.ps1", "repair-argus-api.ps1")) {
  $dest = Join-Path $Root "scripts\control-center\$name"
  $tmp = Join-Path $env:TEMP ("argus-repair-{0}-{1}" -f $name, [guid]::NewGuid().ToString("N"))
  try {
    Invoke-WebRequest -Uri ("{0}/{1}?{2}" -f $baseUrl, $name, (Get-Random)) -OutFile $tmp -UseBasicParsing -TimeoutSec 45
    Copy-Item -LiteralPath $tmp -Destination $dest -Force
    Write-Host "Updated $name"
  } catch {
    Write-Host "WARN: could not refresh $name : $($_.Exception.Message)"
  } finally {
    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
  }
}

. "$Root\scripts\control-center\_common.ps1"

Write-Host "Opening Docker Desktop if needed..."
$null = Ensure-DockerEngine
if (-not (Ensure-ArgusEnvFile $Root)) { throw "Missing .env" }
if (-not (Ensure-ArgusInfra $Root)) {
  throw "Docker Postgres/Redis not healthy. Open Docker Desktop, wait until it is running, then run this again."
}
if (-not (Ensure-ArgusApiVenv $Root)) {
  throw "Could not create API Python environment. Install Python + uv, then retry."
}

Write-Host "Running migrations..."
try {
  & "$Root\scripts\migrate-up.ps1"
} catch {
  Write-Host "WARN: migrate: $($_.Exception.Message)"
}

Write-Host "Starting API..."
$apiPid = Start-ArgusApiProcess $Root
$pids = Read-ArgusPids $Root
Write-ArgusPids -Root $Root -ApiPid $apiPid -EocPid $pids.eoc -WorkerPid $pids.worker

if (-not (Wait-HttpOk (Get-ArgusApiReadyUrl) 120 "API /ready")) {
  Write-Host "FAIL API /ready. Log tail:"
  Write-Host (Get-ArgusApiLogTail $Root 60)
  $desktop = [Environment]::GetFolderPath("Desktop")
  $report = Join-Path $desktop "Argus-api-repair-report.txt"
  @(
    "Argus API repair failed $(Get-Date -Format o)",
    "Root: $Root",
    (Get-ArgusApiLogTail $Root 80)
  ) | Set-Content -Path $report -Encoding utf8
  Write-Host "Report: $report"
  throw "API still not ready. Open Docker Desktop and check Argus-api-repair-report.txt on Desktop."
}

# Worker + keep-awake so paper desk resumes.
$workerPid = Start-ArgusWorkerProcess $Root
Write-ArgusPids -Root $Root -ApiPid $apiPid -EocPid $pids.eoc -WorkerPid $workerPid
$null = Start-ArgusKeepAwake $Root

Write-Host "OK  API /ready"
Write-Host "Open Home: $(Get-ArgusDashboardUrl)"
try { Start-Process (Get-ArgusDashboardUrl) } catch {}
