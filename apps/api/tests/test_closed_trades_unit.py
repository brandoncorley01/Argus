"""Unit-style checks for closed-trade replay math (no DB)."""

from decimal import Decimal


def replay_sell_realized(
    fills: list[tuple[str, Decimal, Decimal]],
) -> list[Decimal]:
    """Mirror list_closed_trades average-cost math for a single symbol."""
    qty = Decimal("0")
    avg = Decimal("0")
    out: list[Decimal] = []
    for side, q, px in fills:
        if side == "buy":
            new_qty = qty + q
            if new_qty > 0:
                avg = ((qty * avg) + (q * px)) / new_qty
            qty = new_qty
        else:
            out.append((px - avg) * q)
            qty -= q
            if qty <= 0:
                qty = Decimal("0")
                avg = Decimal("0")
    return out


def test_closed_trade_realized_pnl() -> None:
    pnls = replay_sell_realized(
        [
            ("buy", Decimal("2"), Decimal("100")),
            ("sell", Decimal("1"), Decimal("110")),
            ("sell", Decimal("1"), Decimal("90")),
        ]
    )
    assert pnls[0] == Decimal("10")
    assert pnls[1] == Decimal("-10")
