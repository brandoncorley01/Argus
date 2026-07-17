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
- Draft/submit authority is further scoped per-document by `draft_authority`
  (see ADR-013's sibling remediation notes below); Operator drafting is opt-in
  per document, not a blanket grant.
- Immutability of non-`DRAFT` versions is enforced at the database level via
  triggers, not just in application code (see ADR-013).

## Addendum (2026-07-17 remediation): legacy backfill maps to SUPERSEDED

The original migration backfill mapped legacy `is_active = false` rows to
`DRAFT`. That was incorrect: those rows were finalized historical versions
under the old boolean-only schema, not documents mid-review. They are now
backfilled to `SUPERSEDED` (with `superseded_at` set to the row's original
`created_at` as a best-effort timestamp), and are therefore immediately
protected by the ADR-013 immutability trigger after migration -- they are
never editable as `DRAFT` again.
