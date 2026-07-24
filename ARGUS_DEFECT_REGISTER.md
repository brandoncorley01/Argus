# ARGUS Defect Register — RC1

| Field | Value |
| --- | --- |
| **Date** | 2026-07-21 |
| **Base commit** | `8d0fd715a05dead9b1e36b573630d7a285c2b384` |
| **Branch** | `phase-14-treasury-executive-analytics` |

## Critical

**None.**

## High (process — non-blocking for local controlled paper)

| ID | Description | Status |
| --- | --- | --- |
| H-RC1-01 | Phase stack not yet merged to `main` | Open — Founder action |
| H-RC1-02 | GitHub Actions not yet observed green on remote | Open until first push/PR CI run |

## Medium (accepted)

| ID | Description |
| --- | --- |
| M-RC1-01 | Paper provider process-local memory |
| M-RC1-05 | No formal interactive browser UI gate |
| M-RC1-06 | OneDrive `.next` build fragility (mitigated by clean rebuild) |
| M-RC1-07 | Dual operating-mode vs live-activation model |

## Fixed this finalization

| ID | Description |
| --- | --- |
| F-RC1-01 | `validate-db-restore.ps1` PowerShell parse failure blocking restore validation |

## Informational

Live disabled; `internal_paper` default; no real funds used.
