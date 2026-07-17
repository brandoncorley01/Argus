# Institutional Identity

This document defines the durable institutional identity for Argus. Runtime persistence of these fields will be introduced with the application schema in a later phase. Values here are the approved baseline for Version 0.1 Foundation.

## Identity record

| Field | Value |
| --- | --- |
| Institution name | Argus |
| Institution ID | `argus-001` |
| Product version | `0.1.0-foundation` |
| Founding date | `2026-07-15` |
| Active Constitution version | `constitution-v0.1` (documented baseline; machine activation deferred) |
| Active Operating Policy version | `operating-policy-v0.1` |
| Active Governance version | `governance-v0.1` |
| Active Treasury Policy version | `treasury-policy-v0.1` |
| Active Research Framework version | `research-framework-v0.1` |

## Operating modes (approved names)

The institutional operating-mode state machine uses these exact names:

| Mode | v0.1 posture |
| --- | --- |
| `OFF` | System offline / not operating |
| `OBSERVE` | Observation without execution capability |
| `PAPER` | Paper posture (no execution engine in Phase 0/1) |
| `MICRO_LIVE` | **Permanently locked** in v0.1 |
| `NORMAL_LIVE` | **Permanently locked** in v0.1 |
| `SAFE_MODE` | Safe failure / restricted operation |
| `EMERGENCY_STOP` | Immediate halt posture |

Do not substitute alternate names such as `INIT`, `RESEARCH`, `ACTIVE`, or `LIVE`.

## RBAC roles (v0.1)

- `FOUNDER`
- `OPERATOR`
- `VIEWER`

## Principles

- Capital preservation comes before profit.
- Important configuration and policy versions must remain auditable and versioned.
- Live trading remains disabled until explicitly implemented and approved in a future release.
