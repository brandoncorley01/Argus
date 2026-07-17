# ADR-006: Fail-closed audit policy

- Status: Accepted
- Date: 2026-07-15
- Deciders: Founder

## Context

Every important action must be auditable. If audit recording is unavailable, continuing critical institutional mutations would violate capital-preservation and governance posture.

## Decision

**Critical institutional mutations must fail closed when audit recording is unavailable.**

Critical mutations include (non-exhaustive, refined at implementation):

- Authentication-sensitive account changes
- Operating-mode transitions
- Activation of configuration or policy versions
- Feature lock/activation changes
- Privilege / RBAC changes

If the audit write cannot be completed, the mutation must not commit.

## Consequences

- Stronger integrity; possible availability tradeoff during infrastructure failure (prefer `SAFE_MODE` / safe failure).
- Recovery procedures must allow Founder/Operator to restore auditability without silent bypass.
- Non-critical read paths may degrade without fail-closed behavior.
