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
from app.models.paper_trading import PaperPortfolio
from app.services.strategy_engine import Bar, SmaCrossoverStrategy

SCAN_INTERVAL = timedelta(minutes=2)
STALE_BAR = timedelta(hours=6)
MIN_BARS = 25
EVENT_RETENTION = timedelta(days=7)
MAX_EVENTS_PER_CYCLE = 80
STRATEGY_KEY = "sma_crossover"
TIMEFRAME_PREF = ("15m", "1h", "1d", "5m")


class MarketScanError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
        latest_bar_at = self.db.scalar(
            select(MarketOhlcvBar.close_time).order_by(desc(MarketOhlcvBar.close_time)).limit(1)
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
            "pipeline_counts": (cycle.pipeline_counts if cycle else {}) or {},
            "rejection_counts": (cycle.rejection_counts if cycle else {}) or {},
            "next_scheduled_at": (
                cycle.next_scheduled_at
                if cycle and cycle.next_scheduled_at
                else (cycle.completed_at + SCAN_INTERVAL if cycle and cycle.completed_at else None)
            ),
            "worker_note": (
                "Scanner runs on the health-supervisor worker cron. "
                "Home reads persisted cycles only — it does not invent activity."
            ),
        }

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
                return latest

            correlation_id = uuid.uuid4().hex[:16]
            cycle = MarketScanCycle(
                status="running",
                timeframe="15m",
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
                    code = "stale_data" if not bars else "confirmation_incomplete"
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
                            f"Need at least {MIN_BARS} bars; found {len(bars)}."
                            if bars
                            else "No OHLCV bars available for this symbol."
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
                            title=f"Entry rejected for {inst.symbol}",
                            detail=(
                                "Insufficient candle history for strategy evaluation."
                                if bars
                                else "No market bars persisted for this symbol."
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
                        reason_text = "SMA fast above slow — watching for confirmation."

                    # Simple structural levels from recent range (not invented targets).
                    window = bars[-20:]
                    low = min(b.low for b in window)
                    high = max(b.high for b in window)
                    stop = Decimal(str(low))
                    target = Decimal(str(high))
                    cand = self._add_candidate(
                        cycle,
                        symbol=inst.symbol,
                        timeframe=timeframe or "15m",
                        bias="Bullish",
                        stage=stage,
                        score=score,
                        risk_status=risk_status,
                        reason_code=reason_code,
                        reason_text=reason_text,
                        price=price,
                        market_data_at=bar_close_time,
                        entry_zone=price,
                        stop_loss=stop if stop < price else None,
                        take_profit=target if target > price else None,
                    )
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
                        bias="Bearish" if exposure == 0 else "Neutral",
                        stage="Rejected",
                        score=Decimal("20"),
                        risk_status="clear",
                        reason_code="weak_signal",
                        reason_text="SMA fast not above slow — no long setup.",
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
                            detail="Momentum strategy check failed: weak signal.",
                            reason_code="weak_signal",
                            stage="Rejected",
                            strategy_key=STRATEGY_KEY,
                            correlation_id=correlation_id,
                        )
                        events_emitted += 1

            # Open paper positions count toward pipeline Positions.
            from app.models.paper_trading import PaperPosition

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
        snap = self.status_snapshot()
        cycle = snap.get("cycle")
        candidates = self.list_candidates(limit=5)
        watching = [c for c in candidates if c.stage in {"Watching", "Evaluating", "Risk Review"}]
        rejected = [c for c in candidates if c.stage == "Rejected"]

        if snap["kill_switch_active"]:
            headline = "Paper trading is blocked by the kill switch."
        elif snap["pause_new_entries_active"]:
            headline = "New paper entries are paused. Argus can still scan and manage exits."
        elif snap["scanner_state"] == "Scanning":
            sym = cycle.get("current_symbol") if cycle else None
            headline = (
                f"Scanning {sym} right now…"
                if sym
                else "Market scan in progress…"
            )
        elif watching:
            names = ", ".join(c.symbol for c in watching[:3])
            headline = f"Watching {names} — not entered yet."
        elif rejected and cycle:
            top = rejected[0]
            why = top.reason_text or top.reason_code or "did not meet entry rules"
            headline = f"Last look: {top.symbol} was not taken — {why}"
        elif snap["scanner_state"] == "Failed":
            headline = "Scanner cannot run until market instruments (and preferably bars) exist."
        elif cycle:
            scanned = cycle.get("symbols_scanned") or 0
            headline = (
                f"Between scans. Last cycle checked {scanned} market"
                f"{'s' if scanned != 1 else ''} and found no entry."
            )
        else:
            headline = "Waiting for the first market scan."

        return {
            **snap,
            "headline": headline,
            "watching_count": len(watching),
            "rejected_count": len(rejected),
            "top_watching": [
                {
                    "symbol": c.symbol,
                    "stage": c.stage,
                    "reason_text": c.reason_text,
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

    def _load_bar_rows(
        self, instrument_id: uuid.UUID, *, limit: int
    ) -> tuple[list[MarketOhlcvBar], str | None, datetime | None]:
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
                # Keep last N for evaluation.
                rows = rows[-limit:]
                return rows, tf, rows[-1].close_time
        # Any timeframe fallback.
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
            detail={},
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
