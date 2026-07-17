# Configuration and Policy Versioning

Phase 6 control-plane for immutable, auditable configuration and policy versions.

## Concepts

| Concept | Meaning |
| --- | --- |
| Document | Named durable container (`document_key`) with a `schema_identifier` and a `draft_authority` |
| Version | Immutable payload snapshot after leaving `DRAFT`; immutability of non-`DRAFT` versions is enforced both in the service layer and by a database trigger (ADR-013) |
| Lifecycle | `DRAFT` → `UNDER_REVIEW` → `APPROVED` → `ACTIVE` → `SUPERSEDED` / `RETIRED`; or `UNDER_REVIEW` → `REJECTED`; or `UNDER_REVIEW` → `DRAFT` (explicit return-to-draft) |
| Active truth | At most one `ACTIVE` version per document (partial unique index) |
| Payload hash | SHA-256 of canonical JSON (`sort_keys`, compact separators) |
| `draft_authority` | Per-document enum (`FOUNDER_ONLY` \| `FOUNDER_OR_OPERATOR`) controlling whether Operator may create/edit `DRAFT` versions; Founder can always draft. Governance-critical policy kinds always require Founder regardless of this setting. |
| Mapped policy kinds | `constitution`, `operating`, `governance`, `treasury`, `research` -- each projects its `ACTIVE` version onto one Institutional Identity string pointer (ADR-014). At most one non-retired `PolicyDocument` may exist per mapped kind. |

This module does not implement generic CRUD. Documents are created once by
the Founder and never deleted; versions are created, transitioned through a
fixed lifecycle, and never deleted or content-mutated once they leave
`DRAFT`. "Update" only ever means either (a) editing the *content* of a
version still in `DRAFT` (`draft_updated`), or (b) transitioning `status`
(`submitted`, `approved`, `rejected`, `retired`, `returned_to_draft`,
`superseded`, `activated`) -- there is no endpoint that mutates a finalized
version's payload.

## HTTP surfaces

- `/api/v1/configurations/...`
- `/api/v1/policies/...`

Both expose document create/list/get, version create/list/get, draft patch, submit/approve/reject/activate/retire, active lookup, and compare.

Mutating routes require authentication + CSRF. Document create, approve, activate, and retire are Founder-only. Version create/draft-edit require Founder, or Operator when the document's `draft_authority` is `FOUNDER_OR_OPERATOR` and the policy kind (if any) is not governance-critical.

## Locking and activation sequence

Every mutating operation that touches a document's versions -- creating a new
version, editing a draft, or activating a version -- takes a `SELECT ... FOR
UPDATE` row lock on the parent document (or the target version row) before
doing any read that influences its decision. This makes the following
concurrency guarantees hold under real Postgres transactions, not just in a
single-threaded test:

- Two concurrent "create version" calls against the same document always get
  distinct, contiguous `version_number`s (the allocation happens under the
  document lock).
- Two concurrent "activate" calls against the same document cannot both
  succeed in making a version `ACTIVE`; the second sees the first's committed
  state once its lock is granted and re-checks `status == APPROVED`.

Activation is atomic within one DB transaction:

1. Lock the parent document row (`SELECT … FOR UPDATE`).
2. Re-fetch and row-lock the target version; re-check it is still
   `APPROVED`, and re-verify its payload hash.
3. On hash mismatch: do not change the version's status; attempt to audit the
   failure; raise `GovernanceError` either way (fail-closed). The prior
   `ACTIVE` version, if any, is left completely untouched.
4. For mapped policy kinds, resolve (and row-lock) the singleton Institutional
   Identity record. If it does not exist, abort before mutating anything
   (fail-closed) -- see ADR-014.
5. Row-lock and supersede any current `ACTIVE` version.
6. Mark the approved version `ACTIVE`.
7. For mapped policy kinds, set the Institutional Identity pointer to
   `{document_key}@{version_number}` (ADR-014).
8. Append fail-closed audit events, then commit. If the audit write fails,
   the whole transaction rolls back and `GovernanceError` is raised; no
   partial activation is ever left committed.

Retiring an `ACTIVE` version of a mapped policy kind is prohibited outright --
a replacement version must be activated (which supersedes it) instead.

## Audit action names

Audit actions describe what actually happened, not a generic CRUD verb:
`*.created` (true creation only), `*.draft_updated` (content edit while still
`DRAFT`), `*.submitted`, `*.approved`, `*.rejected`, `*.retired`,
`*.returned_to_draft`, `*.superseded`, `*.activated`, `*.integrity.failed`,
`policy_activation.identity_missing`.

## Secret detection

Payloads are rejected when keys or values match secret patterns (API keys, private key PEM blocks, credential-like field names, connection strings with embedded credentials, bearer-token-shaped values). Detection is recursive at any nesting depth. Secrets must never be stored in versioned config/policy JSON.

## Related ADRs

- ADR-009 lifecycle statuses (and legacy-migration addendum)
- ADR-010 canonical payload hashing (and baseline-validation-not-schema-validation addendum)
- ADR-011 atomic activation and locking sequence
- ADR-012 secret detection in version payloads
- ADR-013 database-enforced immutability triggers
- ADR-014 Institutional Identity projection and mapped-kind retirement policy
