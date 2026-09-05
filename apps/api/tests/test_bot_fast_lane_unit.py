"""Bot fast-lane: commercial-style strategies must actually enter paper."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.paper_training_service import (
    INTERVAL_DCA_SECONDS,
    INTERVAL_DCA_SYMBOLS,
    SIMPLE_BOT_STRATEGIES,
    PaperTrainingService,
)


def test_simple_bot_strategies_cover_commercial_families() -> None:
    assert SIMPLE_BOT_STRATEGIES == frozenset({"dca", "trend_momentum", "grid_trading"})
    assert INTERVAL_DCA_SECONDS == 4 * 60 * 60
    assert "BTC-USD" in INTERVAL_DCA_SYMBOLS


def test_interval_dca_noop_when_coaching() -> None:
    db = MagicMock()
    svc = PaperTrainingService(db)
    settings = SimpleNamespace(mode="coaching", default_notional=Decimal("150"))
    svc.get_or_create_settings = MagicMock(return_value=settings)  # type: ignore[method-assign]

    out = svc.maybe_interval_dca(portfolio_id=SimpleNamespace(), actor=None)  # type: ignore[arg-type]

    assert out == []


def test_bot_fast_lane_constant_used_for_entry_bypass() -> None:
    # Guard against regressions that re-bury bot families under memory court.
    import inspect

    from app.services import paper_training_service as mod

    src = inspect.getsource(mod.PaperTrainingService.maybe_auto_enter_from_scan)
    assert "SIMPLE_BOT_STRATEGIES" in src
    assert "bot_fast_lane" in src
    assert "if (not bot_fast_lane)" in src or "if not bot_fast_lane" in src
