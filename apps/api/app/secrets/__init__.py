"""Credential reference resolution (Phase 13 Micro-Live Institution).

This package NEVER returns, logs, or persists secret values. Only presence
(boolean) is ever exposed, and only by reference name (e.g. an environment
variable name), never by value. See ADR-029.
"""

from __future__ import annotations

from app.secrets.contracts import SecretReferenceStatus, SecretsProvider
from app.secrets.env_provider import EnvSecretsProvider

__all__ = ["SecretReferenceStatus", "SecretsProvider", "EnvSecretsProvider"]
