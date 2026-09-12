"""Entry-linked, fee-aware closed-trade accounting."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.paper_trading import PaperFill, PaperOrder
from app.services.paper_trading_service import PaperTradingService


def test_partial_exits_aggregate_against_their_actual_entry_after_fees() -> None:
    db = MagicMock()
    svc = PaperTradingService(db)
    svc.get_portfolio = MagicMock()  # type: ignore[method-assign]
    portfolio_id = uuid.uuid4()
    entry_id = uuid.uuid4()
    now = datetime.now(UTC)
    entry = PaperFill(
        order_id=entry_id,
        portfolio_id=portfolio_id,
        symbol="DOT-USD",
        side="buy",
        quantity=Decimal("2"),
        price=Decimal("100"),
        fee=Decimal("0.20"),
        filled_at=now,
    )
    first_exit = PaperFill(
        id=uuid.uuid4(),
        portfolio_id=portfolio_id,
        symbol="DOT-USD",
        side="sell",
        quantity=Decimal("1"),
        price=Decimal("110"),
        fee=Decimal("0.11"),
        filled_at=now + timedelta(minutes=5),
    )
    final_exit = PaperFill(
        id=uuid.uuid4(),
        portfolio_id=portfolio_id,
        symbol="DOT-USD",
        side="sell",
        quantity=Decimal("1"),
        price=Decimal("90"),
        fee=Decimal("0.09"),
        filled_at=now + timedelta(minutes=10),
    )
    first_order = PaperOrder(
        id=uuid.uuid4(),
        portfolio_id=portfolio_id,
        idempotency_key=f"exit:{portfolio_id}:DOT-USD:scale_out:{entry_id}",
    )
    final_order = PaperOrder(
        id=uuid.uuid4(),
        portfolio_id=portfolio_id,
        idempotency_key=f"exit:{portfolio_id}:DOT-USD:stop_loss:{entry_id}",
    )
    db.execute.return_value = [(first_exit, first_order), (final_exit, final_order)]
    db.scalar.return_value = entry

    legs = svc.list_realized_exit_legs(portfolio_id)
    closed = svc.list_closed_trades(portfolio_id, limit=10)

    assert [leg["realized_pnl"] for leg in legs] == [
        Decimal("9.79"),
        Decimal("-10.19"),
    ]
    assert len(closed) == 1
    assert closed[0]["exit_leg_count"] == 2
    assert closed[0]["realized_pnl"] == Decimal("-0.40")


def test_unlinked_legacy_exit_is_not_given_a_fabricated_cost_basis() -> None:
    db = MagicMock()
    svc = PaperTradingService(db)
    svc.get_portfolio = MagicMock()  # type: ignore[method-assign]
    portfolio_id = uuid.uuid4()
    exit_fill = PaperFill(
        portfolio_id=portfolio_id,
        symbol="SUI-USD",
        side="sell",
        quantity=Decimal("1"),
        price=Decimal("1"),
        fee=Decimal("0"),
        filled_at=datetime.now(UTC),
    )
    exit_order = PaperOrder(
        portfolio_id=portfolio_id,
        idempotency_key="legacy-manual-exit",
    )
    db.execute.return_value = [(exit_fill, exit_order)]

    assert svc.list_realized_exit_legs(portfolio_id) == []


def test_daily_equity_pnl_turns_red_when_open_marks_outweigh_realized_gain() -> None:
    db = MagicMock()
    svc = PaperTradingService(db)
    portfolio_id = uuid.uuid4()
    day_start = datetime(2026, 9, 9, 4, 0, tzinfo=UTC)
    db.scalar.side_effect = [
        None,  # no capital reset today
        SimpleNamespace(balance_after=Decimal("100")),
        datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
        SimpleNamespace(id=uuid.uuid4()),
    ]
    db.execute.return_value = [("DOT-USD", Decimal("2"))]
    db.scalars.return_value = [
        SimpleNamespace(
            close=Decimal("50"),
            close_time=day_start,
            source_attribution="coinbase_public",
        )
    ]
    svc.portfolio_summary = MagicMock(  # type: ignore[method-assign]
        return_value={
            "total_account_value": Decimal("198"),
            "marks_complete": True,
        }
    )
    svc.day_realized_pnl = MagicMock(  # type: ignore[method-assign]
        return_value={"today_realized_pnl": Decimal("3")}
    )

    result = svc.day_equity_pnl(
        portfolio_id,
        now=datetime(2026, 9, 9, 10, 0, tzinfo=UTC),
    )

    assert result["baseline_account_value"] == Decimal("200")
    assert result["today_realized_pnl"] == Decimal("3")
    assert result["today_mark_to_market_component"] == Decimal("-5")
    assert result["today_equity_pnl"] == Decimal("-2")
    assert result["pnl_basis"] == "account_equity_change_since_midnight"


def test_daily_equity_pnl_accepts_aged_open_marks_after_feed_gap() -> None:
    db = MagicMock()
    svc = PaperTradingService(db)
    portfolio_id = uuid.uuid4()
    day_start = datetime(2026, 9, 11, 4, 0, tzinfo=UTC)
    db.scalar.side_effect = [
        None,  # no capital reset today
        SimpleNamespace(balance_after=Decimal("100")),
        datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
        SimpleNamespace(id=uuid.uuid4()),
    ]
    db.execute.return_value = [("XRP-USD", Decimal("10"))]
    db.scalars.return_value = [
        SimpleNamespace(
            close=Decimal("1.40"),
            close_time=day_start - timedelta(hours=30),
            source_attribution="coinbase_exchange_public_candles",
        )
    ]
    svc.portfolio_summary = MagicMock(  # type: ignore[method-assign]
        return_value={
            "total_account_value": Decimal("110"),
            "marks_complete": True,
        }
    )
    svc.day_realized_pnl = MagicMock(  # type: ignore[method-assign]
        return_value={"today_realized_pnl": Decimal("-5")}
    )

    result = svc.day_equity_pnl(
        portfolio_id,
        now=datetime(2026, 9, 11, 20, 0, tzinfo=UTC),
    )

    assert result["baseline_account_value"] == Decimal("114.0")
    assert result["today_equity_pnl"] == Decimal("-4.0")
    assert result["baseline_mark_max_age_minutes"] == 30 * 60
    assert result["pnl_basis"] == "account_equity_change_since_midnight_open_marks_aged"
