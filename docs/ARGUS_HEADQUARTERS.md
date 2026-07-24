# Argus Headquarters

**GitHub is the source of truth.** Cursor is an optional development client, not the operating environment.

Argus must run, be operated, and be released without Cursor remaining open.

## Authority model

| Concern | Authority |
| --- | --- |
| Source code & history | GitHub repository |
| Operating interface | Executive Operations Center (EOC) |
| Local paper runtime | Docker Compose + API + optional worker + EOC |
| Verification | Repository-native tests + GitHub Actions CI |
| Releases | Tagged commits + `docs/releases/` evidence |
| Secrets | Local `.env` / operator vault — **never** the repo |
| Backups | Local `backups/` (gitignored) via scripts |

## What belongs in the repository

- Application source (`apps/`, `workers/`)
- Infrastructure configuration (`docker-compose.yml`, `.env.example` templates)
- Database migrations (`apps/api/alembic/`)
- Automated tests (`apps/api/tests/`)
- Operational scripts (`scripts/`)
- Governance, architecture, operations, and release documentation (`docs/`)
- CI workflow (`.github/workflows/`)
- Release evidence markdown (not raw DB dumps)

## What must not be stored in the repository

- Runtime database files / Docker volume contents
- Generated logs
- Local secrets (`.env`, API keys, passwords)
- Broker or exchange credentials
- Database backup archives (`backups/*.sql`)
- Temporary reports and RC command logs (`rc1_*.txt`, `rc_*.txt`)
- Frontend build artifacts (`.next/`, `out/`)
- Caches (`.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`)
- Dependency directories (`.venv/`, `node_modules/`)
- Personal financial information or SSN/KYC material

## Responsibility table

| Component | Owner | Purpose | Source of truth | How started | How validated | Where data lives |
| --- | --- | --- | --- | --- | --- | --- |
| API | Founder / engineers | Control plane HTTP API | `apps/api` on GitHub | `uvicorn` via docs/scripts | pytest, ruff, mypy, `/health` `/ready` | Postgres (orders, audit, config) |
| EOC frontend | Founder / engineers | Operator UI | `apps/eoc` on GitHub | `pnpm eoc:dev` / `pnpm eoc:build` | typecheck, build, CI | Browser session cookies only |
| Workers | Founder / engineers | Health supervisor + ops crons | `workers/health_supervisor` | Compose profile `workers` | heartbeats, ops events | Postgres + Redis |
| Scheduler | Same worker process | Cron host metrics / daily paper reports | ARQ cron in worker | worker up | operational events | Postgres |
| Database | Operator | System of record | Alembic migrations | Compose `postgres` | `/ready`, migrations, backup validate | Docker volume `argus_postgres_data` |
| Queue | Operator | ARQ / Redis coordination | Compose `redis` | Compose `redis` | `/ready` redis | Docker volume `argus_redis_data` |
| Market data | Engineers | Observation only | `apps/api` market module | API ingest endpoints | market tests | Postgres |
| Internal paper provider | Platform | Default execution | `internal_paper` registry seed | automatic default | paper E2E, provider list | Process memory + Postgres SoR |
| Reports | Operator | Paper daily / treasury reports | API + EOC | generate endpoints / cron | content hash, disclaimers | Postgres |
| Backups | Operator | Disaster recovery | `scripts/backup-db.*` | backup scripts | `validate-db-restore` | Local `backups/` (ignored) |
| CI | GitHub Actions | PR/push verification | `.github/workflows/ci.yml` | push/PR | Actions run | Ephemeral CI runners |
| Releases | Founder | Approved product states | tags + `docs/releases/` | tag after merge | RC readiness docs | GitHub |

## Operating principles

1. Pull and review on GitHub — not from chat transcripts.
2. Operate paper trading through scripts + EOC while Cursor is closed.
3. Important decisions belong in ADRs, runbooks, or release evidence.
4. Live trading remains **disabled and not certified**.
5. Default execution provider is **`internal_paper`**. No broker account required for paper mode.

## Related documents

- [Development workflow](development/DEVELOPMENT_WORKFLOW.md)
- [Operations model](operations/ARGUS_OPERATIONS_MODEL.md)
- [Release management](releases/RELEASE_MANAGEMENT.md)
- [Phase 15 handoff](operations/PHASE15_HANDOFF_STATUS.md)
- [RC1 readiness](../ARGUS_RC1_READINESS.md)
