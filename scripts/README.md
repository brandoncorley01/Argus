# Scripts

Operator entry points for Argus. Prefer wrappers under `operations/`, `validation/`, and `backup/` for daily work. Existing `infra-*.ps1` scripts remain authoritative implementations (not moved).

## Recommended entry points

| Wrapper | Action |
| --- | --- |
| `operations/start-paper.ps1` | Infra up + migrate; prints API/EOC start commands |
| `operations/stop-paper.ps1` | Infra stop (volumes preserved) |
| `operations/status-paper.ps1` | Compose status + API health/ready probe |
| `operations/generate-daily-report.ps1` | Points to paper/ops report APIs |
| `validation/verify-argus.ps1` | ruff, mypy, pytest, EOC typecheck/build, paper E2E |
| `backup/backup-paper.ps1` | backup-db + validate-db-restore |

## Core implementations (unchanged locations)

| Script | Action |
| --- | --- |
| `infra-up` / `infra-stop` / `infra-status` / `infra-down` / `infra-reset` / `infra-logs` | Compose lifecycle |
| `migrate-up` | Alembic upgrade head |
| `backup-db` / `restore-db` / `validate-db-restore` | Postgres dump/restore |
| `rc_e2e_paper_validation.py` | Deterministic paper E2E |

Use `.ps1` on Windows PowerShell. Matching `.sh` exists for many infra scripts.
