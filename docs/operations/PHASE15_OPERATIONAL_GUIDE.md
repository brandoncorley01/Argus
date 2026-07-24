# Phase 15 Operational Guide

Argus operational procedures for **sustained controlled paper trading**.

Live trading is disabled. The only active execution provider is `internal_paper`.

## Daily startup

1. Confirm Docker is running.
2. Start infrastructure:

```powershell
.\scripts\infra-up.ps1
.\scripts\infra-status.ps1
```

3. Apply migrations if needed:

```powershell
.\scripts\migrate-up.ps1
```

4. Start the API (`apps/api`):

```powershell
python -m uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

5. Optionally start the health supervisor worker (host metrics cron + daily report cron):

```powershell
docker compose --profile workers up -d health_supervisor
```

6. Start the EOC:

```powershell
pnpm eoc:dev
```

7. Open **System Health** in the EOC and confirm overall status, Postgres/Redis readiness, and `internal_paper` as default provider.

## Daily shutdown

1. Stop EOC (`Ctrl+C`).
2. Stop API (`Ctrl+C`).
3. Optionally stop workers: `docker compose --profile workers stop health_supervisor`
4. Optionally stop infra: `.\scripts\infra-stop.ps1` (keeps volumes) or leave running for continuous paper ops.

## Health checks

| Check | How |
| --- | --- |
| Liveness | `GET http://127.0.0.1:8000/health` |
| Readiness | `GET http://127.0.0.1:8000/ready` |
| System Health | `GET /api/v1/operations/system-health` or EOC → System Health |
| Host metrics | Worker cron every 5 minutes, or `POST /api/v1/operations/host-metrics/capture` |
| Operational events | `GET /api/v1/operations/events` |

Alert severities: `critical` · `high` · `medium` · `info`.

Every major operational event should include timestamp, component, severity, description, and correlation id (`X-Correlation-ID`).

## Incident response

1. Open EOC → Incidents and System Health → recent events.
2. Note correlation ids from API responses / operational events.
3. Use existing runbooks under `docs/operations/` (paper trading, health supervisor, reconciliation, kill switches).
4. Prefer fail-closed: activate portfolio or global kill switch rather than improvising.
5. Do **not** enable live providers to “fix” paper incidents.

## Daily review

1. System Health: warnings/critical counts, kill switches, last paper trade.
2. Generate or open yesterday’s daily trading report (`POST /api/v1/operations/daily-reports/generate` or worker cron at 00:15 UTC).
3. Confirm report disclaimer states paper-only; review P&L, trade count, exposure, risk events, incidents.
4. Skim Audit Explorer for unexpected mutations.

## Weekly review

1. Backup database: `.\scripts\backup-db.ps1` then `.\scripts\validate-db-restore.ps1`.
2. Review open incidents and unresolved Medium residuals.
3. Confirm CI still green on the release branch (GitHub Actions).
4. Confirm no live activation transitions succeeded.

## Boundaries

- No broker integrations in Phase 15.
- No strategy changes required for ops.
- `internal_paper` remains the only active execution provider.
