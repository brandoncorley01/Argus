# Release Management

## Branch strategy

- `main` — Founder-approved integration line (may lag stacked phase branches until merge).
- Feature / phase / separation branches — short-lived; open PRs into `main`.
- Do not rewrite published release tags.

## Pull requests

1. Focused scope; one primary outcome.
2. CI must run (`.github/workflows/ci.yml`).
3. Describe risk to paper trading if any.
4. Founder approval required for merge to `main`.

## CI requirements

Minimum gates (as of RC1 finalization):

- API: `uv sync`, Alembic upgrade, ruff, mypy, pytest
- EOC: pnpm install, typecheck, production build

No live credentials in CI.

## Release-candidate criteria

See `docs/governance/ARGUS_RELEASE_CERTIFICATION_FRAMEWORK.md` and Independent Engineering Review framework.

For controlled paper RC:

- Green required checks
- Paper E2E pass
- `internal_paper` default
- Live execution disabled
- Durable evidence under `docs/releases/`

## Version tagging

```powershell
git checkout main
git pull
git tag -a vX.Y.Z-rcN -m "message"
git push origin vX.Y.Z-rcN
```

Application version (git tag / package metadata) is distinct from operating data (Postgres volumes / backups).

## Rollback

1. Redeploy prior known-good tag.
2. Restore DB only with explicit operator confirmation (`restore-db` scripts).
3. Re-validate `/ready`, System Health / paper providers, and a paper smoke test.

## Historical evidence (do not rewrite)

| Artifact | Status |
| --- | --- |
| `docs/releases/ARGUS_RC1_EVIDENCE.md` | Intact — preserve |
| `ARGUS_RC1_READINESS.md` | Intact — preserve |
| `ARGUS_DEFECT_REGISTER.md` | Intact — preserve |
| Phase 11–14 IER / certification docs | Intact — preserve |

Append new release notes; do not overwrite prior RC evidence.
