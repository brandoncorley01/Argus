# Argus documentation

This directory holds the durable documentation for Argus, a private institutional crypto research and paper-trading system. Keep application code, infrastructure, and trading components out of these folders unless they are documentation.

## Directory guide

| Directory | Purpose |
| --- | --- |
| [`foundation/`](foundation/) | Project identity, operating principles, glossary, assumptions, and non-negotiable constraints (for example capital preservation and paper-trading-only posture until live trading is approved). |
| [`architecture/`](architecture/) | System design: module boundaries, responsibility separation, data flows, interfaces, and significant architectural decisions. |
| [`research/`](research/) | Research methodology, market study notes, strategy hypotheses, validation criteria, and evidence standards. Do not treat unvalidated ideas as proven performance. |
| [`risk/`](risk/) | Risk policy, limits, controls, failure modes, and audit expectations. Risk controls must never be bypassed. |
| [`governance/`](governance/) | Decision rights, approval paths, change control, and accountability for important actions. |
| [`treasury/`](treasury/) | Capital allocation, paper balances, funding posture, and treasury operating rules. No withdrawal, leverage, margin, futures, or short-selling functionality belongs here as product scope. |
| [`releases/`](releases/) | Version history, release notes, migration notes, and rollout records for documented system changes. |

## Working conventions

- Prefer clear, versioned documents over ad hoc notes when the content affects risk, architecture, or configuration.
- Record important actions and decisions so they remain auditable.
- Prefer safe failure and honest uncertainty over claims that outrun available evidence.
