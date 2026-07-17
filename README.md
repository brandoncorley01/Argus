# Argus

Private institutional crypto research and paper-trading system.

**Product version:** `0.1.0-foundation`  
**Current scope:** Version 0.1 Foundation — control plane and governance baseline only.  
**Live trading:** Disabled. `MICRO_LIVE` and `NORMAL_LIVE` operating modes are permanently locked in v0.1.

## Permanent engineering rules

See [`AGENTS.md`](AGENTS.md). Capital preservation comes before profit. Do not bypass risk controls. Prefer safe failure. Never commit secrets.

## Repository layout

| Path | Purpose |
| --- | --- |
| `apps/` | Future application runtimes (API, Executive Operations Center). Not scaffolded in Phase 0/1. |
| `workers/` | Future ARQ workers. Not scaffolded yet. |
| `packages/` | Future shared libraries. Not scaffolded yet. |
| `infrastructure/` | Local infrastructure documentation and Compose-related notes. |
| `scripts/` | Operator scripts for infrastructure lifecycle. |
| `tests/` | Future automated tests. |
| `docs/` | Durable institutional documentation and ADRs. |

## Prerequisites

- Git
- Docker Engine + Docker Compose V2 (required for Phase 1 infrastructure)
- Later phases: Python 3.12+, Node.js LTS, [uv](https://github.com/astral-sh/uv), [pnpm](https://pnpm.io/)

## Local infrastructure (Phase 1)

1. Copy `.env.example` to `.env` and set a strong `POSTGRES_PASSWORD`.
2. Start Postgres 16 and Redis 7:

```powershell
.\scripts\infra-up.ps1
```

```bash
./scripts/infra-up.sh
```

3. Check status, logs, stop, or reset using the scripts in `scripts/` (see [`infrastructure/README.md`](infrastructure/README.md)).

## Documentation

- [`docs/README.md`](docs/README.md) — documentation map
- [`docs/foundation/INSTITUTIONAL_IDENTITY.md`](docs/foundation/INSTITUTIONAL_IDENTITY.md) — institutional identity
- [`docs/governance/`](docs/governance/) — maturity model and feature governance
- [`docs/architecture/decisions/`](docs/architecture/decisions/) — Architecture Decision Records

## Out of scope (v0.1)

Exchange integrations, live trading, leverage, margin, futures, options, short selling, withdrawals, fabricated financial performance data, and decorative or misleading dashboards.
