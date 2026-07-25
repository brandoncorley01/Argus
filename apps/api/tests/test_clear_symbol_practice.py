"""Clear inaccurate paper practice symbols so Founder can restart cleanly."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.paper_trading_service import PaperTradingService


def test_bar_is_trustworthy_rejects_manual_and_absurd_btc() -> None:
    junk = SimpleNamespace(
        source_attribution="manual-operator-entry", close=Decimal("105")
    )
    assert PaperTradingService._bar_is_trustworthy("BTC-USD", junk) is False  # type: ignore[arg-type]
    low = SimpleNamespace(
        source_attribution="coinbase_exchange_public_candles",
        close=Decimal("200"),
    )
    assert PaperTradingService._bar_is_trustworthy("BTC-USD", low) is False  # type: ignore[arg-type]
    good = SimpleNamespace(
        source_attribution="coinbase_exchange_public_candles",
        close=Decimal("95000"),
    )
    assert PaperTradingService._bar_is_trustworthy("BTC-USD", good) is True  # type: ignore[arg-type]


def test_clear_symbol_practice_refunds_and_deletes() -> None:
    db = MagicMock()
    svc = PaperTradingService(db)
    portfolio = SimpleNamespace(
        id="p1",
        cash_balance=Decimal("1000"),
        default_provider_id="prov1",
        status="active",
    )
    svc.get_portfolio = MagicMock(return_value=portfolio)  # type: ignore[method-assign]
    pos = SimpleNamespace(
        quantity=Decimal("1"),
        average_cost=Decimal("126.43"),
        symbol="BTC-USD",
    )
    fill = SimpleNamespace(id="f1", symbol="BTC-USD")
    order = SimpleNamespace(id="o1", symbol="BTC-USD")

    # scalars() is called for positions, fills, orders
    db.scalars.side_effect = [
        iter([pos]),
        iter([fill]),
        iter([order]),
        iter([]),  # purge bars loop
    ]
    db.get.return_value = None  # no provider runtime
    svc.audit.append = MagicMock()  # type: ignore[method-assign]
    svc.purge_untrusted_bars = MagicMock(return_value=2)  # type: ignore[method-assign]

    actor = SimpleNamespace(user=SimpleNamespace(id="u1"))
    out = svc.clear_symbol_practice(
        portfolio_id=portfolio.id,  # type: ignore[arg-type]
        symbol="btc-usd",
        actor=actor,  # type: ignore[arg-type]
    )
    assert out["symbol"] == "BTC-USD"
    assert Decimal(out["cash_refunded"]) == Decimal("126.43")
    assert portfolio.cash_balance == Decimal("1126.43")
    assert out["fills_removed"] == 1
    assert out["bars_purged"] == 2
    db.commit.assert_called()
    svc.audit.append.assert_called()
