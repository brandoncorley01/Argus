"""Execution Gateway package (Phase 12) — paper trading only, no live brokers.

Strategies and services must never call a broker/provider directly. All order
flow goes through :mod:`app.execution.gateway`, which enforces the kill
switch, operating mode, and environment guardrails before delegating to a
registered :class:`app.execution.contracts.ExecutionProvider`.
"""

from __future__ import annotations
