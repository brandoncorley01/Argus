from __future__ import annotations

import hashlib
import json
import re
from typing import Any

# Key names that must never appear in a versioned configuration/policy
# payload, regardless of nesting depth. This is a heuristic denylist, not a
# secrets-detection guarantee -- see `validate_version_payload` docstring.
_SECRET_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|access[_-]?key|"
    r"authorization|cookie|credential|connection[_-]?string|bearer|client[_-]?secret|"
    r"refresh[_-]?token|db[_-]?password)",
    re.IGNORECASE,
)
# String value patterns that look like live secret material even when the
# surrounding key name does not match `_SECRET_KEY_PATTERN`.
_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)(-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"sk_live_|sk_test_|ghp_[A-Za-z0-9]{20,}|xox[baprs]-|"
    r"bearer\s+[A-Za-z0-9._-]{16,}|"
    r"(?:postgres(?:ql)?|mysql|redis|mongodb(?:\+srv)?)://[^\s\"']*:[^\s\"'@]+@)"
)


class PayloadValidationError(ValueError):
    """Raised when a configuration/policy payload is invalid or unsafe."""


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def verify_payload_hash(payload: dict[str, Any], expected_hash: str) -> bool:
    return hash_payload(payload) == expected_hash


def find_secret_violations(payload: Any, path: str = "$") -> list[str]:
    """Recursively scan a JSON-like payload for credential-like keys/values.

    Walks dicts and lists at any depth (there is no depth limit) so a secret
    nested inside an arbitrarily deep structure is still caught. Returns a
    list of human-readable violation descriptions; an empty list means clean.
    """
    violations: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_path = f"{path}.{key}"
            if _SECRET_KEY_PATTERN.search(str(key)):
                violations.append(f"forbidden key at {key_path}")
            violations.extend(find_secret_violations(value, key_path))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            violations.extend(find_secret_violations(value, f"{path}[{index}]"))
    elif isinstance(payload, str):
        if _SECRET_VALUE_PATTERN.search(payload):
            violations.append(f"forbidden secret pattern at {path}")
    return violations


def assert_no_secrets(payload: dict[str, Any]) -> None:
    violations = find_secret_violations(payload)
    if violations:
        raise PayloadValidationError("; ".join(violations[:5]))


_KNOWN_SCHEMA_IDENTIFIERS = frozenset(
    {
        "config.generic.v1",
        "config.system_runtime.v1",
        "config.authentication_security.v1",
        "config.audit_policy.v1",
        "config.feature_controls.v1",
        "policy.generic.v1",
        "policy.operating.v1",
        "policy.governance.v1",
        "policy.treasury.v1",
        "policy.research.v1",
        "policy.security.v1",
        "policy.audit.v1",
        "policy.authentication.v1",
        "policy.feature_governance.v1",
        "policy.constitution.v1",
    }
)


def validate_version_payload(schema_identifier: str, payload: dict[str, Any]) -> None:
    """Baseline, fail-closed payload validation for a config/policy version.

    This function intentionally does NOT perform full JSON-Schema validation
    against `schema_identifier` -- there is no per-field schema engine here.
    It performs three fail-closed checks, in order, and raises
    `PayloadValidationError` on the first failure:

    1. Structural baseline: `payload` must be a JSON object, and if it
       carries an optional `metadata` field, that field must itself be an
       object.
    2. Secrets denylist: recursively rejects credential-like keys or
       secret-shaped string values anywhere in the payload (see
       `assert_no_secrets` / `find_secret_violations`), so secrets are never
       persisted into the auditable, versioned system of record.
    3. Schema-identifier allowlist: `schema_identifier` must be one of the
       registered identifiers in `_KNOWN_SCHEMA_IDENTIFIERS`; unknown
       identifiers are rejected rather than silently accepted.

    Callers that need real per-field schema enforcement for a given
    `schema_identifier` must implement it separately (e.g. a JSON Schema
    validator keyed by identifier) -- this function is a safety baseline,
    not a substitute for that.
    """
    if not isinstance(payload, dict):
        raise PayloadValidationError("payload must be a JSON object")

    # Minimal structural rule: optional "metadata" must be object if present.
    if "metadata" in payload and not isinstance(payload["metadata"], dict):
        raise PayloadValidationError("metadata must be an object when provided")

    assert_no_secrets(payload)

    if schema_identifier not in _KNOWN_SCHEMA_IDENTIFIERS:
        raise PayloadValidationError(f"unknown schema_identifier: {schema_identifier}")
