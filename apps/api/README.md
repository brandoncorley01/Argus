# Argus API

FastAPI control-plane for Argus v0.1 Foundation.

## Scope (Phase 2)

- Settings fail closed when required configuration is missing
- PostgreSQL and Redis readiness probes
- No domain schemas, auth UI, trading, or live modes

## Prerequisites

- Python 3.12+
- `uv` (`python -m pip install uv` if needed)
- Phase 1 infrastructure running (`.\scripts\infra-up.ps1`)

## Setup

```powershell
cd apps\api
python -m uv sync
```

Copy root `.env.example` values into the repo-root `.env` (includes `DATABASE_URL` / `REDIS_URL` after Phase 2).

## Run

From `apps/api`:

```powershell
python -m uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Endpoints

| Path | Purpose |
| --- | --- |
| `GET /health` | Liveness + dependency probe summary |
| `GET /ready` | Readiness (503 if Postgres or Redis unhealthy) |
| `POST /api/v1/auth/login` | Local login (sets HTTP-only session cookie; returns CSRF token) |
| `POST /api/v1/auth/logout` | Logout + revoke session (CSRF required) |
| `GET /api/v1/auth/me` | Current authenticated principal |
| `POST /api/v1/auth/users` | Founder-only user creation (CSRF required) |
| `POST /api/v1/auth/users/{id}/roles` | Founder-only role assignment (CSRF required) |
| `GET /api/v1/audit/events` | List audit events (authenticated) |
| `GET /api/v1/audit/events/{id}` | Fetch one audit event (authenticated) |

## Founder bootstrap

See [`docs/architecture/AUTHENTICATION.md`](../../docs/architecture/AUTHENTICATION.md).

## Migrations

```powershell
python -m uv run alembic upgrade head
python -m uv run alembic downgrade base
python -m uv run alembic current
```

## Tests

```powershell
python -m uv run pytest
python -m uv run ruff check app tests
python -m uv run mypy app
```
