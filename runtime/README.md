# Runtime

This directory documents **where runtime state lives**. It does not store databases or logs in Git.

## Local paper / development runtime

| Resource | Location |
| --- | --- |
| Postgres data | Docker volume `argus_postgres_data` |
| Redis data | Docker volume `argus_redis_data` |
| API process | Local `uvicorn` (not containerized by default) |
| EOC process | Local `pnpm eoc:dev` / `next start` |
| Worker | Compose service `health_supervisor` (profile `workers`) |
| Secrets | Repo-root `.env` (gitignored) |

## Rules

- Do not commit runtime files here.
- Prefer `.\scripts\operations\status-paper.ps1` for status.
- Backups go to `../backups/` (gitignored archives).

Start paper stack: `.\scripts\operations\start-paper.ps1`
