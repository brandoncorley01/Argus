"""Deterministic mock transport for adapter contract tests.

This is the only "transport" any Phase 13 adapter is ever exercised against
in this codebase. It never performs network I/O; it returns fixed fixture
data so contract tests can assert adapter behavior without a real account.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockTransportResponse:
    status_code: int
    payload: dict[str, Any] = field(default_factory=dict)


class MockTransport:
    """Fixture-oriented stand-in for an HTTP/WebSocket exchange transport.

    Deliberately has no concept of a real base URL, API key, or secret. Any
    attempt to "connect" simply returns a canned disabled response.
    """

    def __init__(self, provider_key: str) -> None:
        self.provider_key = provider_key
        self.calls: list[str] = []

    def connect(self) -> MockTransportResponse:
        self.calls.append("connect")
        return MockTransportResponse(
            status_code=200, payload={"status": "disabled", "reason": "credentials_unavailable"}
        )

    def fetch_account(self) -> MockTransportResponse:
        self.calls.append("fetch_account")
        return MockTransportResponse(status_code=403, payload={"error": "credentials_unavailable"})

    def submit_order(self, order_payload: dict[str, Any]) -> MockTransportResponse:
        self.calls.append("submit_order")
        return MockTransportResponse(
            status_code=403,
            payload={"error": "live_execution_forbidden", "order": order_payload},
        )
