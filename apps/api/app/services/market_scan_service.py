"""Observation-only market scan / opportunity evaluation for Command Center.

Evaluates registered instruments against persisted OHLCV bars using the
research `sma_crossover` strategy as a signal probe. Never submits orders,
never invents prices, and never blocks trading on failure.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.models.market_intelligence import MarketInstrument, MarketOhlcvBar
from app.models.market_scan import MarketScanCandidate, MarketScanCycle, MarketScanEvent
from app.models.paper_trading import PaperPortfolio, PaperPosition
from app.services.strategy_engine import Bar, SmaCrossoverStrategy

SCAN_INTERVAL = timedelta(minutes=1)
# Short-TF practice (1m/5m): marks older than this need a price refresh.
STALE_BAR = timedelta(minutes=5)
MIN_BARS = 25
EVENT_RETENTION = timedelta(days=7)
MAX_EVENTS_PER_CYCLE = 120
STRATEGY_KEY = "sma_crossover"
# Prefer 1m/5m charts so Argus re-evaluates often (not stuck on 15m closes).
TIMEFRAME_PREF = ("1m", "5m", "15m")
# Server-side watch window — short for 1m/5m cadence (was 20m; felt stuck).
CANDIDATE_WATCH_TTL = timedelta(minutes=8)
# Default candle length when timeframe is unknown.
CANDLE_LENGTH = timedelta(minutes=1)


def candle_length_for(timeframe: str | None) -> timedelta:
    """Map stored timeframe label to candle duration for next-eval countdowns."""
    tf = (timeframe or "1m").lower()
    if tf in {"1m", "1min", "1"}:
        return timedelta(minutes=1)
    if tf in {"5m", "5min", "5"}:
        return timedelta(minutes=5)
    if tf in {"15m", "15min", "15"}:
        return timedelta(minutes=15)
    if tf in {"1h", "60m"}:
        return timedelta(hours=1)
    if tf in {"1d", "24h"}:
        return timedelta(days=1)
    return CANDLE_LENGTH


class MarketScanError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_iso(value: Any) -> str | None:
    """JSON-safe timestamp for EOC / RSC props (never leave raw datetime in dicts)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return str(value)


