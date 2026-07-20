"""Optional live-adapter scaffolds (Phase 13) — never default, never live.

Every adapter in this package:

- Is registered as an *optional* provider, never the default provider.
- Never opens a network connection in default mode (``connect()`` always
  returns a disabled/``credentials_unavailable`` status).
- Raises :class:`app.execution.contracts.LiveExecutionForbiddenError` from
  ``submit_order`` unconditionally.
- Requires no brokerage account, SSN, or paid API key to import, register,
  or contract-test.

See ADR-029 and ``docs/architecture/MICRO_LIVE.md``.
"""

from __future__ import annotations

from app.execution.adapters.base import AdapterDescriptor, LiveAdapterBase

__all__ = ["AdapterDescriptor", "LiveAdapterBase"]
