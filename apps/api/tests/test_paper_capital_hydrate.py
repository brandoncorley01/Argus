"""Paper capital must stay accurate across API restarts (in-memory hydrate)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.execution.contracts import (
    ExecutionEnvironment,
    OrderIntent,
    OrderSide,
    OrderType,
)
from app.execution.providers.paper import _ACCOUNT_STORE, PaperExecutionProvider


def _intent(portfolio_id, *, side: OrderSide, qty: str = "1") -> OrderIntent:
    return OrderIntent(
        portfolio_id=portfolio_id,
        provider_id=uuid4(),
        symbol="BTC-USD",
        side=side,
        order_type=OrderType.MARKET,
        quantity=Decimal(qty),
        limit_price=Decimal("100"),
        client_order_id=f"c-{uuid4()}",
        idempotency_key=f"k-{uuid4()}",
        strategy_version_id=None,
        session_id=None,
        environment=ExecutionEnvironment.PAPER,
    )


def test_restart_hydrate_preserves_position_and_cash() -> None:
    """Simulate API restart: empty memory, then hydrate from DB before next order."""
    pid = uuid4()
    provider = PaperExecutionProvider()
    provider.connect()
    provider.ensure_account(pid, cash=Decimal("300"))
    state, fills = provider.submit_order(_intent(pid, side=OrderSide.BUY))
    assert state.status.value in {"filled", "partially_filled"}
    assert fills
    cash_after_buy = Decimal(provider.balances(pid)["cash"])
    positions = provider.positions(pid)
    assert len(positions) == 1
    assert positions[0]["symbol"] == "BTC-USD"

    # Restart — process-local store wiped.
    _ACCOUNT_STORE.clear()
    assert provider.account_state(pid)["exists"] is False

    # Next order path hydrates DB cash + open positions before trading.
    provider.ensure_account(
        pid,
        cash=cash_after_buy,
        positions=[
            {
                "symbol": "BTC-USD",
                "quantity": positions[0]["quantity"],
                "average_cost": positions[0]["average_cost"],
            }
        ],
    )
    assert Decimal(provider.balances(pid)["cash"]) == cash_after_buy
    assert len(provider.positions(pid)) == 1

    # Sell must succeed (would reject as short if hydrate missed the position).
    sell, sell_fills = provider.submit_order(_intent(pid, side=OrderSide.SELL))
    assert sell.status.value in {"filled", "partially_filled"}
    assert sell_fills
    assert provider.positions(pid) == []
    assert Decimal(provider.balances(pid)["cash"]) > cash_after_buy


def test_reseed_reset_overwrites_stale_memory_cash() -> None:
    pid = uuid4()
    provider = PaperExecutionProvider()
    provider.connect()
    provider.ensure_account(pid, cash=Decimal("50"))
    provider.submit_order(_intent(pid, side=OrderSide.BUY, qty="0.1"))
    stale = Decimal(provider.balances(pid)["cash"])
    assert stale < Decimal("50")

    provider.reset_account(pid, cash=Decimal("300"))
    assert Decimal(provider.balances(pid)["cash"]) == Decimal("300")
    assert provider.positions(pid) == []


def test_ensure_account_overwrites_stale_empty_book() -> None:
    """Old ensure_account left empty books alone — that wiped DB on sync."""
    pid = uuid4()
    provider = PaperExecutionProvider()
    provider.ensure_account(pid, cash=Decimal("10"))
    # Stale empty book with wrong cash.
    assert Decimal(provider.balances(pid)["cash"]) == Decimal("10")

    provider.ensure_account(
        pid,
        cash=Decimal("220.50"),
        positions=[
            {
                "symbol": "ETH-USD",
                "quantity": Decimal("0.5"),
                "average_cost": Decimal("200"),
            }
        ],
    )
    assert Decimal(provider.balances(pid)["cash"]) == Decimal("220.50")
    pos = provider.positions(pid)
    assert len(pos) == 1
    assert pos[0]["symbol"] == "ETH-USD"
    assert pos[0]["quantity"] == Decimal("0.5")
