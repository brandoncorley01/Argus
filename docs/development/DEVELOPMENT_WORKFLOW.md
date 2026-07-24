# Development Workflow

GitHub is the source of truth. Cursor is an optional editor/agent client.

Cursor conversations are **not** project records. Important decisions must be written into repository documentation (ADRs, runbooks, release evidence).

## Verified workflow

1. Pull the latest `main` (or the authorized integration branch if `main` has not yet received the Phase 8–RC1 stack).
2. Create a focused feature or fix branch (`fix/…`, `docs/…`, `ops/…`).
3. Make **bounded** changes with one defined outcome.
4. Run repository-native checks (see below).
5. Commit with a clear message describing **why**.
6. Push the branch to GitHub.
7. Open a pull request.
8. Wait for CI (`.github/workflows/ci.yml`).
9. Review evidence in the PR and in `docs/releases/` when releasing.
10. Merge only after Founder/reviewer approval and green required checks.

## Repository-native checks (API)

```powershell
cd apps\api
python -m uv sync
python -m uv run ruff check app tests
python -m uv run mypy app
python -m uv run pytest
```

## Repository-native checks (EOC)

```powershell
pnpm install
pnpm eoc:typecheck
pnpm eoc:build
```

## Paper smoke (optional but recommended for execution-path changes)

```powershell
apps\api\.venv\Scripts\python.exe scripts\rc_e2e_paper_validation.py
```

Or: `.\scripts\validation\verify-argus.ps1`

## Explicit rules

- Do **not** use large multi-phase prompts for routine work.
- Each implementation batch should have **one** defined outcome.
- Do **not** enable live execution or add broker credentials in development.
- Do **not** commit `.env`, backups, or secrets.
- Prefer small PRs that CI can verify quickly.

## Configuration for development

Copy `.env.example` → `.env` for local infra.

For controlled paper-oriented local settings, see `.env.paper.example` (still uses `internal_paper`; no live keys).

CI uses disposable Postgres/Redis as defined in `.github/workflows/ci.yml` (see also `.env.ci.example` for documented variable names).
