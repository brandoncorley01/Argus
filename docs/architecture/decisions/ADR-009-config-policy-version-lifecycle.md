# ADR-009: Configuration and policy version lifecycle

- Status: Accepted
- Date: 2026-07-16
- Deciders: Founder (Phase 6 defaults)

## Context

Phase 3 stored config/policy versions with a boolean `is_active` flag only. Institutional governance requires review, approval, rejection, retirement, and a single active version without silent mutation of published payloads.

## Decision

1. Use exact lifecycle statuses: `DRAFT`, `UNDER_REVIEW`, `APPROVED`, `ACTIVE`, `SUPERSEDED`, `REJECTED`, `RETIRED`.
2. Allow only the documented transitions in `version_lifecycle.py`.
3. Permit payload mutation only while status is `DRAFT`.
4. Enforce one `ACTIVE` row per document via partial unique index on `status = 'ACTIVE'`.

## Consequences

- Activation requires prior approval.
- Rejected and superseded versions remain immutable historical records.
- Operators may draft/submit non-governance-critical configuration; Founder controls approve/activate/retire.
