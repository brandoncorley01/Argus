"""Ensure Paper Training Lab tables exist after alembic upgrade.

alembic_version can be stamped at head while paper_training_settings is
missing (interrupted migrate / prior stamp). Re-apply that revision when needed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
PARENT_REV = "d6e7f8a9b0c1"


def _run_alembic(*args: str) -> None:
    # Match migrate-up.ps1; fall back when `python -m uv` is unavailable.
    candidates = [
        [sys.executable, "-m", "uv", "run", "alembic", *args],
        [sys.executable, "-m", "alembic", *args],
        ["alembic", *args],
    ]
    for cmd in candidates:
        completed = subprocess.run(
            cmd,
            cwd=API_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            if completed.stdout:
                print(completed.stdout, end="")
            return
        err = (completed.stderr or "") + (completed.stdout or "")
        if "No module named" in err or "not found" in err.lower():
            continue
        sys.stderr.write(err)
        raise SystemExit(completed.returncode)
    sys.stderr.write("Could not run alembic (uv/alembic unavailable).\n")
    raise SystemExit(1)


def _training_settings_missing() -> bool:
    sys.path.insert(0, str(API_ROOT))
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    from app.core.settings import clear_settings_cache, get_settings
    from app.db.session import get_session_factory, reset_engine

    clear_settings_cache()
    reset_engine()
    get_settings()
    db = get_session_factory()()
    try:
        missing = db.execute(
            text(
                "SELECT NOT EXISTS ("
                " SELECT 1 FROM information_schema.tables"
                " WHERE table_schema = 'public'"
                " AND table_name = 'paper_training_settings'"
                ")"
            )
        ).scalar()
        return bool(missing)
    except OperationalError as exc:
        sys.stderr.write(
            "Could not connect to PostgreSQL while verifying Paper Training schema.\n"
            "Open Docker Desktop, confirm postgres is up (docker compose ps),\n"
            "check DATABASE_URL / POSTGRES_PASSWORD in .env, then Start Argus again.\n"
            f"Detail: {exc.orig if getattr(exc, 'orig', None) else exc}\n"
        )
        raise SystemExit(2) from exc
    finally:
        db.close()
        reset_engine()
        clear_settings_cache()


def main() -> int:
    if not _training_settings_missing():
        print("Paper Training schema OK.")
        return 0

    print(
        "paper_training_settings missing while alembic at head - repairing..."
    )
    _run_alembic("stamp", PARENT_REV)
    _run_alembic("upgrade", "head")
    if _training_settings_missing():
        print("ERROR: paper_training_settings still missing after repair.")
        return 1
    print("Paper Training schema repaired.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
