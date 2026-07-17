# Configuration and Policy Versioning

Phase 6 control-plane for immutable, auditable configuration and policy versions.

## Concepts

| Concept | Meaning |
| --- | --- |
| Document | Named durable container (`document_key`) with a `schema_identifier` |
| Version | Immutable payload snapshot after leaving `DRAFT` |
| Lifecycle | `DRAFT` → `UNDER_REVIEW` → `APPROVED` → `ACTIVE` → `SUPERSEDED` / `RETIRED`; or `UNDER_REVIEW` → `REJECTED` |
| Active truth | At most one `ACTIVE` version per document (partial unique index) |
| Payload hash | SHA-256 of canonical JSON (`sort_keys`, compact separators) |

## HTTP surfaces

- `/api/v1/configurations/...`
- `/api/v1/policies/...`

Both expose document CRUD (create/list/get), version create/list/get, draft patch, submit/approve/reject/activate/retire, active lookup, and compare.

Mutating routes require authentication + CSRF. Approve/activate/retire (and governance-critical policy create) are Founder-only.

## Activation

Activation is atomic within one DB transaction:

1. Lock the parent document row (`SELECT … FOR UPDATE`)
2. Verify payload hash
3. Supersede any current `ACTIVE` version
4. Mark the approved version `ACTIVE`
5. For mapped policy kinds, update Institutional Identity string pointers
6. Append fail-closed audit events, then commit

## Secret detection

Payloads are rejected when keys or values match secret patterns (API keys, private key PEM blocks, credential-like field names). Secrets must never be stored in versioned config/policy JSON.

## Related ADRs

- ADR-009 lifecycle statuses
- ADR-010 canonical payload hashing
- ADR-011 atomic activation
- ADR-012 secret detection in version payloads
