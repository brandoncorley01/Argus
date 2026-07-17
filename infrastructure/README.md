# Infrastructure

Local infrastructure foundation for Argus v0.1 Phase 1.

## Services

| Service | Image | Purpose |
| --- | --- | --- |
| `postgres` | `postgres:16` | Institutional system of record (empty of app schema in Phase 1) |
| `redis` | `redis:7` | Coordination / future ARQ broker |

Compose file: [`../docker-compose.yml`](../docker-compose.yml) (repo root for standard operator discovery).

## Prerequisites

1. Install [Docker Desktop](https://docs.docker.com/desktop/) (Windows/macOS) or Docker Engine + Compose V2 (Linux).
2. Ensure `docker` and `docker compose` are on `PATH`.
3. Copy `.env.example` to `.env` and set `POSTGRES_PASSWORD`.

## Operator commands

PowerShell (Windows):

```powershell
.\scripts\infra-up.ps1
.\scripts\infra-status.ps1
.\scripts\infra-logs.ps1
.\scripts\infra-stop.ps1
.\scripts\infra-down.ps1
.\scripts\infra-reset.ps1   # WARNING: deletes local data volumes
```

Bash:

```bash
./scripts/infra-up.sh
./scripts/infra-status.sh
./scripts/infra-logs.sh
./scripts/infra-stop.sh
./scripts/infra-down.sh
./scripts/infra-reset.sh   # WARNING: deletes local data volumes
```

## Health

- PostgreSQL: `pg_isready`
- Redis: `redis-cli ping`

Ports bind to `127.0.0.1` only for local development.

## Out of scope

No application schemas, trading tables, exchange integrations, or live credentials in Phase 1.
