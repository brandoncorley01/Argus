# Verify integrity of the latest Argus Postgres backup (Sprint 4).
# Does not restore or mutate trading history — hash + size checks only.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

$OutDir = Join-Path $Root "backups"
$LastOk = Join-Path $OutDir "LAST_OK.json"
if (-not (Test-Path $LastOk)) {
  Write-Error "No LAST_OK.json under backups/. Run .\scripts\backup-db.ps1 first."
}

$meta = Get-Content -Raw $LastOk | ConvertFrom-Json
$dump = Join-Path $OutDir $meta.filename
if (-not (Test-Path $dump)) {
  Write-Error "Backup dump missing: $dump"
}

$size = (Get-Item $dump).Length
if ($size -lt 100) {
  Write-Error "Backup too small ($size bytes): $dump"
}
if ($meta.size_bytes -and [int64]$meta.size_bytes -ne $size) {
  Write-Error "Size mismatch: meta=$($meta.size_bytes) actual=$size"
}

$sha = (Get-FileHash -Algorithm SHA256 -Path $dump).Hash.ToLowerInvariant()
if ($meta.sha256 -and $meta.sha256.ToLowerInvariant() -ne $sha) {
  Write-Error "SHA256 mismatch for $dump"
}

# Lightweight content sniff — pg_dump text should mention PostgreSQL.
$head = Get-Content -Path $dump -TotalCount 5 -ErrorAction SilentlyContinue
$joined = ($head -join " ")
if ($joined -notmatch "PostgreSQL|pg_dump|--") {
  Write-Warning "Dump header did not look like pg_dump text; hash still matched."
}

Write-Host "OK  Backup integrity verified"
Write-Host ("File:         {0}" -f $dump)
Write-Host ("Completed at: {0}" -f $meta.completed_at)
Write-Host ("Size bytes:   {0}" -f $size)
Write-Host ("SHA256:       {0}" -f $sha)
exit 0
