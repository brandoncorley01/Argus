# ADR-013: Database-enforced version immutability triggers

- Status: Accepted
- Date: 2026-07-17
- Deciders: Founder (Phase 6 remediation)

## Context

The application layer already blocks edits to non-`DRAFT` configuration/policy
versions (`GovernanceService.update_configuration_draft` /
`update_policy_draft` reject any version whose `status != DRAFT`). That is an
application-level guarantee only: any other code path with a database
connection -- a bug in a future service, an ad-hoc maintenance script, a
different application entirely -- could still `UPDATE` a finalized version's
`content` or `payload_hash` directly in Postgres, silently corrupting the
system of record that audit events and payload-hash verification depend on.

## Decision

1. Add a `BEFORE UPDATE` trigger function `enforce_version_immutability()` on
   both `configuration_versions` and `policy_versions`.
2. The trigger rejects (raises) any `UPDATE` where `OLD.status <> 'DRAFT'`
   **and** one of the following columns is changing: `content`,
   `payload_hash`, `document_id`, `version_number`, `previous_version_id`,
   `created_by_user_id`, `created_at`, `version_label`, `change_summary`.
3. The trigger explicitly **allows** changes to lifecycle/status columns at
   any time, regardless of `OLD.status`: `status` itself, and the
   `submitted_at/by`, `approved_at/by`, `activated_at/by`, `superseded_at/by`,
   `rejected_at/by`, `rejection_reason`, `retired_at/by` attribution columns.
   These are exactly the columns `GovernanceService` mutates when
   transitioning a version through its lifecycle.
4. Rows still in `DRAFT` are unrestricted by this trigger (the application
   layer is the sole gatekeeper for in-progress drafts).

## Consequences

- Once a version leaves `DRAFT`, its payload and identifying metadata are
  immutable at the database level, not just in application code. This
  includes the `SUPERSEDED` versions produced by the Phase 6 migration
  backfill (see the addendum to ADR-009): those rows are immutable
  immediately, even though they were never actually reviewed through the
  `DRAFT -> UNDER_REVIEW -> APPROVED` flow.
- Legitimate lifecycle transitions (submit, approve, reject, activate,
  supersede, retire, and the explicit `UNDER_REVIEW -> DRAFT` return-to-draft)
  continue to work unchanged, because they only touch the allow-listed
  lifecycle columns.
- The trigger function and both triggers are created once per database and
  dropped in `downgrade()`. Downgrading past this migration removes the
  database-level guarantee; only the application-level check remains.
