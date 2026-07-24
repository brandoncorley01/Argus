"""Kraken adapter scaffold — optional, disabled, no account required.

Importing or registering this module never contacts Kraken. ``submit_order``
always raises ``LiveExecutionForbiddenError``.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.execution.adapters.base import AdapterDescriptor, LiveAdapterBase
from app.execution.contracts import ExecutionEnvironment, VerificationStatus

KRAKEN_DESCRIPTOR = AdapterDescriptor(
    provider_key="kraken_adapter",
    display_name="Kraken Adapter (optional)",
    environment=ExecutionEnvironment.LIVE,
    verification_status=VerificationStatus.CONTRACT_TESTED,
    required_credential_refs=("KRAKEN_API_KEY_REF", "KRAKEN_API_SECRET_REF"),
    description=(
        "Optional plug-in scaffold. No brokerage/exchange account required to "
        "run Argus. Live execution permanently disabled in Phase 13."
    ),
)


@dataclass(frozen=True)
class KrakenOrderRequest:
    pair: str
    type: str
    ordertype: str
    volume: str


@dataclass(frozen=True)
class KrakenOrderResponse:
    txid: str
    status: str


class KrakenAdapter(LiveAdapterBase):
    provider_key = "kraken_adapter"
    descriptor = KRAKEN_DESCRIPTOR
