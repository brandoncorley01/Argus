# Backups

SQL dumps and restore archives are **local operator artifacts**.

- Created by `scripts/backup-db.ps1` / `.sh` or `scripts/backup/backup-paper.ps1`
- Integrity verified by `scripts/backup/verify-backup.ps1` (SHA256 + size)
- Table presence validated by `scripts/validate-db-restore.ps1`
- Restored only with explicit confirmation (`RESTORE-LOCAL-DB` or `-Force`)

Each successful dump also writes:

- `argus_postgres_<stamp>.meta.json` — size, sha256, completed_at
- `LAST_OK.json` — pointer to the latest verified backup (read by System Health)

**Never commit `*.sql` / `*.meta.json` / `LAST_OK.json` backup files.** This directory is gitignored except for this README.

Default dump path pattern: `backups/argus_postgres_YYYYMMDD_HHMMSS.sql`
