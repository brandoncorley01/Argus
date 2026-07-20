"""Environment-variable-backed SecretsProvider (presence checks only)."""

from __future__ import annotations

import os
from datetime import UTC, datetime

from app.secrets.contracts import SecretReferenceStatus, SecretsProvider


class EnvSecretsProvider(SecretsProvider):
    """Resolves credential presence by reading ``os.environ``.

    ``get_reference_status`` never returns, logs, or persists the value —
    only whether a non-empty value is present for the given reference name.
    No provider in this codebase requires this to return ``present=True`` to
    remain operational; absence of every referenced credential keeps the
    system in ``PAPER_ONLY`` (see ``live_activation_service``).
    """

    def get_reference_status(self, ref_name: str) -> SecretReferenceStatus:
        value = os.environ.get(ref_name)
        present = value is not None and value.strip() != ""
        return SecretReferenceStatus(
            ref_name=ref_name, present=present, checked_at=datetime.now(UTC)
        )
