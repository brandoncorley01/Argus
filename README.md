# Argus

Private institutional crypto research and **controlled paper-trading** system.

**Product channel:** Controlled paper operation (RC1 evidence at commit documented in `docs/releases/ARGUS_RC1_EVIDENCE.md`)  
**Certified execution provider (paper):** `internal_paper`  
**Live trading:** Disabled and **not certified**. No reachable path to live execution without a future Founder-authorized phase.  
**Real funds:** Not used and not required for paper mode.  
**Broker / exchange accounts:** Not required for paper mode. No SSN, KYC, or paid API required for local paper operation.

Capital preservation comes before profit. See [`AGENTS.md`](AGENTS.md).

## What is verified

On the Phase 14 tip with RC1 finalization evidence:

- Local Postgres + Redis via Docker Compose
- Alembic migrations to institutional schema head
- FastAPI control plane (`/health`, `/ready`, paper/treasury/strategy/market APIs)
- Automated API suite (pytest), ruff, mypy
- Executive Operations Center typecheck and production build
- Deterministic paper buy → fill → position → cash decrease
- Risk block, kill switch, short-sale reject
- External transfer execute forbidden; micro-live ACTIVE denied
- Local DB backup / restore scripts with table validation

## What is not certified

- Live trading, live brokers, testnet funding, or real-money movement
- Multi-replica paper provider memory consistency (single-process local paper assumed)
- Interactive browser UI walkthrough as a formal gate (EOC builds; API E2E is the paper gate)
- Production SaaS deployment

## Repository layout

| Path | Purpose |
| --- | --- |
| `apps/api` | FastAPI control plane |
| `apps/eoc` | Executive Operations Center (Next.js) |
| `workers/health_supervisor` | ARQ health supervisor worker |
| `scripts/` | Infra, migrate, backup/restore |
| `docs/` | Architecture, ADRs, operations, releases |
| `.github/workflows/ci.yml` | Minimal CI (API + EOC) |

## Prerequisites

- Git
- Docker Engine + Docker Compose V2
- Python 3.12+ and [uv](https://github.com/astral-sh/uv) (API)
- Node.js LTS and [pnpm](https://pnpm.io/) (EOC)

## Local setup (verified commands)

See [`docs/ARGUS_HEADQUARTERS.md`](docs/ARGUS_HEADQUARTERS.md) for how Argus runs independently of Cursor.

1. Copy `.env.example` (or `.env.paper.example` for paper-oriented local settings) to `.env` and set a strong `POSTGRES_PASSWORD`.
2. Start paper infra:

```powershell
.\scripts\operations\start-paper.ps1
.\scripts\operations\status-paper.ps1
```

Or the underlying scripts:

```powershell
.\scripts\infra-up.ps1
.\scripts\infra-status.ps1
.\scripts\migrate-up.ps1
```

3. API (from `apps/api`):

```powershell
cd apps\api
python -m uv sync
python -m uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

4. EOC:

```powershell
pnpm install
$env:ARGUS_API_BASE_URL = "http://127.0.0.1:8000"
pnpm eoc:dev
```

## Tests (API)

```powershell
.\scripts\validation\verify-argus.ps1
```

Or manually from `apps/api`:

```powershell
python -m uv run pytest
python -m uv run ruff check app tests
python -m uv run mypy app
```

## Backup / restore (local)

```powershell
.\scripts\backup-db.ps1
.\scripts\validate-db-restore.ps1
# Destructive restore (confirmation required unless -Force):
.\scripts\restore-db.ps1 .\backups\argus_postgres_YYYYMMDD_HHMMSS.sql
```

Never commit `.env` or `backups/*.sql` containing operational data you consider sensitive.

## Documentation

- [`docs/README.md`](docs/README.md) — documentation map
- [`ARGUS_RC1_READINESS.md`](ARGUS_RC1_READINESS.md) — RC1 readiness verdict
- [`docs/releases/ARGUS_RC1_EVIDENCE.md`](docs/releases/ARGUS_RC1_EVIDENCE.md) — durable RC1 evidence
- [`docs/governance/`](docs/governance/) — constitution and certification frameworks

## Out of scope (current channel)

Exchange live credentials, funded brokerage accounts, leverage, margin, futures, options, short selling, withdrawals, fabricated performance claims, and decorative metrics.
