# ADR-011: Atomic configuration and policy activation

- Status: Accepted
- Date: 2026-07-16
- Deciders: Founder (Phase 6 defaults)

## Context

Activating a version must supersede the previous active version without leaving two ACTIVE rows or an unaudited switch.

## Decision

1. Take a row lock (`SELECT ... FOR UPDATE`) on the parent document at the
   start of activation, before re-reading the target version. Every other
   mutating operation on the same document (creating a new version,
   activating a version) also locks the document row first, so all of them
   serialize on this single lock -- there is no path that mutates a
   document's versions without holding it.
2. Under the document lock, re-fetch and row-lock the target version
   (`SELECT ... FOR UPDATE`), and re-check that its status is still
   `APPROVED` and that its content still re-hashes to `payload_hash`. Both
   the document lock and the version row lock are needed: the document lock
   prevents a concurrent second activation from racing on which version
   becomes `ACTIVE`; the version row lock prevents a concurrent draft-update
   or transition from mutating the specific row being activated.
3. Row-lock the current `ACTIVE` version (if any) before superseding it.
4. Supersede any existing `ACTIVE` version, activate the approved version, and
   write audit events in one commit.
5. On mapped policy kinds (`constitution`, `operating`, `governance`,
   `treasury`, `research`), update the corresponding Institutional Identity
   string pointer to `{document_key}@{version_number}` (see ADR-014). If no
   Institutional Identity record exists, the entire activation is aborted
   fail-closed before any row is mutated (see ADR-014).
6. If audit persistence fails at any commit point, roll back the entire
   activation (fail-closed) and raise; no partial state (e.g. a version
   marked `ACTIVE` with no corresponding audit event) is ever left committed.

## Consequences

- Concurrent activations, and concurrent version creation against the same
  document, serialize on the document lock.
- Institutional Identity strings remain synchronized with ACTIVE policy versions for mapped kinds, or activation is blocked entirely (never silently skipped).
- ACTIVE database rows remain the source of truth for runtime lookups.
- A hash-mismatch or missing-identity failure never touches the prior
  `ACTIVE` version; only the target version was ever a candidate for
  mutation, and it is only mutated after both checks pass.
