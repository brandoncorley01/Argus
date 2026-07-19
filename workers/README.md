# workers/

ARQ background workers for Argus.

## Phase 8 — Health Supervisor

Package: `workers/health_supervisor`

Run locally (infra Postgres + Redis must be healthy; API package on `PYTHONPATH`):

```powershell
cd <repo-root>
$env:PYTHONPATH = "$PWD\apps\api;$PWD"
apps\api\.venv\Scripts\python.exe -m arq workers.health_supervisor.worker.WorkerSettings
```

Optional Compose service `health_supervisor` runs the same command inside a Python image with the repo mounted.

The worker reuses API domain services (no privilege side doors). It records heartbeats, evaluates health, opens incidents, and may apply SYSTEM `SAFE_MODE` under fail-closed audit rules.
