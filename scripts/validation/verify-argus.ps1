$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

Write-Host "=== Argus verify (repository-native) ==="
Write-Host "Provider under test: internal_paper"
Write-Host "Live execution: must remain disabled"

Push-Location "$Root\apps\api"
try {
  & .\.venv\Scripts\python.exe -m ruff check app tests
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  & .\.venv\Scripts\python.exe -m mypy app
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  & .\.venv\Scripts\python.exe -m pytest -q --tb=line
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
  Pop-Location
}

Push-Location "$Root\apps\eoc"
try {
  pnpm typecheck
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  if (Test-Path ".next") { Remove-Item -Recurse -Force ".next" }
  pnpm build
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
  Pop-Location
}

Write-Host "Running paper E2E harness..."
& "$Root\apps\api\.venv\Scripts\python.exe" "$Root\scripts\rc_e2e_paper_validation.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== VERIFY PASS ==="
