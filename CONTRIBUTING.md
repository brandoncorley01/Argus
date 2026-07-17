# Contributing to Argus

Argus is a private institutional system. Changes must respect [`AGENTS.md`](AGENTS.md) and Founder-approved Architecture Decision Records.

## Before you change code

1. Read `AGENTS.md` and the relevant docs under `docs/`.
2. Confirm the change is in the approved phase scope.
3. For major technical decisions, draft or update an ADR under `docs/architecture/decisions/` before implementing.
4. Explain significant architectural deviations before implementing them.

## Hard prohibitions (v0.1)

- Do not implement live trading or unlock `MICRO_LIVE` / `NORMAL_LIVE`.
- Do not add exchange integrations, live credentials, leverage, margin, futures, options, short selling, or withdrawals.
- Do not fabricate financial data or claim strategy profitability without validation evidence.
- Do not bypass audit, risk controls, or operating-mode locks.
- Do not commit secrets, `.env` files, or credentials.
- Do not add fake metrics, decorative controls, or misleading dashboard pages.

## Local workflow

1. Copy `.env.example` → `.env` (never commit `.env`).
2. Use infrastructure scripts under `scripts/` for Postgres/Redis.
3. Run relevant tests after making changes (once the test suite exists).
4. Prefer safe failure over continuing with uncertain system state.

## Roles

RBAC roles for v0.1: `FOUNDER`, `OPERATOR`, `VIEWER`. Privilege changes must be auditable.

## Pull requests / reviews

- Keep diffs scoped to the approved phase.
- Critical institutional mutations must remain fail-closed when audit recording is unavailable (ADR-006).
- CI will use GitHub Actions once introduced in a later phase.
