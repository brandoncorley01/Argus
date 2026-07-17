# ADR-014: Institutional Identity projection and mapped-kind retirement policy

- Status: Accepted
- Date: 2026-07-17
- Deciders: Founder (Phase 6 remediation)

## Context

Five policy kinds -- `constitution`, `operating`, `governance`, `treasury`,
`research` -- each project their currently `ACTIVE` version onto a single
string column on the singleton `InstitutionalIdentity` row
(`active_constitution_version`, `active_operating_policy_version`, etc.). Two
gaps existed in the initial Phase 6 implementation:

1. Activation silently skipped the identity update when no
   `InstitutionalIdentity` row existed yet, leaving the activated policy
   version and the (missing) identity pointer out of sync with no error.
2. The pointer stored was `version_label`, a free-text field with no
   uniqueness or format guarantee, and nothing prevented more than one
   non-retired `PolicyDocument` from claiming the same mapped kind (which
   would make "the" active pointer for that kind ambiguous), or an `ACTIVE`
   mapped version from being retired without a replacement (leaving the
   identity pointer referencing a `RETIRED` version).

## Decision

1. **Fail closed on missing identity.** Activating an `APPROVED` version of a
   mapped policy kind requires an existing `InstitutionalIdentity` row. If
   none exists, activation is aborted with `GovernanceError` (audited as
   `policy_activation.identity_missing`) before any status is mutated -- no
   supersede, no activate, no partial state.
2. **Stable pointer format.** The identity pointer is
   `{document_key}@{version_number}` (see
   `GovernanceService.identity_pointer`), not `version_label`. This is
   collision-free per document (backed by the
   `(document_id, version_number)` unique constraint) and stable even if
   `version_label` formatting changes later. `InstitutionalIdentity` string
   columns are widened to `String(256)` to accommodate this format.
3. **One non-retired document per mapped kind.** A partial unique index
   (`uq_policy_documents_one_per_mapped_kind`) enforces at most one
   non-retired `PolicyDocument` per mapped kind, so "the" identity pointer
   for a mapped kind is never ambiguous.
4. **Retirement of ACTIVE mapped versions is prohibited.** `RETIRED` remains a
   valid transition from `ACTIVE` for non-mapped policy kinds and for
   configuration versions, but `GovernanceService.transition_policy_version`
   rejects `ACTIVE -> RETIRED` for any mapped-kind policy version. A
   replacement version must be activated instead, which supersedes (not
   retires) the previous `ACTIVE` version and keeps the identity pointer
   continuously valid.

## Consequences

- Institutional Identity pointers for mapped kinds are always either unset
  (no version ever activated) or point at a version that is `ACTIVE` or
  `SUPERSEDED` -- never `RETIRED`.
- Bootstrapping a brand-new environment requires creating the
  `InstitutionalIdentity` row before the first mapped-kind policy activation;
  this is intentional friction to prevent silent drift.
- Existing `version_label`-based pointers written before this ADR are not
  migrated retroactively; the format change takes effect for the next
  activation of each mapped document.
