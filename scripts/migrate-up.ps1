$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\apps\api"
python -m uv run alembic upgrade head
