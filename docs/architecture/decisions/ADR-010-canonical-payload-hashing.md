# ADR-010: Canonical JSON payload hashing

- Status: Accepted
- Date: 2026-07-16
- Deciders: Founder (Phase 6 defaults)

## Context

Active configuration and policy must be integrity-checked before activation. Ad-hoc JSON serialization would produce unstable hashes.

## Decision

1. Canonicalize payloads with `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
2. Hash with SHA-256 hex digest stored in `payload_hash`.
3. Reject creating a new version whose hash matches the latest version for that document.
4. Block activation when stored content does not re-hash to `payload_hash` (audit `*.integrity.failed`).

## Consequences

- Key order in API requests does not affect identity.
- Integrity failures fail closed and do not activate: on hash mismatch the
  version's `status` is left completely untouched (no supersede, no
  activate), an `*.integrity.failed` audit event is attempted, and
  `GovernanceError` is raised regardless of whether that audit write itself
  succeeds (see ADR-011 for the fail-closed audit-write contract). The prior
  `ACTIVE` version, if any, is never touched during a failed activation
  attempt.

## Addendum (2026-07-17 remediation): baseline validation, not schema validation

`validate_version_payload` (formerly named `validate_payload_for_schema`) was
renamed because its original name overstated what it does: it does not run a
per-field JSON Schema check against `schema_identifier`. It performs a
fail-closed baseline only -- structural sanity, the ADR-012 secrets denylist,
and a `schema_identifier` allowlist check. See the function's docstring in
`payload_integrity.py` for the exact ordered checks.
