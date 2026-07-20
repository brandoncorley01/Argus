"""Secrets provider contract — presence-only, never value-returning.

Institutional rule (AGENTS.md, ADR-029): Argus never stores, logs, or
returns credential VALUES anywhere in this codebase — only references
(e.g. environment variable names) and a boolean presence flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SecretReferenceStatus:
    """Presence-only status for a named credential reference.

    ``ref_name`` is a reference (e.g. an environment variable name), never a
    value. ``present`` is a boolean; no secret material is included anywhere
    on this object.
    """

    ref_name: str
    present: bool
    checked_at: datetime


@runtime_checkable
class SecretsProvider(Protocol):
    """Institutional boundary for credential presence checks.

    Implementations must never return, log, or persist the underlying secret
    value. Only ``get_reference_status`` is exposed, and it returns a boolean
    presence flag keyed by reference name.
    """

    def get_reference_status(self, ref_name: str) -> SecretReferenceStatus:
        """Return presence status for ``ref_name``. Never returns the value."""
        ...
