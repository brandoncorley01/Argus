"""Learning-desk sizing economics — meaningful dollar targets, not pennies."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.paper_opportunity_detectors import _rr_levels
from app.services.paper_training_service import (
    LEARNING_DEFAULT_NOTIONAL,
    LEGACY_TINY_NOTIONAL,
    MIN_EXPECTED_REWARD_USD,
    MIN_STOP_DISTANCE_PCT,
    PaperTrainingService,
    expected_reward_usd,
    normalize_exit_levels,
)


def test_learning_default_notional_is_meaningful() -> None:
    assert LEARNING_DEFAULT_NOTIONAL == Decimal("100")
    assert LEARNING_DEFAULT_NOTIONAL > LEGACY_TINY_NOTIONAL


def test_normalize_exit_levels_widens_micro_stop() -> None:
    price = Decimal("100")
    stop, target = normalize_exit_levels(
        price, stop=Decimal("99.9"), target=Decimal("100.2")
    )
    assert price - stop == price * MIN_STOP_DISTANCE_PCT
    assert target == price + (price - stop) * Decimal("2")
    reward = expected_reward_usd(
        price=price, target=target, notional=LEARNING_DEFAULT_NOTIONAL
    )
    assert reward >= MIN_EXPECTED_REWARD_USD


def test_expected_reward_at_default_notional_meets_floor() -> None:
    price = Decimal("50")
    stop, target = normalize_exit_levels(price, None, None)
    reward = expected_reward_usd(
        price=price, target=target, notional=LEARNING_DEFAULT_NOTIONAL
    )
    # 1.5% risk * 2R * $100 = $3.00
    assert reward == Decimal("3.00")


def test_detector_rr_levels_respect_min_stop() -> None:
    price = Decimal("200")
    stop, target = _rr_levels(price, stop=Decimal("199.8"))
    assert price - stop == price * Decimal("0.015")
    assert target == price + (price - stop) * Decimal("2")


def test_upgrade_legacy_tiny_notional_when_cash_allows() -> None:
    db = MagicMock()
    svc = PaperTrainingService(db)
    portfolio = SimpleNamespace(
        id="p1",
        cash_balance=Decimal("300"),
        reserved_cash=Decimal("0"),
        owner_user_id="u1",
    )
    settings = SimpleNamespace(default_notional=Decimal("30"))
    svc.get_or_create_settings = MagicMock(return_value=settings)  # type: ignore[method-assign]
    svc.audit.append = MagicMock()  # type: ignore[method-assign]

    svc._upgrade_legacy_tiny_notional(portfolio)  # type: ignore[arg-type]

    assert settings.default_notional == LEARNING_DEFAULT_NOTIONAL
    svc.audit.append.assert_called_once()
    db.commit.assert_called_once()


def test_upgrade_skips_when_cash_below_new_notional() -> None:
    db = MagicMock()
    svc = PaperTrainingService(db)
    portfolio = SimpleNamespace(
        id="p1",
        cash_balance=Decimal("40"),
        reserved_cash=Decimal("0"),
        owner_user_id="u1",
    )
    settings = SimpleNamespace(default_notional=Decimal("30"))
    svc.get_or_create_settings = MagicMock(return_value=settings)  # type: ignore[method-assign]
    svc.audit.append = MagicMock()  # type: ignore[method-assign]

    svc._upgrade_legacy_tiny_notional(portfolio)  # type: ignore[arg-type]

    assert settings.default_notional == Decimal("30")
    svc.audit.append.assert_not_called()
    db.commit.assert_not_called()
