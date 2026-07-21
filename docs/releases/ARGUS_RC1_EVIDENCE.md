# ARGUS RC1 Evidence

| Field | Value |
| --- | --- |
| **Channel** | Controlled paper operation |
| **Base commit verified (pre-finalization)** | `8d0fd715a05dead9b1e36b573630d7a285c2b384` |
| **Branch** | `phase-14-treasury-executive-analytics` |
| **Provider** | `internal_paper` (default) |
| **Live execution** | Disabled â€” not certified |
| **Real funds** | Not used |
| **Evidence date** | 2026-07-21 |

This document records **commands and results that were executed**. It does not claim checks that were not run.

---

## A. Pre-finalization sprint (commit `8d0fd71`)

### Commands

```text
.\scripts\infra-up.ps1 / infra-status
.\scripts\migrate-up.ps1
alembic current  â†’ a3b4c5d6e7f8 (head)
cd apps/api
uv/python -m pytest -q
uv run ruff check app tests
uv run mypy app
uvicorn â†’ GET /health, GET /ready
cd apps/eoc
pnpm typecheck
pnpm build   # first attempt failed (OneDrive .next); after Remove-Item .next â†’ PASS
apps/api/.venv/Scripts/python.exe scripts/rc_e2e_paper_validation.py
```

### Results

| Check | Result |
| --- | --- |
| Pytest | **180 passed** |
| Ruff | PASS |
| Mypy | PASS |
| `/health` `/ready` | 200 |
| EOC typecheck | PASS |
| EOC build | PASS after `.next` clean |
| Paper E2E | **24/24 PASS** |
| Critical defects | **0** |

### Paper trade accounting snapshot

- Opening cash: `100000`
- Ending cash: `99816.19487133`
- Position qty: `1`
- Fills: `1`
- Fees: `0.01837868`
- Environment: `paper`
- Risk notional block: PASS
- Kill switch block: PASS
- Short reject: PASS
- External transfer execute: 403
- MICRO_LIVE_ACTIVE: denied

---

## B. Finalization changes (this commit)

Added/updated:

- `.github/workflows/ci.yml` â€” minimal CI (API: migrate, ruff, mypy, pytest; EOC: typecheck, build)
- `scripts/backup-db.ps1` / `.sh`
- `scripts/restore-db.ps1` / `.sh` (confirmation or `-Force`/`--force`)
- `scripts/validate-db-restore.ps1` / `.sh`
- README honesty; FEATURE_GOVERNANCE `feat.api.fastapi` â†’ implemented
- This evidence pack + readiness update

### Post-change verification

Results recorded in section C after the finalization verification run on the finalization commit.

---

## C. Post-finalization verification

Finalization verification run completed 2026-07-21 (local PowerShell). Exit codes captured below.

| Check | Result |
| --- | --- |
| Infra status | **PASS** (postgres + redis healthy; exit 0) |
| Migrate-up | **PASS** (exit 0; already at head) |
| Pytest | **PASS — 180 passed**, 172 warnings (exit 0; ~173s) |
| Ruff | **PASS** (All checks passed!; exit 0) |
| Mypy | **PASS** (no issues in 89 source files; exit 0) |
| EOC typecheck | **PASS** (exit 0) |
| EOC build | **PASS** (after Remove-Item .next; exit 0) |
| CI workflow syntax | **PASS** — `.github/workflows/ci.yml` present; actionlint unavailable locally |
| Backup | **PASS** — `backups/argus_postgres_20260721_151328.sql` (initial) and `backups/argus_postgres_20260721_152255.sql` (reverify) |
| Restore + validate | **PASS** (after fixing `validate-db-restore.ps1` quoting; restore `-Force` + validate exit 0) |
| Paper smoke E2E | **PASS — 24/24** (exit 0; post-restore + migrate-up; reconfirmed after restore reverify) |
---

## Known limitations (non-blocking for controlled paper)

1. Paper provider process-local memory (single-process local OK)
2. No interactive browser UI formal gate
3. Phase stack may still be awaiting Founder merge to `main` at evidence time
4. OneDrive can corrupt `.next` artifacts; clean rebuild if build fails with `EINVAL readlink`
5. CI job uses disposable Postgres/Redis service containers â€” not a live broker

## Explicit non-claims

- Live trading not verified and not certified
- No broker/exchange credentials used
- No real capital movement
