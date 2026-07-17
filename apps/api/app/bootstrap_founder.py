"""Bootstrap the initial Founder account.

Requires environment variables (never hardcode credentials):

  ARGUS_BOOTSTRAP_USERNAME
  ARGUS_BOOTSTRAP_PASSWORD
  ARGUS_BOOTSTRAP_EMAIL   (optional)

Usage (from apps/api):

  python -m uv run python -m app.bootstrap_founder
"""

from __future__ import annotations

import os
import sys

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
from app.services.auth_service import AuthError, AuthService


def main() -> int:
    username = os.environ.get("ARGUS_BOOTSTRAP_USERNAME", "").strip()
    password = os.environ.get("ARGUS_BOOTSTRAP_PASSWORD", "")
    email = os.environ.get("ARGUS_BOOTSTRAP_EMAIL", "").strip() or None

    if not username or not password:
        print(
            "Refusing bootstrap: set ARGUS_BOOTSTRAP_USERNAME and ARGUS_BOOTSTRAP_PASSWORD.",
            file=sys.stderr,
        )
        return 2
    if len(password) < 12:
        print("Refusing bootstrap: password must be at least 12 characters.", file=sys.stderr)
        return 2

    clear_settings_cache()
    reset_engine()
    get_settings()
    session = get_session_factory()()
    try:
        auth = AuthService(session)
        user = auth.bootstrap_founder(username=username, password=password, email=email)
    except AuthError as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()
        reset_engine()
        clear_settings_cache()

    print(f"Founder bootstrap complete for user_id={user.id} username={user.username}")
    print("Unset ARGUS_BOOTSTRAP_PASSWORD from your shell after use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
