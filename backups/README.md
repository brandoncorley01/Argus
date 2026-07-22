# Backups

SQL dumps and restore archives are **local operator artifacts**.

- Created by `scripts/backup-db.ps1` / `.sh` or `scripts/backup/backup-paper.ps1`
- Validated by `scripts/validate-db-restore.ps1`
- Restored only with explicit confirmation (`RESTORE-LOCAL-DB` or `-Force`)

**Never commit `*.sql` backup files.** This directory is gitignored except for this README (see `.gitignore` exception if configured).

Default dump path pattern: `backups/argus_postgres_YYYYMMDD_HHMMSS.sql`
