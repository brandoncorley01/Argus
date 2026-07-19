# Health Supervisor Recovery

Operational recovery guidance for Phase 8 health supervision.

## Symptoms

| Symptom | Likely cause |
| --- | --- |
| Institutional health stuck `unhealthy` | Critical dependency probe failing or heartbeats timed out |
| Supervisor `lease_held` | Another worker instance holds an unexpired lease |
| Unexpected `SAFE_MODE` | Threshold of consecutive critical failures reached |
| Heartbeat `stale_sequence` | Client replayed an old sequence or clock/process restarted without syncing projection |
| Migration / audit 503 | Audit or DB unavailable — fail closed |

## Safe recovery steps

1. **Do not initialize SystemState** unless intentionally demonstrating modes. Health tests create isolated state.
2. Confirm Postgres and Redis health: `docker compose ps`, `pg_isready`, `redis-cli ping`.
3. Confirm Alembic head is `b8c0d1e2f3a4`.
4. Inspect:
   - `GET /api/v1/health/institutional`
   - `GET /api/v1/health/supervisor`
   - `GET /api/v1/health/services/{key}`
   - `GET /api/v1/incidents`
5. If a stale worker holds the lease, wait for `lease_until` expiry or stop the stale process, then run one Founder `POST /api/v1/health/supervisor/run`.
6. Exit `SAFE_MODE` only via the Phase 7 mode API (Founder + reason to `OBSERVE`). Health supervisor never auto-recovers mode.
7. Dismiss obsolete protective recommendations as Founder when appropriate.

## What not to do

- Do not delete append-only heartbeat or incident lifecycle rows to “fix” history.
- Do not overwrite Founder accounts.
- Do not bypass audit or RBAC.
- Do not treat Redis as authoritative for health or leases.