class MarketScanService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def latest_cycle(self) -> MarketScanCycle | None:
        return self.db.scalar(
            select(MarketScanCycle).order_by(desc(MarketScanCycle.started_at)).limit(1)
        )

    def list_candidates(self, *, limit: int = 5) -> list[MarketScanCandidate]:
        safe = min(max(limit, 1), 50)
        latest = self.latest_cycle()
        if latest is None:
            return []
        return list(
            self.db.scalars(
                select(MarketScanCandidate)
                .where(MarketScanCandidate.cycle_id == latest.id)
                .order_by(
                    desc(MarketScanCandidate.score),
                    MarketScanCandidate.symbol.asc(),
                )
                .limit(safe)
            )
        )

    def list_events(self, *, limit: int = 40) -> list[MarketScanEvent]:
        safe = min(max(limit, 1), 200)
        return list(
            self.db.scalars(
                select(MarketScanEvent)
                .order_by(desc(MarketScanEvent.occurred_at))
                .limit(safe)
            )
        )

    def status_snapshot(self) -> dict[str, Any]:
        cycle = self.latest_cycle()
        now = _utcnow()
        instruments = list(
            self.db.scalars(
                select(MarketInstrument).where(MarketInstrument.is_active.is_(True))
            )
        )
        # Prefer short-TF closes for "feed age" so 15m leftovers do not look current.
        latest_bar_at = self.db.scalar(
            select(MarketOhlcvBar.close_time)
            .where(MarketOhlcvBar.timeframe.in_(("1m", "5m")))
            .order_by(desc(MarketOhlcvBar.close_time))
            .limit(1)
        )
        if latest_bar_at is None:
            latest_bar_at = self.db.scalar(
                select(MarketOhlcvBar.close_time)
                .order_by(desc(MarketOhlcvBar.close_time))
                .limit(1)
            )
        pause = self.db.scalar(
            select(PaperPortfolio.pause_new_entries_active)
            .where(PaperPortfolio.status == "active")
            .limit(1)
        )
        kill = self.db.scalar(
            select(PaperPortfolio.kill_switch_active)
            .where(PaperPortfolio.status == "active")
            .limit(1)
        )

        scanner_state = "Between Cycles"
        if cycle is None:
            scanner_state = "Failed" if not instruments else "Between Cycles"
        elif cycle.status == "running":
            scanner_state = "Scanning"
        elif cycle.status == "failed":
            scanner_state = "Failed"
        elif cycle.completed_at and now - cycle.completed_at > SCAN_INTERVAL * 3:
            scanner_state = "Delayed"
        elif kill:
            scanner_state = "Paused"
        elif pause:
            scanner_state = "Between Cycles"

        data_age_seconds: int | None = None
        if latest_bar_at is not None:
            data_age_seconds = max(0, int((now - latest_bar_at).total_seconds()))

        last_decision = self.db.scalar(
            select(MarketScanEvent)
            .where(MarketScanEvent.component == "strategy_evaluator")
            .order_by(desc(MarketScanEvent.occurred_at))
            .limit(1)
        )

        # Live open count — Founder book only when possible. Never sum fixture
        # portfolios (that made Live Desk show "11 open" while Active Trades
        # showed 2 real positions).
        open_positions_live, _open_syms = self._founder_open_positions()
        pipeline = dict((cycle.pipeline_counts if cycle else {}) or {})
        pipeline["positions"] = open_positions_live

        return {
            "scanner_state": scanner_state,
            "cycle": self._cycle_dict(cycle) if cycle else None,
            "symbols_monitored": len(instruments),
            "market_data_at": latest_bar_at,
            "market_data_age_seconds": data_age_seconds,
            "market_data_stale": (
                data_age_seconds is None or data_age_seconds > int(STALE_BAR.total_seconds())
            ),
            "pause_new_entries_active": bool(pause),
            "kill_switch_active": bool(kill),
            "trading_allowed": not bool(kill) and not bool(pause),
            "last_decision": self._event_dict(last_decision) if last_decision else None,
            "pipeline_counts": pipeline,
            "open_positions_live": open_positions_live,
            "rejection_counts": (cycle.rejection_counts if cycle else {}) or {},
            "next_scheduled_at": self._next_scan_at(
                cycle, now=now, scanner_state=scanner_state
            ),
            "worker_note": (
                "Argus auto-scans every minute on 1m/5m charts while running. "
                "Start once; it keeps scanning until you Stop. "
                "Home reads persisted cycles only — it does not invent activity."
            ),
        }

    @staticmethod
    def _next_scan_at(
        cycle: MarketScanCycle | None,
        *,
        now: datetime,
        scanner_state: str,
    ) -> datetime | None:
        """Forward-looking next pass time while Argus is running.

        Cron often returns the same cycle within the interval; that can leave
        next_scheduled_at in the past and make the UI look like Argus stopped.
        Keep the countdown on the next due slot until Delayed/Failed/Paused.
        """
        if cycle is None:
            return None
        if scanner_state in {"Failed", "Paused"}:
            return cycle.next_scheduled_at
        if cycle.status == "running":
            return cycle.next_scheduled_at or (now + SCAN_INTERVAL)
        completed = cycle.completed_at
        if completed is None:
            return cycle.next_scheduled_at
        elapsed = max(0.0, (now - completed).total_seconds())
        interval = SCAN_INTERVAL.total_seconds()
        slots = int(elapsed // interval) + 1
        return completed + timedelta(seconds=slots * interval)

    def run_scan_cycle(self, *, force: bool = False) -> MarketScanCycle:
        """Run one scan over active instruments. Safe to call from worker or API."""
        try:
            self._prune_old_events()
            latest = self.latest_cycle()
            now = _utcnow()
            if (
                not force
                and latest is not None
                and latest.completed_at is not None
                and now - latest.completed_at < SCAN_INTERVAL
            ):
                due = latest.completed_at + SCAN_INTERVAL
                if latest.next_scheduled_at is None or latest.next_scheduled_at < due:
                    latest.next_scheduled_at = due
                    self.db.commit()
                return latest

            # Keep 1m/5m bars fresh so each minute scan has real short-TF data.
            self._ensure_short_tf_prices(now)

            correlation_id = f"scan-{now.strftime('%Y%m%dT%H%M')}"
            cycle = MarketScanCycle(
                status="running",
                timeframe="1m",
                strategy_key=STRATEGY_KEY,
                correlation_id=correlation_id,
                started_at=now,
                next_scheduled_at=now + SCAN_INTERVAL,
                detail={},
            )
            self.db.add(cycle)
            self.db.flush()

            self._emit(
                cycle,
                component="market_scanner",
                outcome="started",
                title="Scan cycle started",
                detail="Evaluating registered instruments against persisted OHLCV bars.",
                correlation_id=correlation_id,
            )

            instruments = list(
                self.db.scalars(
                    select(MarketInstrument)
                    .where(MarketInstrument.is_active.is_(True))
                    .order_by(MarketInstrument.symbol.asc())
                )
            )
            pause = bool(
                self.db.scalar(
                    select(PaperPortfolio.pause_new_entries_active)
                    .where(PaperPortfolio.status == "active")
                    .limit(1)
                )
            )
            kill = bool(
                self.db.scalar(
                    select(PaperPortfolio.kill_switch_active)
                    .where(PaperPortfolio.status == "active")
                    .limit(1)
                )
            )
            cycle.symbols_total = len(instruments)
            rejection_counts: dict[str, int] = {}
            pipeline = {
                "scanned": 0,
                "watching": 0,
                "qualified": 0,
                "risk_review": 0,
                "approved": 0,
                "orders": 0,
                "positions": 0,
                "rejected": 0,
            }
            candidates_found = 0
            events_emitted = 1

            if not instruments:
                cycle.status = "failed"
                cycle.completed_at = _utcnow()
                cycle.detail = {"error": "no_active_instruments"}
                self._emit(
                    cycle,
                    component="market_scanner",
                    outcome="failed",
                    title="Scan failed — no instruments",
                    detail="Register market instruments before the scanner can evaluate setups.",
                    reason_code="no_instruments",
                    correlation_id=correlation_id,
                )
                self.db.commit()
                self.db.refresh(cycle)
                return cycle

            strategy = SmaCrossoverStrategy()
            for inst in instruments:
                if events_emitted >= MAX_EVENTS_PER_CYCLE:
                    break
                cycle.current_symbol = inst.symbol
                self.db.flush()

                if events_emitted < MAX_EVENTS_PER_CYCLE:
                    self._emit(
                        cycle,
                        component="market_scanner",
                        symbol=inst.symbol,
                        outcome="info",
                        title=f"Scanning {inst.symbol}",
                        detail=f"Loading latest candles for {inst.symbol}.",
                        stage="Discovered",
                        correlation_id=correlation_id,
                    )
                    events_emitted += 1

                bars, timeframe, bar_close_time = self._load_bars(inst.id)
                pipeline["scanned"] += 1
                cycle.symbols_scanned = pipeline["scanned"]

                if len(bars) < MIN_BARS:
                    code = "insufficient_history" if bars else "insufficient_history"
                    rejection_counts[code] = rejection_counts.get(code, 0) + 1
                    pipeline["rejected"] += 1
                    self._add_candidate(
                        cycle,
                        symbol=inst.symbol,
                        timeframe=timeframe or "15m",
                        bias="Neutral",
                        stage="Rejected",
                        score=Decimal("0"),
                        risk_status="blocked",
                        reason_code=code,
                        reason_text=(
                            f"Need at least {MIN_BARS} recent price points; found {len(bars)}."
                            if bars
                            else "No recent price history is stored for this market yet."
                        ),
                        price=bars[-1].close if bars else None,
                        market_data_at=bar_close_time,
                    )
                    if events_emitted < MAX_EVENTS_PER_CYCLE:
                        self._emit(
                            cycle,
                            component="strategy_evaluator",
                            symbol=inst.symbol,
                            outcome="rejected",
                            title=f"Not enough price history for {inst.symbol}",
                            detail=(
                                f"Argus needs {MIN_BARS} recent price points before it can "
                                f"evaluate this strategy safely (found {len(bars)})."
                                if bars
                                else (
                                    "No recent price history is stored yet. "
                                    "Refresh recent prices, then scan again."
                                )
                            ),
                            reason_code=code,
                            stage="Rejected",
                            strategy_key=STRATEGY_KEY,
                            correlation_id=correlation_id,
                        )
                        events_emitted += 1
                    continue

                assert bar_close_time is not None
                age = now - bar_close_time
                if age > STALE_BAR:
                    rejection_counts["stale_data"] = rejection_counts.get("stale_data", 0) + 1
                    pipeline["rejected"] += 1
                    price = Decimal(str(bars[-1].close))
                    self._add_candidate(
                        cycle,
                        symbol=inst.symbol,
                        timeframe=timeframe or "15m",
                        bias="Neutral",
                        stage="Rejected",
                        score=Decimal("5"),
                        risk_status="blocked",
                        reason_code="stale_data",
                        reason_text=f"Latest bar is {int(age.total_seconds() // 60)} minutes old.",
                        price=price,
                        market_data_at=bar_close_time,
                    )
                    if events_emitted < MAX_EVENTS_PER_CYCLE:
                        self._emit(
                            cycle,
                            component="strategy_evaluator",
                            symbol=inst.symbol,
                            outcome="rejected",
                            title=f"Stale data for {inst.symbol}",
                            detail="Market data older than freshness policy; no entry considered.",
                            reason_code="stale_data",
                            stage="Rejected",
                            strategy_key=STRATEGY_KEY,
                            correlation_id=correlation_id,
                        )
                        events_emitted += 1
                    continue

                # Volume gate only when the bars carry non-null source volume
                # in the ORM payload path — zero-filled research bars skip this.
                orm_rows, _, _ = self._load_bar_rows(inst.id, limit=5)
                source_vols = [r.volume for r in orm_rows if r.volume is not None]
                if len(source_vols) >= 3 and all(v <= 0 for v in source_vols):
                    rejection_counts["low_liquidity"] = rejection_counts.get("low_liquidity", 0) + 1
                    pipeline["rejected"] += 1
                    price = Decimal(str(bars[-1].close))
                    self._add_candidate(
                        cycle,
                        symbol=inst.symbol,
                        timeframe=timeframe or "15m",
                        bias="Neutral",
                        stage="Rejected",
                        score=Decimal("10"),
                        risk_status="blocked",
                        reason_code="low_liquidity",
                        reason_text="Recent bar volume is zero.",
                        price=price,
                        market_data_at=bar_close_time,
                    )
                    if events_emitted < MAX_EVENTS_PER_CYCLE:
                        self._emit(
                            cycle,
                            component="strategy_evaluator",
                            symbol=inst.symbol,
                            outcome="rejected",
                            title=f"Candidate rejected for {inst.symbol}",
                            detail="Volume was insufficient on recent bars.",
                            reason_code="low_liquidity",
                            stage="Rejected",
                            strategy_key=STRATEGY_KEY,
                            correlation_id=correlation_id,
                        )
                        events_emitted += 1
                    continue

                if events_emitted < MAX_EVENTS_PER_CYCLE:
                    self._emit(
                        cycle,
                        component="strategy_evaluator",
                        symbol=inst.symbol,
                        outcome="info",
                        title=f"Evaluating {STRATEGY_KEY} on {inst.symbol}",
                        detail=f"Calculating SMA crossover on {timeframe} timeframe.",
                        stage="Evaluating",
                        strategy_key=STRATEGY_KEY,
                        correlation_id=correlation_id,
                    )
                    events_emitted += 1

                i = len(bars) - 1
                try:
                    exposure = strategy.target_exposure(
                        bars, i, {"fast": 5, "slow": 20}
                    )
                except Exception as exc:  # noqa: BLE001 — record and continue
                    rejection_counts["weak_signal"] = rejection_counts.get("weak_signal", 0) + 1
                    pipeline["rejected"] += 1
                    self._add_candidate(
                        cycle,
                        symbol=inst.symbol,
                        timeframe=timeframe or "15m",
                        bias="Neutral",
                        stage="Rejected",
                        score=Decimal("0"),
                        risk_status="blocked",
                        reason_code="weak_signal",
                        reason_text=str(exc)[:240],
                        price=Decimal(str(bars[-1].close)),
                        market_data_at=bar_close_time,
                    )
                    continue

                price = Decimal(str(bars[-1].close))
                if exposure > 0:
                    # Bullish probe — observation only; no order placement.
                    score = Decimal("70") + Decimal(str(min(25.0, abs(exposure) * 25)))
                    stage = "Watching"
                    pipeline["watching"] += 1
                    pipeline["qualified"] += 1
                    candidates_found += 1
                    # Risk review is informational: kill/pause block approval.
                    if kill:
                        stage = "Rejected"
                        risk_status = "blocked"
                        reason_code = "execution_unavailable"
                        reason_text = "Paper kill switch is active."
                        rejection_counts[reason_code] = rejection_counts.get(reason_code, 0) + 1
                        pipeline["rejected"] += 1
                        pipeline["watching"] = max(0, pipeline["watching"] - 1)
                        pipeline["qualified"] = max(0, pipeline["qualified"] - 1)
                        candidates_found = max(0, candidates_found - 1)
                    elif pause:
                        stage = "Risk Review"
                        risk_status = "paused"
                        reason_code = "pause_new_entries"
                        reason_text = "New entries paused; candidate held in risk review."
                        pipeline["risk_review"] += 1
                    else:
                        stage = "Watching"
                        risk_status = "clear"
                        reason_code = None
                        reason_text = (
                            "Price is rising with a stronger short-term trend. "
                            "Argus is watching for one more confirming candle."
                        )

                    # Simple structural levels from recent range (not invented targets).
                    window = bars[-20:]
                    low = min(b.low for b in window)
                    high = max(b.high for b in window)
                    stop = Decimal(str(low))
                    target = Decimal(str(high))
                    stop_d = stop if stop < price else None
                    target_d = target if target > price else None
                    # Expire watch if prior watch for this symbol already timed out.
                    prior = self._prior_watch_meta(inst.symbol)
                    watching_since = prior.get("watching_since") or _utcnow()
                    expires_at = watching_since + CANDIDATE_WATCH_TTL
                    if stage == "Watching" and _utcnow() >= expires_at:
                        stage = "Expired"
                        risk_status = "blocked"
                        reason_code = "confirmation_incomplete"
                        reason_text = (
                            f"Watching expired after "
                            f"{int(CANDIDATE_WATCH_TTL.total_seconds() // 60)} minutes "
                            "because price never confirmed the planned entry. "
                            "No trade was opened."
                        )
                        rejection_counts["confirmation_incomplete"] = (
                            rejection_counts.get("confirmation_incomplete", 0) + 1
                        )
                        pipeline["rejected"] += 1
                        pipeline["watching"] = max(0, pipeline["watching"] - 1)
                        pipeline["qualified"] = max(0, pipeline["qualified"] - 1)
                        candidates_found = max(0, candidates_found - 1)
                    detail = self._watch_detail(
                        stage=stage,
                        price=price,
                        entry=price,
                        stop=stop_d,
                        target=target_d,
                        market_data_at=bar_close_time,
                        watching_since=watching_since if stage in {
                            "Watching", "Risk Review", "Expired"
                        } else None,
                        expires_at=expires_at if stage in {
                            "Watching", "Risk Review", "Expired"
                        } else None,
                        risk_status=risk_status,
                        bars=bars,
                        timeframe=timeframe or "1m",
                    )
                    cand = self._add_candidate(
                        cycle,
                        symbol=inst.symbol,
                        timeframe=timeframe or "1m",
                        bias="Bullish",
                        stage=stage,
                        score=score,
                        risk_status=risk_status,
                        reason_code=reason_code,
                        reason_text=reason_text,
                        price=price,
                        market_data_at=bar_close_time,
                        entry_zone=price,
                        stop_loss=stop_d,
                        take_profit=target_d,
                        detail=detail,
                    )
                    if stage == "Expired":
                        try:
                            from app.services.trading_intelligence_service import (
                                TradingIntelligenceService,
                            )

                            with self.db.begin_nested():
                                TradingIntelligenceService(
                                    self.db
                                ).track_missed_opportunity(cand)
                        except Exception:  # noqa: BLE001
                            pass
                    if events_emitted < MAX_EVENTS_PER_CYCLE:
                        outcome = (
                            "watching"
                            if stage == "Watching"
                            else stage.lower().replace(" ", "_")
                        )
                        self._emit(
                            cycle,
                            component="strategy_evaluator",
                            symbol=inst.symbol,
                            outcome=outcome,
                            title=f"Candidate {stage.lower()} for {inst.symbol}",
                            detail=reason_text or "Strategy probe passed.",
                            reason_code=reason_code,
                            stage=stage,
                            strategy_key=STRATEGY_KEY,
                            correlation_id=correlation_id,
                            candidate_id=cand.id,
                        )
                        events_emitted += 1
                else:
                    rejection_counts["weak_signal"] = rejection_counts.get("weak_signal", 0) + 1
                    pipeline["rejected"] += 1
                    self._add_candidate(
                        cycle,
                        symbol=inst.symbol,
                        timeframe=timeframe or "15m",
                        # Neutral — not a short thesis (long-only never buys this).
                        bias="Neutral",
                        stage="Rejected",
                        score=Decimal("20"),
                        risk_status="clear",
                        reason_code="weak_signal",
                        reason_text=(
                            "Price is not showing a clear upward setup that meets entry rules."
                        ),
                        price=price,
                        market_data_at=bar_close_time,
                    )
                    if events_emitted < MAX_EVENTS_PER_CYCLE:
                        self._emit(
                            cycle,
                            component="strategy_evaluator",
                            symbol=inst.symbol,
                            outcome="rejected",
                            title=f"Entry rejected for {inst.symbol}",
                            detail="The move is not strong enough to meet Argus entry rules.",
                            reason_code="weak_signal",
                            stage="Rejected",
                            strategy_key=STRATEGY_KEY,
                            correlation_id=correlation_id,
                        )
                        events_emitted += 1

            # Open paper positions count toward pipeline Positions.
            open_count = len(
                list(
                    self.db.scalars(
                        select(PaperPosition).where(PaperPosition.quantity != 0)
                    )
                )
            )
            pipeline["positions"] = open_count

            cycle.status = "succeeded"
            cycle.candidates_found = candidates_found
            cycle.current_symbol = None
            cycle.rejection_counts = rejection_counts
            cycle.pipeline_counts = pipeline
            cycle.completed_at = _utcnow()
            cycle.next_scheduled_at = cycle.completed_at + SCAN_INTERVAL
            cycle.detail = {
                "strategy": STRATEGY_KEY,
                "min_bars": MIN_BARS,
                "stale_after_seconds": int(STALE_BAR.total_seconds()),
            }
            self._emit(
                cycle,
                component="market_scanner",
                outcome="completed",
                title="Scan cycle completed",
                detail=(
                    f"{cycle.symbols_scanned} symbols evaluated, "
                    f"{candidates_found} candidates found."
                ),
                correlation_id=correlation_id,
            )
            self.db.commit()
            self.db.refresh(cycle)
            return cycle
        except Exception:
            self.db.rollback()
            raise

    def record_teaching_signal(
        self,
        *,
        symbol: str,
        signal: str,
        actor_user_id: uuid.UUID | None,
        candidate_id: uuid.UUID | None = None,
        note: str | None = None,
    ) -> MarketScanEvent:
        """Persist a Founder teaching signal. Never places an order."""
        allowed = {
            "interested",
            "not_interested",
            "needs_more_data",
            "looks_wrong",
        }
        if signal not in allowed:
            raise MarketScanError(
                "invalid_signal",
                f"Teaching signal must be one of: {', '.join(sorted(allowed))}",
            )
        labels = {
            "interested": "Founder marked setup as interesting",
            "not_interested": "Founder marked setup as not interesting",
            "needs_more_data": "Founder asked for more market data",
            "looks_wrong": "Founder flagged setup as looking wrong",
        }
        cycle = self.latest_cycle()
        correlation_id = (cycle.correlation_id if cycle else uuid.uuid4().hex[:16])
        event = MarketScanEvent(
            cycle_id=cycle.id if cycle else None,
            candidate_id=candidate_id,
            component="founder_teaching",
            symbol=symbol.upper(),
            stage="Teaching",
            outcome=signal,
            reason_code=signal,
            title=labels[signal],
            detail=(note or labels[signal])[:500],
            strategy_key=None,
            correlation_id=correlation_id,
            occurred_at=_utcnow(),
            payload={"actor_user_id": str(actor_user_id) if actor_user_id else None},
        )
        self.db.add(event)
        self.db.flush()
        self.db.refresh(event)
        return event

    def plain_status_summary(self) -> dict[str, Any]:
        """Short Founder-facing sentences for the Home 'what Argus is doing' strip."""
        from app.services.plain_language import plain_rejection, readiness_action

        snap = self.status_snapshot()
        cycle = snap.get("cycle")
        candidates = self.list_candidates(limit=5)
        watching = [
            c for c in candidates if c.stage in {"Watching", "Evaluating", "Risk Review"}
        ]
        rejected = [c for c in candidates if c.stage == "Rejected"]
        symbols_total = (
            int(cycle.get("symbols_total") or 0)
            if cycle
            else snap.get("symbols_monitored") or 0
        )
        scanned = int(cycle.get("symbols_scanned") or 0) if cycle else 0
        current_symbol = cycle.get("current_symbol") if cycle else None

        if snap["kill_switch_active"]:
            headline = "Argus is paused by the emergency stop and will not open new paper trades."
        elif snap["pause_new_entries_active"]:
            headline = "Argus is paused and will not open new trades."
        elif snap["market_data_stale"] and snap.get("symbols_monitored", 0) > 0:
            headline = "Argus needs attention because market prices are outdated."
        elif snap["scanner_state"] == "Scanning":
            headline = (
                f"Argus is analyzing {current_symbol} for a possible trade."
                if current_symbol
                else "Argus is scanning crypto markets for short-term opportunities."
            )
        elif watching:
            if len(watching) == 1:
                headline = (
                    f"Argus is analyzing {watching[0].symbol} for a possible upward trade."
                    if watching[0].bias == "Bullish"
                    else f"Argus is watching {watching[0].symbol}."
                )
            else:
                headline = (
                    f"Argus found {len(watching)} possible trades and is checking their risk."
                )
        elif snap.get("pipeline_counts", {}).get("positions", 0):
            n = snap["pipeline_counts"]["positions"]
            headline = (
                f"Argus is monitoring {n} open position{'s' if n != 1 else ''}."
            )
        elif rejected and cycle:
            top = rejected[0]
            why = plain_rejection(top.reason_code, top.reason_text)
            headline = (
                f"Argus is waiting because no trades currently meet your rules. "
                f"({top.symbol}: {why})"
            )
        elif snap["scanner_state"] == "Failed":
            headline = (
                "Argus needs attention because no markets are registered yet. "
                "Press Refresh recent prices to register markets and download price history."
            )
        elif cycle and symbols_total:
            headline = (
                f"Argus is scanning {symbols_total} crypto markets for short-term opportunities."
                if scanned == 0
                else (
                    f"Argus checked {scanned} market{'s' if scanned != 1 else ''} "
                    "and is waiting because no trades currently meet your rules."
                )
            )
        else:
            headline = (
                "Argus is waiting for recent price history. "
                "Press Refresh recent prices, then Scan markets now."
            )

        next_step = None
        if snap.get("symbols_monitored", 0) == 0:
            next_step = readiness_action(
                bar_count=0, min_bars=MIN_BARS, stale=True, has_instrument=False
            )
        elif snap.get("market_data_stale"):
            next_step = readiness_action(
                bar_count=MIN_BARS, min_bars=MIN_BARS, stale=True, has_instrument=True
            )

        return {
            **snap,
            "headline": headline,
            "watching_count": len(watching),
            "rejected_count": len(rejected),
            # Only set while a cycle is actively scanning — do not freeze on
            # the first watch symbol between passes (that made Home look stuck).
            "current_market": current_symbol if snap["scanner_state"] == "Scanning" else None,
            "scan_progress": {
                "scanned": scanned,
                "total": symbols_total,
            },
            "possible_trades_found": len(watching),
            "next_step": next_step,
            "top_watching": [
                {
                    "symbol": c.symbol,
                    "stage": c.stage,
                    "reason_text": plain_rejection(c.reason_code, c.reason_text),
                    "score": c.score,
                }
                for c in watching[:3]
            ],
        }

    def bars_for_symbol(self, symbol: str, *, limit: int = 60) -> dict[str, Any]:
        inst = self.db.scalar(
            select(MarketInstrument).where(MarketInstrument.symbol == symbol.upper())
        )
        if inst is None:
            return {
                "symbol": symbol.upper(),
                "timeframe": None,
                "bars": [],
                "available": False,
            }
        bars_orm, timeframe, _ = self._load_bar_rows(inst.id, limit=limit)
        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "available": bool(bars_orm),
            "bars": [
                {
                    "open_time": b.open_time,
                    "close_time": b.close_time,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
                for b in bars_orm
            ],
        }

    def _load_bars(
        self, instrument_id: uuid.UUID
    ) -> tuple[list[Bar], str | None, datetime | None]:
        rows, timeframe, close_time = self._load_bar_rows(instrument_id, limit=120)
        bars = [
            Bar(
                open_time=r.open_time.isoformat(),
                open=float(r.open),
                high=float(r.high),
                low=float(r.low),
                close=float(r.close),
                volume=float(r.volume) if r.volume is not None else 0.0,
            )
            for r in rows
        ]
        return bars, timeframe, close_time

    def _ensure_short_tf_prices(self, now: datetime) -> None:
        """Refresh 1m/5m candles when the book is stale before a scan cycle."""
        # Only short TFs count — a fresh 15m bar must not skip a 1m refresh.
        latest_bar_at = self.db.scalar(
            select(MarketOhlcvBar.close_time)
            .where(MarketOhlcvBar.timeframe.in_(("1m", "5m")))
            .order_by(desc(MarketOhlcvBar.close_time))
            .limit(1)
        )
        if latest_bar_at is not None and (now - latest_bar_at) < timedelta(seconds=90):
            return
        try:
            from app.services.market_price_refresh_service import (
                MarketPriceRefreshError,
                MarketPriceRefreshService,
            )

            # Short frames only — keep the scan path fast.
            MarketPriceRefreshService(self.db).refresh_recent_prices(
                actor=None,
                timeframes=(("1m", 60, 80), ("5m", 300, 50)),
            )
        except MarketPriceRefreshError:
            # Scan continues with whatever verified bars already exist.
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                pass
            return
        except Exception:  # noqa: BLE001 — never block scanning on refresh failure
            # Unique races can poison the session; clear before the cycle continues.
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                pass
            return

    def _load_bar_rows(
        self, instrument_id: uuid.UUID, *, limit: int
    ) -> tuple[list[MarketOhlcvBar], str | None, datetime | None]:
        # Prefer short TFs only when they have enough history to evaluate.
        for tf in TIMEFRAME_PREF:
            rows = list(
                self.db.scalars(
                    select(MarketOhlcvBar)
                    .where(
                        MarketOhlcvBar.instrument_id == instrument_id,
                        MarketOhlcvBar.timeframe == tf,
                    )
                    .order_by(MarketOhlcvBar.open_time.asc())
                )
            )
            if len(rows) >= MIN_BARS:
                rows = rows[-limit:]
                return rows, tf, rows[-1].close_time
        # Fallback: best available preferred TF even if short, else any bars.
        for tf in TIMEFRAME_PREF:
            rows = list(
                self.db.scalars(
                    select(MarketOhlcvBar)
                    .where(
                        MarketOhlcvBar.instrument_id == instrument_id,
                        MarketOhlcvBar.timeframe == tf,
                    )
                    .order_by(MarketOhlcvBar.open_time.asc())
                )
            )
            if rows:
                rows = rows[-limit:]
                return rows, tf, rows[-1].close_time
        rows = list(
            self.db.scalars(
                select(MarketOhlcvBar)
                .where(MarketOhlcvBar.instrument_id == instrument_id)
                .order_by(MarketOhlcvBar.open_time.asc())
            )
        )
        if not rows:
            return [], None, None
        rows = rows[-limit:]
        return rows, rows[-1].timeframe, rows[-1].close_time

    def _prior_watch_meta(self, symbol: str) -> dict[str, Any]:
        """Reuse watching_since across cycles for the same symbol when still active."""
        row = self.db.scalar(
            select(MarketScanCandidate)
            .where(
                MarketScanCandidate.symbol == symbol.upper(),
                MarketScanCandidate.stage.in_(("Watching", "Risk Review", "Evaluating")),
            )
            .order_by(desc(MarketScanCandidate.evaluated_at))
            .limit(1)
        )
        if row is None:
            return {}
        detail = row.detail or {}
        since = detail.get("watching_since") or row.evaluated_at
        if isinstance(since, str):
            try:
                since = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                since = row.evaluated_at
        return {"watching_since": since}

    def _watch_detail(
        self,
        *,
        stage: str,
        price: Decimal,
        entry: Decimal,
        stop: Decimal | None,
        target: Decimal | None,
        market_data_at: datetime | None,
        watching_since: datetime | None,
        expires_at: datetime | None,
        risk_status: str,
        bars: list[Bar],
        timeframe: str | None = "1m",
    ) -> dict[str, Any]:
        now = _utcnow()
        candle_len = candle_length_for(timeframe)
        next_candle = None
        if market_data_at is not None:
            # Next evaluation aligns with next short-TF candle close.
            next_candle = market_data_at + candle_len
            while next_candle <= now:
                next_candle = next_candle + candle_len
        rr = None
        if stop is not None and target is not None and price > 0:
            risk = abs(price - stop)
            reward = abs(target - price)
            if risk > 0:
                rr = float(reward / risk)
        vols = [b.volume for b in bars[-5:] if b.volume is not None]
        vol_ok = bool(vols) and sum(vols) / len(vols) > 0
        data_fresh = (
            market_data_at is not None
            and (now - market_data_at) <= STALE_BAR
        )
        checklist = [
            {
                "key": "trend",
                "label": "Trend direction agrees",
                "status": "passed" if stage in {"Watching", "Risk Review", "Entered"} else (
                    "failed" if stage == "Rejected" else "waiting"
                ),
            },
            {
                "key": "entry_range",
                "label": "Price entered planned range",
                "status": (
                    "waiting"
                    if stage == "Watching"
                    else ("passed" if stage in {"Risk Review", "Entered"} else "failed")
                ),
            },
            {
                "key": "volume",
                "label": "Buying volume is strong enough",
                "status": "passed" if vol_ok else "waiting",
            },
            {
                "key": "confirmation",
                "label": "Confirmation candle closed",
                "status": (
                    "waiting"
                    if stage == "Watching"
                    else ("passed" if stage in {"Risk Review", "Entered"} else "failed")
                ),
            },
            {
                "key": "risk_reward",
                "label": "Risk/reward meets minimum",
                "status": "passed" if rr is not None and rr >= 1.0 else "waiting",
            },
            {
                "key": "exposure",
                "label": "Account exposure is acceptable",
                "status": "passed" if risk_status == "clear" else (
                    "waiting" if risk_status == "paused" else "failed"
                ),
            },
            {
                "key": "data",
                "label": "Market data is current",
                "status": "passed" if data_fresh else "failed",
            },
        ]
        waiting_n = sum(1 for c in checklist if c["status"] == "waiting")
        return {
            "watching_since": watching_since.isoformat() if watching_since else None,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "next_eval_at": (
                next_candle.isoformat()
                if next_candle is not None
                else None
            ),
            "next_candle_close_at": next_candle.isoformat() if next_candle else None,
            "risk_reward": rr,
            "checklist": checklist,
            "checklist_waiting": waiting_n,
            "support": float(stop) if stop is not None else None,
            "resistance": float(target) if target is not None else None,
        }

    def _founder_open_positions(
        self, portfolio_id: uuid.UUID | None = None
    ) -> tuple[int, list[str]]:
        """Open paper positions for the Founder book (not fixture portfolios).

        Preference: explicit portfolio_id → automatic-mode books → any book with
        open size excluding absurd test marks (BTC avg cost < 1000, etc.).
        """
        from app.models.paper_training import PaperTrainingSettings

        q = select(PaperPosition).where(PaperPosition.quantity != 0)
        if portfolio_id is not None:
            rows = list(
                self.db.scalars(q.where(PaperPosition.portfolio_id == portfolio_id))
            )
            syms = sorted({p.symbol for p in rows})
            return len(rows), syms

        auto_ids = set(
            self.db.scalars(
                select(PaperTrainingSettings.portfolio_id).where(
                    PaperTrainingSettings.mode == "automatic"
                )
            ).all()
        )
        if auto_ids:
            rows = list(
                self.db.scalars(q.where(PaperPosition.portfolio_id.in_(auto_ids)))
            )
            syms = sorted({p.symbol for p in rows})
            return len(rows), syms

        # Fallback: exclude obvious fixture junk (unit-test BTC/ETH at fake prices).
        rows = []
        for p in self.db.scalars(q):
            cost = Decimal(p.average_cost or 0)
            sym = (p.symbol or "").upper()
            if sym.startswith("BTC") and cost < Decimal("1000"):
                continue
            if sym.startswith("ETH") and cost < Decimal("50"):
                continue
            rows.append(p)
        syms = sorted({p.symbol for p in rows})
        return len(rows), syms

    def cockpit_snapshot(
        self,
        *,
        default_notional: Decimal = Decimal("100"),
        portfolio_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Aggregated Founder cockpit: wall, watches, gauges — genuine data only."""
        status = self.plain_status_summary()
        now = _utcnow()
        instruments = list(
            self.db.scalars(
                select(MarketInstrument)
                .where(MarketInstrument.is_active.is_(True))
                .order_by(MarketInstrument.symbol.asc())
            )
        )
        candidates = self.list_candidates(limit=50)
        by_symbol = {c.symbol: c for c in candidates}
        open_count, open_position_symbols = self._founder_open_positions(portfolio_id)
        open_syms = set(open_position_symbols)
        wall: list[dict[str, Any]] = []
        for inst in instruments:
            rows, timeframe, close_time = self._load_bar_rows(inst.id, limit=30)
            closes = [float(r.close) for r in rows]
            price = closes[-1] if closes else None
            pct = None
            if len(closes) >= 2 and closes[-2] != 0:
                pct = ((closes[-1] - closes[-2]) / closes[-2]) * 100.0
            cand = by_symbol.get(inst.symbol)
            status_label = self._wall_status(cand, inst.symbol in open_syms, len(rows))
            outlook = "Unclear"
            if cand is not None:
                if cand.bias == "Bullish":
                    outlook = "Rising"
                elif cand.bias == "Bearish":
                    outlook = "Falling"
            wall.append(
                {
                    "symbol": inst.symbol,
                    "current_price": price,
                    "pct_change": pct,
                    "sparkline": closes[-24:],
                    "outlook": outlook,
                    "signal_strength": float(cand.score) if cand else 0.0,
                    "status": status_label,
                    "last_analyzed_at": (
                        cand.evaluated_at.isoformat() if cand else None
                    ),
                    "candidate_id": str(cand.id) if cand else None,
                    "timeframe": timeframe,
                    "market_data_at": (
                        close_time.isoformat() if close_time else None
                    ),
                    "stale": (
                        close_time is None
                        or (now - close_time) > STALE_BAR
                    ),
                }
            )

        watches = []
        for cand in candidates:
            # Active focus stages first; Expired stays visible but must not freeze Live Desk.
            if cand.stage not in {"Watching", "Risk Review", "Evaluating", "Expired"}:
                continue
            watches.append(self._founder_watch_plan(cand, default_notional=default_notional))
        # Stable order: active watches before expired so UI rotation prefers live work.
        watches.sort(
            key=lambda w: (
                0
                if w["stage_raw"] in {"Watching", "Risk Review", "Evaluating"}
                else 1,
                w.get("symbol") or "",
            )
        )

        awaiting = [w for w in watches if w["stage_raw"] == "Watching"]
        risk_check = [w for w in watches if w["stage_raw"] == "Risk Review"]

        doing = self._doing_lines(status, candidates)
        decided = self._decided_lines(limit=24)
        current_market = status.get("current_market")
        focus_symbols = list(
            dict.fromkeys(
                [
                    *open_position_symbols,
                    *[w["symbol"] for w in awaiting],
                    *[w["symbol"] for w in risk_check],
                    *([current_market] if current_market else []),
                ]
            )
        )
        monitor = self._monitor_rows(
            wall, current_market=current_market, now=now
        )

        # Plain-language rejection strip for this pass (not a frozen snapshot essay).
        from app.services.plain_language import plain_rejection

        rej_raw = status.get("rejection_counts") or {}
        rejection_summary = [
            {
                "code": str(code),
                "count": int(n),
                "why": plain_rejection(str(code)),
            }
            for code, n in sorted(
                ((k, int(v)) for k, v in rej_raw.items() if int(v or 0) > 0),
                key=lambda kv: -kv[1],
            )[:8]
        ]
        # Latest rejected candidates with symbol + why (live teach stream).
        rejected_live = []
        for cand in candidates:
            if cand.stage not in {"Rejected", "Expired"}:
                continue
            rejected_live.append(
                {
                    "symbol": cand.symbol,
                    "stage": cand.stage,
                    "reason_code": cand.reason_code,
                    "why": plain_rejection(cand.reason_code, cand.reason_text),
                    "evaluated_at": cand.evaluated_at.isoformat()
                    if cand.evaluated_at
                    else None,
                }
            )
            if len(rejected_live) >= 16:
                break

        scanned = int((status.get("scan_progress") or {}).get("scanned") or 0)
        total = int((status.get("scan_progress") or {}).get("total") or 0)
        return {
            "generated_at": now.isoformat(),
            "headline": status.get("headline"),
            "scanner_state": status.get("scanner_state") or "Between Cycles",
            "current_market": current_market,
            "markets_monitored": len(instruments),
            "scan_progress": {"scanned": scanned, "total": total},
            "next_scan_at": _as_iso(status.get("next_scheduled_at")),
            "possible_trades_found": status.get("possible_trades_found") or 0,
            "watching_count": len(awaiting),
            "awaiting_confirmation": len(awaiting),
            "risk_check_count": len(risk_check),
            "open_trades": open_count,
            "open_position_symbols": open_position_symbols,
            "focus_symbols": focus_symbols,
            "market_data_at": _as_iso(status.get("market_data_at")),
            "market_data_stale": bool(status.get("market_data_stale")),
            "market_data_age_seconds": status.get("market_data_age_seconds"),
            "trading_allowed": bool(status.get("trading_allowed")),
            "pause_new_entries_active": bool(status.get("pause_new_entries_active")),
            "kill_switch_active": bool(status.get("kill_switch_active")),
            "next_step": status.get("next_step"),
            "wall": wall,
            "watches": watches,
            "monitor": monitor,
            "doing": doing,
            "decided": [
                {
                    **d,
                    "at": _as_iso(d.get("at")) or "",
                }
                for d in decided
            ],
            "rejection_summary": rejection_summary,
            "rejected_live": rejected_live,
            "last_cycle_completed_at": _as_iso(
                (status.get("cycle") or {}).get("completed_at")
            ),
            "scan_interval_seconds": int(SCAN_INTERVAL.total_seconds()),
            "watch_ttl_seconds": int(CANDIDATE_WATCH_TTL.total_seconds()),
        }

    def _founder_watch_plan(
        self, cand: MarketScanCandidate, *, default_notional: Decimal
    ) -> dict[str, Any]:
        from app.services.plain_language import (
            BIAS_PLAIN,
            confidence_from_score,
            plain_rejection,
        )

        detail = cand.detail or {}
        now = _utcnow()
        watching_since = detail.get("watching_since") or cand.evaluated_at.isoformat()
        expires_at = detail.get("expires_at")
        if not expires_at:
            expires_at = (cand.evaluated_at + CANDIDATE_WATCH_TTL).isoformat()
        since_dt = cand.evaluated_at
        if isinstance(watching_since, str):
            try:
                since_dt = datetime.fromisoformat(watching_since.replace("Z", "+00:00"))
            except ValueError:
                since_dt = cand.evaluated_at
        watched_seconds = max(0, int((now - since_dt).total_seconds()))
        exp_dt = since_dt + CANDIDATE_WATCH_TTL
        if isinstance(expires_at, str):
            try:
                exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except ValueError:
                exp_dt = since_dt + CANDIDATE_WATCH_TTL
        expire_in = max(0, int((exp_dt - now).total_seconds()))
        next_eval = detail.get("next_eval_at") or detail.get("next_candle_close_at")
        next_eval_in = None
        if isinstance(next_eval, str):
            try:
                ne = datetime.fromisoformat(next_eval.replace("Z", "+00:00"))
                next_eval_in = max(0, int((ne - now).total_seconds()))
            except ValueError:
                next_eval_in = None
        checklist = detail.get("checklist") or []
        waiting_n = int(detail.get("checklist_waiting") or sum(
            1 for c in checklist if c.get("status") == "waiting"
        ))
        price = cand.current_price
        stop = cand.stop_loss
        target = cand.take_profit
        max_loss = None
        pot_profit = None
        if price and stop and price > 0:
            units = default_notional / price
            max_loss = abs(price - stop) * units
        if price and target and price > 0:
            units = default_notional / price
            pot_profit = abs(target - price) * units
        entry = cand.entry_zone or price
        narrative = self._watch_narrative(
            cand=cand,
            watched_seconds=watched_seconds,
            next_eval_in=next_eval_in,
            expire_in=expire_in,
        )
        def _dec(v: Decimal | float | int | str | None) -> str | None:
            if v is None:
                return None
            return str(v)

        entry_dec: Decimal | None
        if isinstance(entry, Decimal):
            entry_dec = entry
        elif entry is None:
            entry_dec = None
        else:
            entry_dec = Decimal(str(entry))

        return {
            "id": str(cand.id),
            "symbol": cand.symbol,
            "stage_raw": cand.stage,
            "outlook": BIAS_PLAIN.get(cand.bias, cand.bias),
            "confidence": confidence_from_score(float(cand.score)),
            "score": float(cand.score),
            "why": plain_rejection(cand.reason_code, cand.reason_text),
            "waiting_for": narrative["waiting_for"],
            "narrative": narrative["statement"],
            # ISO strings — JSON-safe for EOC / RSC props
            "watching_since": since_dt.isoformat(),
            "watched_seconds": watched_seconds,
            "expires_at": exp_dt.isoformat(),
            "expire_in_seconds": expire_in,
            "next_eval_at": next_eval,
            "next_eval_in_seconds": next_eval_in,
            "current_price": _dec(price),
            "entry_zone": _dec(entry_dec),
            "stop_loss": _dec(stop),
            "take_profit": _dec(target),
            "risk_reward": detail.get("risk_reward"),
            "paper_capital_planned": str(default_notional),
            "max_dollar_loss": _dec(max_loss),
            "potential_dollar_profit": _dec(pot_profit),
            "checklist": checklist,
            "checklist_waiting": waiting_n,
            "checklist_summary": (
                f"Argus is waiting for {waiting_n} remaining condition"
                f"{'' if waiting_n == 1 else 's'} before this paper trade "
                "can be considered."
                if waiting_n
                else (
                    "All listed conditions currently look ready for paper consideration."
                )
            ),
            "support": detail.get("support"),
            "resistance": detail.get("resistance"),
            "timeframe": cand.timeframe,
            "strategy_key": cand.strategy_key,
            "risk_status": cand.risk_status,
            "reason_code": cand.reason_code,
            "market_data_at": (
                cand.market_data_at.isoformat() if cand.market_data_at else None
            ),
            "evaluated_at": cand.evaluated_at.isoformat(),
        }

    def _watch_narrative(
        self,
        *,
        cand: MarketScanCandidate,
        watched_seconds: int,
        next_eval_in: int | None,
        expire_in: int,
    ) -> dict[str, str]:
        mins = watched_seconds // 60
        if cand.stage == "Expired":
            return {
                "statement": (
                    f"Watching expired after {mins} minutes because confirmation never "
                    f"arrived for {cand.symbol}. No trade was opened."
                ),
                "waiting_for": "Nothing — this opportunity expired.",
            }
        entry = cand.entry_zone or cand.current_price
        entry_txt = f"${entry:,.2f}" if entry is not None else "the planned level"
        countdown = (
            f"{next_eval_in // 60}:{next_eval_in % 60:02d}"
            if next_eval_in is not None
            else "the next scan"
        )
        return {
            "statement": (
                f"Watching for {mins} minute{'s' if mins != 1 else ''}. "
                f"Argus wants {cand.symbol} to hold above {entry_txt} with stronger "
                f"buying volume. It will evaluate again when the current "
                f"{cand.timeframe} candle closes in {countdown}."
            ),
            "waiting_for": (
                f"A confirming {cand.timeframe} candle close above {entry_txt}, "
                f"or expiration in {expire_in // 60}:{expire_in % 60:02d}."
            ),
        }

    @staticmethod
    def _wall_status(
        cand: MarketScanCandidate | None, trade_open: bool, bar_count: int
    ) -> str:
        if trade_open:
            return "Trade Open"
        if bar_count < MIN_BARS:
            return "Waiting for Data"
        if cand is None:
            return "Scanning"
        if cand.stage == "Watching":
            return "Watching"
        if cand.stage == "Risk Review":
            return "Risk Check"
        if cand.stage == "Evaluating":
            return "Almost Ready"
        if cand.stage == "Expired":
            return "Rejected"
        if cand.stage == "Rejected":
            return "Rejected"
        if cand.stage == "Entered":
            return "Trade Open"
        return "Scanning"

    def _doing_lines(
        self, status: dict[str, Any], candidates: list[MarketScanCandidate]
    ) -> list[dict[str, str]]:
        """Short activity lines for the live monitor strip (not a frozen essay)."""
        lines: list[dict[str, str]] = []
        cur = status.get("current_market")
        progress = status.get("scan_progress") or {}
        scanned = int(progress.get("scanned") or 0)
        total = int(progress.get("total") or status.get("symbols_monitored") or 0)
        state = status.get("scanner_state") or "Between Cycles"

        if state == "Scanning" and cur:
            lines.append(
                {
                    "text": f"Checking {cur} ({scanned}/{total})",
                    "tone": "ok",
                }
            )
        elif state == "Delayed":
            lines.append(
                {
                    "text": "Scan delayed — worker catching up (still running)",
                    "tone": "warn",
                }
            )
        elif total:
            lines.append(
                {
                    "text": f"Last pass {scanned}/{total} markets · auto scan on",
                    "tone": "ok",
                }
            )

        watching = [c for c in candidates if c.stage == "Watching"]
        risk = [c for c in candidates if c.stage == "Risk Review"]
        if watching:
            syms = ", ".join(c.symbol for c in watching[:4])
            more = f" +{len(watching) - 4}" if len(watching) > 4 else ""
            lines.append(
                {
                    "text": f"Watch {len(watching)}: {syms}{more}",
                    "tone": "wait",
                }
            )
        if risk:
            lines.append(
                {
                    "text": f"Risk check {len(risk)}: "
                    + ", ".join(c.symbol for c in risk[:3]),
                    "tone": "wait",
                }
            )

        open_n = int(
            status.get("open_positions_live")
            if status.get("open_positions_live") is not None
            else (status.get("pipeline_counts") or {}).get("positions")
            or 0
        )
        if open_n:
            lines.append(
                {
                    "text": f"Stops live on {open_n} open paper trade"
                    f"{'' if open_n == 1 else 's'}",
                    "tone": "ok",
                }
            )
        if status.get("market_data_stale"):
            lines.append({"text": "Feed stale — Update prices", "tone": "warn"})

        # Surface this-pass rejection tallies so Live Monitor is not a green blink.
        from app.services.plain_language import plain_rejection

        rej = status.get("rejection_counts") or {}
        if isinstance(rej, dict) and rej:
            top = sorted(
                ((str(k), int(v)) for k, v in rej.items() if int(v or 0) > 0),
                key=lambda kv: -kv[1],
            )[:3]
            for code, n in top:
                short = plain_rejection(code).split(".")[0]
                lines.append(
                    {
                        "text": f"Rejected {n}× — {short}",
                        "tone": "bad",
                    }
                )

        if not lines:
            lines.append({"text": "Standing by for next scan", "tone": "wait"})
        return lines[:8]

    def _monitor_rows(
        self,
        wall: list[dict[str, Any]],
        *,
        current_market: str | None,
        now: datetime,
    ) -> list[dict[str, Any]]:
        """Per-market live monitor rows derived from the wall (verified data only)."""
        rows: list[dict[str, Any]] = []
        for tile in wall:
            close_iso = tile.get("market_data_at")
            age: int | None = None
            if isinstance(close_iso, str):
                try:
                    close_dt = datetime.fromisoformat(close_iso.replace("Z", "+00:00"))
                    age = max(0, int((now - close_dt).total_seconds()))
                except ValueError:
                    age = None
            analyzed_iso = tile.get("last_analyzed_at")
            analyzed_age: int | None = None
            if isinstance(analyzed_iso, str):
                try:
                    a_dt = datetime.fromisoformat(analyzed_iso.replace("Z", "+00:00"))
                    analyzed_age = max(0, int((now - a_dt).total_seconds()))
                except ValueError:
                    analyzed_age = None
            status = str(tile.get("status") or "Scanning")
            phase = "idle"
            if tile.get("symbol") == current_market:
                phase = "focus"
            elif status in {"Watching", "Risk Check", "Almost Ready"}:
                phase = "watch"
            elif status == "Trade Open":
                phase = "open"
            elif tile.get("stale") or status == "Waiting for Data":
                phase = "stale"
            elif status == "Rejected":
                phase = "clear"
            rows.append(
                {
                    "symbol": tile.get("symbol"),
                    "status": status,
                    "phase": phase,
                    "price": tile.get("current_price"),
                    "pct_change": tile.get("pct_change"),
                    "outlook": tile.get("outlook"),
                    "signal_strength": tile.get("signal_strength") or 0,
                    "timeframe": tile.get("timeframe"),
                    "stale": bool(tile.get("stale")),
                    "market_data_at": close_iso,
                    "age_seconds": age,
                    "last_analyzed_at": analyzed_iso,
                    "analyzed_age_seconds": analyzed_age,
                    "focus": tile.get("symbol") == current_market,
                }
            )
        # Focus / watch / open first so the live board reads as active work.
        order = {"focus": 0, "open": 1, "watch": 2, "stale": 3, "clear": 4, "idle": 5}
        rows.sort(
            key=lambda r: (
                order.get(str(r.get("phase")), 9),
                -float(r.get("signal_strength") or 0),
                str(r.get("symbol") or ""),
            )
        )
        return rows

    def _decided_lines(self, *, limit: int = 12) -> list[dict[str, Any]]:
        from app.services.plain_language import plain_rejection

        events = self.list_events(limit=40)
        out: list[dict[str, Any]] = []
        for e in events:
            if e.component not in {"strategy_evaluator", "market_scanner", "paper_training"}:
                # Keep teaching / evaluator decisions; skip pure health noise.
                if e.outcome not in {"watching", "rejected", "interested", "not_interested"}:
                    continue
            why = plain_rejection(e.reason_code, e.detail)
            if e.outcome == "watching":
                text = (
                    f"Watched {e.symbol} because upward momentum strengthened"
                    if e.symbol
                    else why
                )
            elif e.outcome == "rejected":
                text = f"Rejected {e.symbol}: {why}" if e.symbol else why
            else:
                text = e.title
            out.append(
                {
                    "id": str(e.id),
                    "at": e.occurred_at,
                    "text": text,
                    "tone": (
                        "bad"
                        if e.outcome == "rejected"
                        else ("ok" if e.outcome == "watching" else "info")
                    ),
                }
            )
            if len(out) >= limit:
                break
        return out

    def _add_candidate(
        self,
        cycle: MarketScanCycle,
        *,
        symbol: str,
        timeframe: str,
        bias: str,
        stage: str,
        score: Decimal,
        risk_status: str,
        reason_code: str | None,
        reason_text: str | None,
        price: Decimal | float | None,
        market_data_at: datetime | None,
        entry_zone: Decimal | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        detail: dict[str, Any] | None = None,
    ) -> MarketScanCandidate:
        cand = MarketScanCandidate(
            cycle_id=cycle.id,
            symbol=symbol,
            timeframe=timeframe,
            strategy_key=STRATEGY_KEY,
            bias=bias,
            stage=stage,
            score=score,
            risk_status=risk_status,
            reason_code=reason_code,
            reason_text=reason_text,
            current_price=Decimal(str(price)) if price is not None else None,
            entry_zone=entry_zone,
            stop_loss=stop_loss,
            take_profit=take_profit,
            market_data_at=market_data_at,
            evaluated_at=_utcnow(),
            detail=detail or {},
        )
        self.db.add(cand)
        self.db.flush()
        return cand

    def _emit(
        self,
        cycle: MarketScanCycle,
        *,
        component: str,
        outcome: str,
        title: str,
        detail: str,
        correlation_id: str,
        symbol: str | None = None,
        stage: str | None = None,
        reason_code: str | None = None,
        strategy_key: str | None = None,
        candidate_id: uuid.UUID | None = None,
    ) -> None:
        self.db.add(
            MarketScanEvent(
                cycle_id=cycle.id,
                candidate_id=candidate_id,
                component=component,
                symbol=symbol,
                stage=stage,
                outcome=outcome,
                reason_code=reason_code,
                title=title,
                detail=detail,
                strategy_key=strategy_key,
                correlation_id=correlation_id,
                occurred_at=_utcnow(),
                payload={},
            )
        )

    def _prune_old_events(self) -> None:
        cutoff = _utcnow() - EVENT_RETENTION
        self.db.execute(delete(MarketScanEvent).where(MarketScanEvent.occurred_at < cutoff))

    @staticmethod
    def _cycle_dict(cycle: MarketScanCycle) -> dict[str, Any]:
        return {
            "id": cycle.id,
            "status": cycle.status,
            "timeframe": cycle.timeframe,
            "strategy_key": cycle.strategy_key,
            "symbols_total": cycle.symbols_total,
            "symbols_scanned": cycle.symbols_scanned,
            "candidates_found": cycle.candidates_found,
            "current_symbol": cycle.current_symbol,
            "started_at": cycle.started_at,
            "completed_at": cycle.completed_at,
            "next_scheduled_at": cycle.next_scheduled_at,
            "correlation_id": cycle.correlation_id,
            "rejection_counts": cycle.rejection_counts or {},
            "pipeline_counts": cycle.pipeline_counts or {},
        }

    @staticmethod
    def _event_dict(event: MarketScanEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "cycle_id": event.cycle_id,
            "candidate_id": event.candidate_id,
            "occurred_at": event.occurred_at,
            "component": event.component,
            "symbol": event.symbol,
            "stage": event.stage,
            "outcome": event.outcome,
            "reason_code": event.reason_code,
            "title": event.title,
            "detail": event.detail,
            "strategy_key": event.strategy_key,
            "correlation_id": event.correlation_id,
        }
