"""Paper exit plans — stop/target attached to entries; long-only paper exits."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.paper_training_service import PaperTrainingService


def test_evaluate_paper_exits_take_profit_triggers_sell() -> None:
    db = MagicMock()
    svc = PaperTrainingService(db)
    portfolio = SimpleNamespace(
        id="p1",
        kill_switch_active=False,
        owner_user_id="u1",
    )
    db.get.return_value = portfolio
    pos = SimpleNamespace(symbol="BTC-USD", quantity=Decimal("0.01"))
    svc.paper.list_positions = MagicMock(return_value=[pos])  # type: ignore[method-assign]
    svc.paper._exit_plan_levels = MagicMock(  # type: ignore[method-assign]
        return_value={
            "stop_loss": Decimal("90"),
            "take_profit": Decimal("110"),
        }
    )
    svc.paper._latest_mark = MagicMock(  # type: ignore[method-assign]
        return_value=(Decimal("111"), None)
    )
    order = SimpleNamespace(id="ord1", status="filled")
    svc.paper.submit_order = MagicMock(return_value=order)  # type: ignore[method-assign]
    svc.paper._event = MagicMock()  # type: ignore[method-assign]
    svc._resolve_actor = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(user=SimpleNamespace(id="u1"))
    )
    svc.audit.append = MagicMock()  # type: ignore[method-assign]

    out = svc.evaluate_paper_exits(portfolio_id=portfolio.id, actor=None)
    assert len(out) == 1
    assert out[0]["reason"] == "take_profit"
    assert svc.paper.submit_order.call_args.kwargs["side"] == "sell"


def test_evaluate_paper_exits_stop_triggers_sell() -> None:
    db = MagicMock()
    svc = PaperTrainingService(db)
    portfolio = SimpleNamespace(
        id="p1",
        kill_switch_active=False,
        owner_user_id="u1",
    )
    db.get.return_value = portfolio
    pos = SimpleNamespace(symbol="ETH-USD", quantity=Decimal("1"))
    svc.paper.list_positions = MagicMock(return_value=[pos])  # type: ignore[method-assign]
    svc.paper._exit_plan_levels = MagicMock(  # type: ignore[method-assign]
        return_value={
            "stop_loss": Decimal("100"),
            "take_profit": Decimal("130"),
        }
    )
    svc.paper._latest_mark = MagicMock(  # type: ignore[method-assign]
        return_value=(Decimal("99"), None)
    )
    order = SimpleNamespace(id="ord2", status="filled")
    svc.paper.submit_order = MagicMock(return_value=order)  # type: ignore[method-assign]
    svc.paper._event = MagicMock()  # type: ignore[method-assign]
    svc._resolve_actor = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(user=SimpleNamespace(id="u1"))
    )
    svc.audit.append = MagicMock()  # type: ignore[method-assign]

    out = svc.evaluate_paper_exits(portfolio_id=portfolio.id, actor=None)
    assert len(out) == 1
    assert out[0]["reason"] == "stop_loss"


def test_evaluate_paper_exits_skips_when_between_levels() -> None:
    db = MagicMock()
    svc = PaperTrainingService(db)
    portfolio = SimpleNamespace(
        id="p1",
        kill_switch_active=False,
        owner_user_id="u1",
    )
    db.get.return_value = portfolio
    pos = SimpleNamespace(symbol="SOL-USD", quantity=Decimal("2"))
    svc.paper.list_positions = MagicMock(return_value=[pos])  # type: ignore[method-assign]
    svc.paper._exit_plan_levels = MagicMock(  # type: ignore[method-assign]
        return_value={
            "stop_loss": Decimal("10"),
            "take_profit": Decimal("20"),
        }
    )
    svc.paper._latest_mark = MagicMock(  # type: ignore[method-assign]
        return_value=(Decimal("15"), None)
    )
    svc.paper.submit_order = MagicMock()  # type: ignore[method-assign]
    svc._resolve_actor = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(user=SimpleNamespace(id="u1"))
    )

    out = svc.evaluate_paper_exits(portfolio_id=portfolio.id, actor=None)
    assert out == []
    svc.paper.submit_order.assert_not_called()
