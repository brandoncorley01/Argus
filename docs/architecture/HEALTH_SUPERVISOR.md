# Institutional Health Supervisor and Worker Foundation

Phase 8 adds governed health evidence, evaluation, and a durable ARQ worker that can protect the institution by entering `SAFE_MODE` under fail-closed rules.

## Architecture

```text
ARQ worker (health_supervisor)
  → acquire PostgreSQL lease
  → probe postgres/redis (+ self/api heartbeats)
  → append-only health_heartbeats (ordered + idempotent)
  → update service_health_projections
  → aggregate institutional_health_state
  → open/update incidents + lifecycle events
  → protective-action recommendations
  → SYSTEM actor → OperatingModeService.system_enter_safe_mode
```

PostgreSQL remains the system of record. Redis is the ARQ broker and a probed dependency. Redis is **not** the source of truth for leases, health, or incidents.

## Governed service registry

Seeded services (migration `b8c0d1e2f3a4`):

| service_key | kind | criticality |
| --- | --- | --- |
| `postgres` | postgres | critical |
| `redis` | redis | critical |
| `api` | api | critical |
| `health_supervisor` | supervisor | critical |

Worker identity: `health_supervisor_worker`.

## Heartbeat protocol

- Append-only `health_heartbeats` (DB trigger blocks UPDATE/DELETE).
- Per-service monotonic `sequence_number` (unique).
- Idempotency via `(service_id, idempotency_key_hash)` + request fingerprint.
- Stale or conflicting sequences fail closed with stable error codes.
- Meaningful status transitions also write `service_health_events`.

## Evaluation

- Timeout: no heartbeat within `heartbeat_timeout_seconds` → `unhealthy`.
- `consecutive_failures` increments on critical non-healthy evaluations; resets on healthy.
- Institutional aggregation: any critical `unhealthy` → institutional `unhealthy`; else any degraded/non-critical unhealthy → `degraded`; else `healthy`.

## Supervisor coordination

- Singleton row `health_supervisor_leases` with `FOR UPDATE`.
- Lease holder + `lease_until` + monotonic `lease_epoch`.
- Concurrent cycles: non-holders receive `lease_held` without mutating institutional state.

## Operating-mode integration

Defaults:

1. **SYSTEM actor** — `actor_user_id=NULL`, audit payload `actor=SYSTEM`.
2. Auto-degrade only from `OBSERVE` / `PAPER` / `MICRO_LIVE` / `NORMAL_LIVE`.
3. Threshold: `HEALTH_SUPERVISOR_FAILURE_THRESHOLD` (default 3) consecutive critical failures.

Does not auto-exit `SAFE_MODE` or `EMERGENCY_STOP`.

## APIs

| Method | Path | Auth |
| --- | --- | --- |
| GET | `/api/v1/health/services` | authenticated read |
| GET | `/api/v1/health/services/{key}` | authenticated read |
| GET | `/api/v1/health/institutional` | authenticated read |
| POST | `/api/v1/health/heartbeats` | Founder/Operator + CSRF + Idempotency-Key |
| GET | `/api/v1/health/lease` | authenticated read |
| POST | `/api/v1/health/supervisor/run-cycle` | Founder + CSRF |
| GET | `/api/v1/health/protective-actions` | authenticated read |
| POST | `/api/v1/health/protective-actions/{id}/dismiss` | Founder |
| GET | `/api/v1/workers/identities` | authenticated read |
| GET | `/api/v1/workers/instances` | authenticated read |
| POST | `/api/v1/workers/instances/register` | Founder/Operator |
| GET/POST | `/api/v1/incidents...` | read / Founder-Operator mutate |

## Running the worker

Local:

```powershell
$env:PYTHONPATH = "$PWD\apps\api;$PWD"
apps\api\.venv\Scripts\python.exe -m arq workers.health_supervisor.worker.WorkerSettings
```

Compose (optional profile):

```powershell
docker compose --profile workers up -d --build health_supervisor
```

API remains local uvicorn; Compose still does not containerize the API by default.

## Out of scope

Market data, strategies, signals, orders, positions, paper/live trading, exchanges, portfolio/treasury, Phase 9 EOC UI.
