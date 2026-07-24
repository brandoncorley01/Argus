"""Coinbase adapter scaffold — optional, disabled, no account required.

Importing or registering this module never contacts Coinbase. It exists so
the adapter framework and registry have a concrete plug-in shape to test
against; ``submit_order`` always raises ``LiveExecutionForbiddenError``.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.execution.adapters.base import AdapterDescriptor, LiveAdapterBase
from app.execution.contracts import ExecutionEnvironment, VerificationStatus

COINBASE_DESCRIPTOR = AdapterDescriptor(
    provider_key="coinbase_adapter",
    display_name="Coinbase Adapter (optional)",
    environment=ExecutionEnvironment.LIVE,
    verification_status=VerificationStatus.CONTRACT_TESTED,
    required_credential_refs=("COINBASE_API_KEY_REF", "COINBASE_API_SECRET_REF"),
    description=(
        "Optional plug-in scaffold. No brokerage/exchange account required to "
        "run Argus. Live execution permanently disabled in Phase 13."
    ),
)


@dataclass(frozen=True)
class CoinbaseOrderRequest:
    """Request model boundary — never constructed from a real credential."""

    product_id: str
    side: str
    order_type: str
    size: str


@dataclass(frozen=True)
class CoinbaseOrderResponse:
    order_id: str
    status: str


class CoinbaseAdapter(LiveAdapterBase):
    provider_key = "coinbase_adapter"
    descriptor = COINBASE_DESCRIPTOR
