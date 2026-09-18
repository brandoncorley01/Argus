"""Paper exit plans — stop/target attached to entries; long-only paper exits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
        return_value=(Decimal("111"), datetime.now(UTC))
    )
    order = SimpleNamespace(id="ord1", status="filled")
    svc.paper.submit_order = MagicMock(return_value=order)  # type: ignore[method-assign]
    svc.paper._event = MagicMock()  # type: ignore[method-assign]
    svc._resolve_actor = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(user=SimpleNamespace(id="u1"))
    )
    svc._position_held_seconds = MagicMock(return_value=180.0)  # type: ignore[method-assign]
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
        return_value=(Decimal("99"), datetime.now(UTC))
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


def test_evaluate_paper_exits_ratchets_stop_without_exiting() -> None:
    db = MagicMock()
    svc = PaperTrainingService(db)
    portfolio = SimpleNamespace(
        id="p1",
        kill_switch_active=False,
        owner_user_id="u1",
    )
    entry = SimpleNamespace(id="ord-entry", status="filled")

    def _get(model: object, key: object) -> object:
        if key == portfolio.id:
            return portfolio
        return entry

    db.get.side_effect = _get
    pos = SimpleNamespace(
        symbol="BTC-USD",
        quantity=Decimal("0.01"),
        average_cost=Decimal("100"),
    )
    svc.paper.list_positions = MagicMock(return_value=[pos])  # type: ignore[method-assign]
    svc.paper._exit_plan_levels = MagicMock(  # type: ignore[method-assign]
        return_value={
            "stop_loss": Decimal("90"),
            "take_profit": Decimal("120"),
            "entry_order_id": "ord-entry",
        }
    )
    svc.paper._latest_mark = MagicMock(  # type: ignore[method-assign]
        return_value=(Decimal("115"), datetime.now(UTC))
    )
    svc.paper.submit_order = MagicMock()  # type: ignore[method-assign]
    svc.paper._event = MagicMock()  # type: ignore[method-assign]
    svc._resolve_actor = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(user=SimpleNamespace(id="u1"))
    )

    out = svc.evaluate_paper_exits(portfolio_id=portfolio.id, actor=None)
    assert out == []
    svc.paper.submit_order.assert_not_called()
    assert svc.paper._event.called
    payload = svc.paper._event.call_args.args[4]
    assert Decimal(payload["stop_loss"]) == Decimal("105")


def test_evaluate_paper_exits_no_breakeven_at_one_r() -> None:
    """+1R must not ratchet to breakeven — that clipped winners into noise exits."""
    db = MagicMock()
    svc = PaperTrainingService(db)
    portfolio = SimpleNamespace(
        id="p1",
        name="Lab Book",
        kill_switch_active=False,
        owner_user_id="u1",
    )
    db.get.return_value = portfolio
    pos = SimpleNamespace(
        symbol="BTC-USD",
        quantity=Decimal("0.01"),
        average_cost=Decimal("100"),
    )
    svc.paper.list_positions = MagicMock(return_value=[pos])  # type: ignore[method-assign]
    svc.paper._exit_plan_levels = MagicMock(  # type: ignore[method-assign]
        return_value={
            "stop_loss": Decimal("90"),
            "take_profit": Decimal("120"),
            "entry_order_id": "ord-entry",
            "scaled_out": False,
        }
    )
    # +1R = mark 110 with risk 10 — must leave planned stop alone.
    svc.paper._latest_mark = MagicMock(  # type: ignore[method-assign]
        return_value=(Decimal("110"), datetime.now(UTC))
    )
    svc.paper.submit_order = MagicMock()  # type: ignore[method-assign]
    svc.paper._event = MagicMock()  # type: ignore[method-assign]
    svc._resolve_actor = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(user=SimpleNamespace(id="u1"))
    )
    svc._catalyst_momentum_weakened = MagicMock(return_value=False)  # type: ignore[method-assign]
    svc._position_held_seconds = MagicMock(return_value=180.0)  # type: ignore[method-assign]

    out = svc.evaluate_paper_exits(portfolio_id=portfolio.id, actor=None)
    assert out == []
    svc.paper.submit_order.assert_not_called()
    svc.paper._event.assert_not_called()


def test_evaluate_paper_exits_scales_out_half_at_one_r_on_founder() -> None:
    """Founder desk banks half at +1R so cash can redeploy into dips."""
    from app.services.paper_training_service import FOUNDER_LEARNING_DESK_NAME

    db = MagicMock()
    svc = PaperTrainingService(db)
    portfolio = SimpleNamespace(
        id="p1",
        name=FOUNDER_LEARNING_DESK_NAME,
        kill_switch_active=False,
        owner_user_id="u1",
    )
    entry = SimpleNamespace(id="ord-entry", status="filled")

    def _get(model: object, key: object) -> object:
        if key == portfolio.id:
            return portfolio
        return entry

    db.get.side_effect = _get
    pos = SimpleNamespace(
        id="pos1",
        symbol="BTC-USD",
        quantity=Decimal("0.02"),
        average_cost=Decimal("100"),
    )
    svc.paper.list_positions = MagicMock(return_value=[pos])  # type: ignore[method-assign]
    svc.paper._exit_plan_levels = MagicMock(  # type: ignore[method-assign]
        return_value={
            "stop_loss": Decimal("90"),
            "take_profit": Decimal("120"),
            "initial_stop_loss": Decimal("90"),
            "entry_order_id": "ord-entry",
            "scaled_out": False,
        }
    )
    svc.paper._latest_mark = MagicMock(  # type: ignore[method-assign]
        return_value=(Decimal("110"), datetime.now(UTC))
    )
    order = SimpleNamespace(id="ord-scale", status="filled")
    svc.paper.submit_order = MagicMock(return_value=order)  # type: ignore[method-assign]
    svc.paper._event = MagicMock()  # type: ignore[method-assign]
    svc._resolve_actor = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(user=SimpleNamespace(id="u1"))
    )
    svc._position_held_seconds = MagicMock(return_value=200.0)  # type: ignore[method-assign]
    svc._catalyst_momentum_weakened = MagicMock(return_value=False)  # type: ignore[method-assign]
    svc.audit.append = MagicMock()  # type: ignore[method-assign]
    svc._emit_decision_event = MagicMock()  # type: ignore[method-assign]

    out = svc.evaluate_paper_exits(portfolio_id=portfolio.id, actor=None)
    assert len(out) == 1
    assert out[0]["reason"] == "scale_out"
    assert svc.paper.submit_order.call_args.kwargs["quantity"] == Decimal("0.01000000")
    assert svc.paper.submit_order.call_args.kwargs["side"] == "sell"


def test_evaluate_paper_exits_uses_ratcheted_stop() -> None:
    db = MagicMock()
    svc = PaperTrainingService(db)
    portfolio = SimpleNamespace(
        id="p1",
        kill_switch_active=False,
        owner_user_id="u1",
    )
    db.get.return_value = portfolio
    pos = SimpleNamespace(
        symbol="BTC-USD",
        quantity=Decimal("0.01"),
        average_cost=Decimal("100"),
    )
    svc.paper.list_positions = MagicMock(return_value=[pos])  # type: ignore[method-assign]
    svc.paper._exit_plan_levels = MagicMock(  # type: ignore[method-assign]
        return_value={
            "stop_loss": Decimal("107.5"),
            "take_profit": Decimal("120"),
            "entry_order_id": "ord-entry",
        }
    )
    svc.paper._latest_mark = MagicMock(  # type: ignore[method-assign]
        return_value=(Decimal("107"), datetime.now(UTC))
    )
    order = SimpleNamespace(id="ord3", status="filled")
    svc.paper.submit_order = MagicMock(return_value=order)  # type: ignore[method-assign]
    svc.paper._event = MagicMock()  # type: ignore[method-assign]
    svc._resolve_actor = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(user=SimpleNamespace(id="u1"))
    )
    svc.audit.append = MagicMock()  # type: ignore[method-assign]

    out = svc.evaluate_paper_exits(portfolio_id=portfolio.id, actor=None)
    assert len(out) == 1
    assert out[0]["reason"] == "stop_loss"


def test_evaluate_paper_exits_runner_bank_after_scale_out() -> None:
    """Founder recycles capital: close scaled runner at +1.5R."""
    from app.services.paper_training_service import FOUNDER_LEARNING_DESK_NAME

    db = MagicMock()
    svc = PaperTrainingService(db)
    portfolio = SimpleNamespace(
        id="p1",
        name=FOUNDER_LEARNING_DESK_NAME,
        kill_switch_active=False,
        owner_user_id="u1",
    )
    db.get.return_value = portfolio
    pos = SimpleNamespace(
        id="pos1",
        symbol="SOL-USD",
        quantity=Decimal("0.5"),
        average_cost=Decimal("100"),
    )
    svc.paper.list_positions = MagicMock(return_value=[pos])  # type: ignore[method-assign]
    svc.paper._exit_plan_levels = MagicMock(  # type: ignore[method-assign]
        return_value={
            "stop_loss": Decimal("107.5"),
            "take_profit": Decimal("120"),
            "initial_stop_loss": Decimal("90"),
            "entry_order_id": "ord-entry",
            "scaled_out": True,
        }
    )
    # +1.6R with risk 10
    svc.paper._latest_mark = MagicMock(  # type: ignore[method-assign]
        return_value=(Decimal("116"), datetime.now(UTC))
    )
    order = SimpleNamespace(id="ord-bank", status="filled")
    svc.paper.submit_order = MagicMock(return_value=order)  # type: ignore[method-assign]
    svc.paper._event = MagicMock()  # type: ignore[method-assign]
    svc._resolve_actor = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(user=SimpleNamespace(id="u1"))
    )
    svc._position_held_seconds = MagicMock(return_value=900.0)  # type: ignore[method-assign]
    svc._catalyst_momentum_weakened = MagicMock(return_value=False)  # type: ignore[method-assign]
    svc.audit.append = MagicMock()  # type: ignore[method-assign]
    svc._emit_decision_event = MagicMock()  # type: ignore[method-assign]

    out = svc.evaluate_paper_exits(portfolio_id=portfolio.id, actor=None)
    assert len(out) == 1
    assert out[0]["reason"] == "runner_bank"


def test_evaluate_paper_exits_refuses_stale_mark() -> None:
    db = MagicMock()
    svc = PaperTrainingService(db)
    portfolio = SimpleNamespace(
        id="p1", name="Lab Book", kill_switch_active=False, owner_user_id="u1"
    )
    db.get.return_value = portfolio
    pos = SimpleNamespace(
        symbol="BTC-USD", quantity=Decimal("0.01"), average_cost=Decimal("100")
    )
    svc.paper.list_positions = MagicMock(return_value=[pos])  # type: ignore[method-assign]
    svc.paper._exit_plan_levels = MagicMock(  # type: ignore[method-assign]
        return_value={
            "stop_loss": Decimal("95"),
            "take_profit": Decimal("110"),
            "strategy_key": "range_micro",
        }
    )
    svc.paper._latest_mark = MagicMock(  # type: ignore[method-assign]
        return_value=(Decimal("90"), datetime.now(UTC) - timedelta(minutes=9))
    )
    svc.paper.submit_order = MagicMock()  # type: ignore[method-assign]
    svc._resolve_actor = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(user=SimpleNamespace(id="u1"))
    )
    svc._position_held_seconds = MagicMock(return_value=30.0)  # type: ignore[method-assign]

    assert svc.evaluate_paper_exits(portfolio_id=portfolio.id) == []
    svc.paper.submit_order.assert_not_called()


def test_micro_time_exit_recycles_position_on_fresh_mark() -> None:
    db = MagicMock()
    svc = PaperTrainingService(db)
    portfolio = SimpleNamespace(
        id="p1", name="Founder Learning Desk", kill_switch_active=False, owner_user_id="u1"
    )
    db.get.return_value = portfolio
    pos = SimpleNamespace(
        id="pos1",
        symbol="APE-USD",
        quantity=Decimal("10"),
        average_cost=Decimal("1"),
    )
    svc.paper.list_positions = MagicMock(return_value=[pos])  # type: ignore[method-assign]
    svc.paper._exit_plan_levels = MagicMock(  # type: ignore[method-assign]
        return_value={
            "stop_loss": Decimal("0.985"),
            "take_profit": Decimal("1.0225"),
            "initial_stop_loss": Decimal("0.985"),
            "entry_order_id": "entry1",
            "scaled_out": False,
            "strategy_key": "range_micro",
        }
    )
    svc.paper._latest_mark = MagicMock(  # type: ignore[method-assign]
        return_value=(Decimal("1.001"), datetime.now(UTC))
    )
    svc._position_held_seconds = MagicMock(return_value=14401.0)  # type: ignore[method-assign]
    svc.paper.submit_order = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(id="exit1", status="filled")
    )
    svc.paper._event = MagicMock()  # type: ignore[method-assign]
    svc._resolve_actor = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(user=SimpleNamespace(id="u1"))
    )
    svc.audit.append = MagicMock()  # type: ignore[method-assign]
    svc._emit_decision_event = MagicMock()  # type: ignore[method-assign]

    out = svc.evaluate_paper_exits(
        portfolio_id=portfolio.id,
        allowed_strategy_keys={"range_micro", "trend_pullback_micro"},
    )
    assert out[0]["reason"] == "micro_time_exit"


def test_stale_mark_still_time_exits_overdue_micro() -> None:
    """8m stop/target freshness must not freeze a 4h+ micro slot (ETHFI deadlock)."""
    db = MagicMock()
    svc = PaperTrainingService(db)
    portfolio = SimpleNamespace(
        id="p1",
        name="Founder Learning Desk",
        kill_switch_active=False,
        owner_user_id="u1",
    )
    db.get.return_value = portfolio
    pos = SimpleNamespace(
        id="pos1",
        symbol="ETHFI-USD",
        quantity=Decimal("153"),
        average_cost=Decimal("0.627"),
    )
    svc.paper.list_positions = MagicMock(return_value=[pos])  # type: ignore[method-assign]
    svc.paper._exit_plan_levels = MagicMock(  # type: ignore[method-assign]
        return_value={
            "stop_loss": Decimal("0.617"),
            "take_profit": Decimal("0.646"),
            "initial_stop_loss": Decimal("0.617"),
            "entry_order_id": "entry1",
            "scaled_out": False,
            "strategy_key": "trend_pullback_micro",
        }
    )
    svc.paper._latest_mark = MagicMock(  # type: ignore[method-assign]
        return_value=(Decimal("0.631"), datetime.now(UTC) - timedelta(minutes=20))
    )
    svc._position_held_seconds = MagicMock(return_value=14401.0)  # type: ignore[method-assign]
    svc.paper.submit_order = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(id="exit1", status="filled")
    )
    svc.paper._event = MagicMock()  # type: ignore[method-assign]
    svc._resolve_actor = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(user=SimpleNamespace(id="u1"))
    )
    svc.audit.append = MagicMock()  # type: ignore[method-assign]
    svc._emit_decision_event = MagicMock()  # type: ignore[method-assign]

    out = svc.evaluate_paper_exits(
        portfolio_id=portfolio.id,
        allowed_strategy_keys={"range_micro", "trend_pullback_micro"},
    )
    assert out[0]["reason"] == "micro_time_exit"
    svc.paper.submit_order.assert_called_once()


def test_exit_strategy_lane_filter_prevents_cross_worker_ownership() -> None:
    db = MagicMock()
    svc = PaperTrainingService(db)
    portfolio = SimpleNamespace(
        id="p1", name="Lab Book", kill_switch_active=False, owner_user_id="u1"
    )
    db.get.return_value = portfolio
    pos = SimpleNamespace(
        symbol="APE-USD", quantity=Decimal("10"), average_cost=Decimal("1")
    )
    svc.paper.list_positions = MagicMock(return_value=[pos])  # type: ignore[method-assign]
    svc.paper._exit_plan_levels = MagicMock(  # type: ignore[method-assign]
        return_value={
            "stop_loss": Decimal("0.98"),
            "take_profit": Decimal("1.03"),
            "strategy_key": "range_micro",
        }
    )
    svc.paper.submit_order = MagicMock()  # type: ignore[method-assign]
    svc._resolve_actor = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(user=SimpleNamespace(id="u1"))
    )

    assert svc.evaluate_paper_exits(
        portfolio_id=portfolio.id,
        excluded_strategy_keys={"range_micro", "trend_pullback_micro"},
    ) == []
    svc.paper.submit_order.assert_not_called()
