# Infrastructure scripts

Scripts for PostgreSQL 16 and Redis 7 lifecycle via Docker Compose.

| Script | Action |
| --- | --- |
| `infra-up` | Start infrastructure detached |
| `infra-status` | Show compose status / health |
| `infra-logs` | Tail service logs |
| `infra-stop` | Stop containers (keep containers/volumes) |
| `infra-down` | Remove containers/networks; **keep named volumes** |
| `infra-reset` | Destroy containers **and** volumes (explicit confirmation) |
| `migrate-up` | Alembic upgrade head (`apps/api`) |
| `backup-db` | `pg_dump` via docker to `backups/` (password not printed) |
| `restore-db` | Drop/recreate local DB and restore dump (confirmation or `-Force`/`--force`) |
| `validate-db-restore` | Count-check institutional tables after restore |

Use `.ps1` on Windows PowerShell and `.sh` on Unix shells.
