"""Interactive Brokers adapter scaffold — optional, disabled, no account required.

Importing or registering this module never contacts IBKR. ``submit_order``
always raises ``LiveExecutionForbiddenError``. No SSN or brokerage account is
required to import, register, or contract-test this module.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.execution.adapters.base import AdapterDescriptor, LiveAdapterBase
from app.execution.contracts import ExecutionEnvironment, VerificationStatus

IBKR_DESCRIPTOR = AdapterDescriptor(
    provider_key="ibkr_adapter",
    display_name="Interactive Brokers Adapter (optional)",
    environment=ExecutionEnvironment.LIVE,
    verification_status=VerificationStatus.CONTRACT_TESTED,
    required_credential_refs=("IBKR_GATEWAY_TOKEN_REF",),
    description=(
        "Optional plug-in scaffold. No brokerage account required to run "
        "Argus. Live execution permanently disabled in Phase 13."
    ),
)


@dataclass(frozen=True)
class IbkrOrderRequest:
    conid: str
    side: str
    order_type: str
    quantity: str


@dataclass(frozen=True)
class IbkrOrderResponse:
    order_id: str
    status: str


class IbkrAdapter(LiveAdapterBase):
    provider_key = "ibkr_adapter"
    descriptor = IBKR_DESCRIPTOR
