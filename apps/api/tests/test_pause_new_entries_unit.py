"""Unit tests for pause-new-entries entry classification (no DB)."""

from decimal import Decimal

from app.services.paper_trading_service import is_new_entry_order


def test_buy_on_flat_is_entry() -> None:
    assert is_new_entry_order(
        position_qty=Decimal("0"), side="buy", order_qty=Decimal("1")
    )


def test_buy_on_long_is_entry() -> None:
    assert is_new_entry_order(
        position_qty=Decimal("2"), side="buy", order_qty=Decimal("1")
    )


def test_buy_on_short_is_not_entry() -> None:
    assert not is_new_entry_order(
        position_qty=Decimal("-2"), side="buy", order_qty=Decimal("1")
    )


def test_sell_reducing_long_is_not_entry() -> None:
    assert not is_new_entry_order(
        position_qty=Decimal("2"), side="sell", order_qty=Decimal("1")
    )


def test_sell_oversize_is_entry() -> None:
    assert is_new_entry_order(
        position_qty=Decimal("1"), side="sell", order_qty=Decimal("2")
    )


def test_sell_on_flat_is_entry() -> None:
    assert is_new_entry_order(
        position_qty=Decimal("0"), side="sell", order_qty=Decimal("1")
    )
