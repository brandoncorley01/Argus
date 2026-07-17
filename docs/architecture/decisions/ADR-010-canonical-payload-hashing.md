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
- Integrity failures fail closed and do not activate.
