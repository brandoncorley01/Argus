from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_SECRET_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|access[_-]?key|"
    r"authorization|cookie|credential|connection[_-]?string|bearer)",
    re.IGNORECASE,
)
_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)(-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"sk_live_|sk_test_|ghp_[A-Za-z0-9]{20,}|xox[baprs]-)"
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


def validate_payload_for_schema(schema_identifier: str, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise PayloadValidationError("payload must be a JSON object")
    assert_no_secrets(payload)

    known = {
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
    if schema_identifier not in known:
        raise PayloadValidationError(f"unknown schema_identifier: {schema_identifier}")

    # Minimal structural rule: optional "metadata" must be object if present.
    if "metadata" in payload and not isinstance(payload["metadata"], dict):
        raise PayloadValidationError("metadata must be an object when provided")
