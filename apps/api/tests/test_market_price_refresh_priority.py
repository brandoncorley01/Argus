"""Price refresh priority protects open paper risk from universe caps."""

from app.services.market_price_refresh_service import prioritized_refresh_symbols


def test_founder_open_symbols_survive_refresh_cap() -> None:
    symbols = prioritized_refresh_symbols(
        active_symbols=[f"ASSET{i}-USD" for i in range(100)],
        founder_open_symbols=["JASMY-USD", "APE-USD", "BONK-USD"],
        other_open_symbols=["LAB-USD"],
        limit=8,
    )

    assert symbols[:3] == ["JASMY-USD", "APE-USD", "BONK-USD"]
    assert len(symbols) == 8


def test_refresh_priority_deduplicates_open_and_active_symbols() -> None:
    symbols = prioritized_refresh_symbols(
        active_symbols=["BTC-USD", "APE-USD", "SOL-USD"],
        founder_open_symbols=["ape-usd"],
        other_open_symbols=[],
        limit=10,
    )

    assert symbols.count("APE-USD") == 1
    assert symbols[0] == "APE-USD"
