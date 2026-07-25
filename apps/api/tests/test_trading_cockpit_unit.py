"""Unit tests for Trading Cockpit helpers (no DB)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.services.market_scan_service import MarketScanService, _as_iso


def test_as_iso_json_safe() -> None:
    assert _as_iso(None) is None
    assert _as_iso("2026-07-25T12:00:00+00:00") == "2026-07-25T12:00:00+00:00"
    dt = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
    assert _as_iso(dt) == dt.isoformat()


def test_wall_status_labels() -> None:
    assert MarketScanService._wall_status(None, False, 10) == "Waiting for Data"
    assert MarketScanService._wall_status(None, False, 40) == "Scanning"
    assert MarketScanService._wall_status(None, True, 40) == "Trade Open"
    watching = SimpleNamespace(stage="Watching")
    assert MarketScanService._wall_status(watching, False, 40) == "Watching"
    risk = SimpleNamespace(stage="Risk Review")
    assert MarketScanService._wall_status(risk, False, 40) == "Risk Check"


def test_watch_narrative_expired() -> None:
    svc = MarketScanService(db=None)  # type: ignore[arg-type]
    cand = SimpleNamespace(
        stage="Expired",
        symbol="BTC-USD",
        entry_zone=Decimal("100"),
        current_price=Decimal("100"),
        timeframe="15m",
    )
    out = svc._watch_narrative(
        cand=cand,  # type: ignore[arg-type]
        watched_seconds=45 * 60,
        next_eval_in=None,
        expire_in=0,
    )
    assert "expired" in out["statement"].lower()
    assert "no trade" in out["statement"].lower()


def test_watch_narrative_active_countdown() -> None:
    svc = MarketScanService(db=None)  # type: ignore[arg-type]
    cand = SimpleNamespace(
        stage="Watching",
        symbol="ETH-USD",
        entry_zone=Decimal("3200.5"),
        current_price=Decimal("3200.5"),
        timeframe="15m",
    )
    out = svc._watch_narrative(
        cand=cand,  # type: ignore[arg-type]
        watched_seconds=12 * 60,
        next_eval_in=4 * 60 + 18,
        expire_in=30 * 60,
    )
    assert "Watching for 12 minutes" in out["statement"]
    assert "ETH-USD" in out["statement"]
    assert "4:18" in out["statement"]


def test_scan_interval_is_one_minute() -> None:
    from app.services.market_scan_service import SCAN_INTERVAL

    assert SCAN_INTERVAL == timedelta(minutes=1)


def test_short_timeframe_preference_and_candle_lengths() -> None:
    from app.services.market_scan_service import (
        TIMEFRAME_PREF,
        CANDIDATE_WATCH_TTL,
        candle_length_for,
    )

    assert TIMEFRAME_PREF[0] == "1m"
    assert TIMEFRAME_PREF[1] == "5m"
    assert candle_length_for("1m") == timedelta(minutes=1)
    assert candle_length_for("5m") == timedelta(minutes=5)
    assert CANDIDATE_WATCH_TTL == timedelta(minutes=20)
