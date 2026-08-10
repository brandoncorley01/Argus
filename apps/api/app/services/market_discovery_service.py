"""Dynamic Coinbase USD market discovery — PAPER observation only.

Discovers active Coinbase USD spot markets, ranks sudden interest, filters
for liquidity/spread/extreme tip risk, then promotes a capped set into
the existing instrument universe for Alpha Radar / market scan.

Strong-day runners near highs are labeled and score-demoted — not erased —
so Argus can watch continuation/pullback structure. Extreme peak exhaustion
still stays off the promote list.

Never places orders. Never unlocks live trading. Volume alone never triggers entries.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.market_intelligence import MarketInstrument
from app.services.audit_service import AuditService
from app.services.market_intelligence_service import MarketIntelligenceService
from app.services.market_price_refresh_service import DEFAULT_SYMBOLS

COINBASE_PRODUCTS_URL = "https://api.exchange.coinbase.com/products"
COINBASE_STATS_URL = "https://api.exchange.coinbase.com/products/{product_id}/stats"
COINBASE_TICKER_URL = "https://api.exchange.coinbase.com/products/{product_id}/ticker"

# Core always-on desk — never deactivated by discovery rotation.
CORE_SYMBOLS: frozenset[str] = frozenset(s.upper() for s in DEFAULT_SYMBOLS)

# Caps keep scan/refresh within cycle budgets — widened so strong-day
# Coinbase runners are not left outside Alpha Radar.
MAX_DISCOVERY_ACTIVE = 35
MAX_STATS_PROBE = 140
MIN_DOLLAR_VOLUME_24H = Decimal("150000")  # reject thin books
MAX_SPREAD_PCT = Decimal("0.012")  # 1.2%
MAX_RANGE_PCT = Decimal("0.35")  # extreme 24h range (allow hotter movers)
MIN_RANGE_PCT = Decimal("0.008")  # need some movement to be "interesting"
STABLE_BASES = frozenset(
    {
        "USD",
        "USDT",
        "USDC",
        "DAI",
        "EUR",
        "GBP",
        "PYUSD",
        "USDCE",
    }
)

HTTP_TIMEOUT_SEC = 12

# Repo root = Argus/ (apps/api/app/services → four parents up from services is apps; five is repo).
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_STATE = _REPO_ROOT / "runtime" / "market-discovery" / "latest.json"


@dataclass
class RankedMarket:
    symbol: str
    dollar_volume: Decimal
    last: Decimal
    open_24h: Decimal
    high_24h: Decimal
    low_24h: Decimal
    change_pct: Decimal
    range_pct: Decimal
    relative_volume: Decimal
    spread_pct: Decimal | None
    opportunity_class: str
    rank_score: Decimal
    reject_reason: str | None = None


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return Decimal("0")


def _http_json(url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ArgusMarketDiscovery/1.0 (paper-research)",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def classify_opportunity(
    *,
    last: Decimal,
    open_24h: Decimal,
    high_24h: Decimal,
    low_24h: Decimal,
    change_pct: Decimal,
    range_pct: Decimal,
) -> str:
    """Label how to approach a mover — not an automatic entry."""
    if last <= 0 or high_24h <= 0:
        return "insufficient_data"
    dist_from_high = (high_24h - last) / high_24h
    dist_from_low = (last - low_24h) / high_24h if high_24h > 0 else Decimal("1")
    # Extreme tip only — normal strong-day runners must still reach Radar.
    if change_pct >= Decimal("0.18") and dist_from_high <= Decimal("0.005"):
        return "peak_exhaustion"
    if change_pct >= Decimal("0.12") and dist_from_high <= Decimal("0.01"):
        return "late_stage_chase"
    # Pullback/retest after a push.
    if change_pct >= Decimal("0.03") and Decimal("0.02") <= dist_from_high <= Decimal(
        "0.06"
    ):
        return "pullback_retest"
    # Early / continuation breakout structure (covers most "new high" runs).
    if change_pct >= Decimal("0.04") and dist_from_high <= Decimal("0.025"):
        if range_pct >= Decimal("0.06"):
            return "breakout_continuation"
        return "early_breakout"
    if change_pct >= Decimal("0.02") and dist_from_low >= Decimal("0.04"):
        return "momentum_continuation"
    if change_pct <= Decimal("-0.04"):
        return "weak_or_dump"
    return "watch"


def rank_score_for(m: RankedMarket) -> Decimal:
    # Prefer dollar volume + acceleration proxy (change) with soft penalties.
    score = (m.dollar_volume / Decimal("1000000")).quantize(Decimal("0.01"))
    score += abs(m.change_pct) * Decimal("40")
    score += m.relative_volume * Decimal("8")
    if m.opportunity_class == "peak_exhaustion":
        score *= Decimal("0.35")
    elif m.opportunity_class == "late_stage_chase":
        # Still caution — but do not bury hot runners under quiet names.
        score *= Decimal("0.7")
    elif m.opportunity_class == "weak_or_dump":
        score *= Decimal("0.35")
    if m.opportunity_class in {"early_breakout", "breakout_continuation", "pullback_retest"}:
        score *= Decimal("1.15")
    if m.spread_pct is not None and m.spread_pct > Decimal("0.006"):
        score *= Decimal("0.7")
    return score


class MarketDiscoveryService:
    """PAPER-only dynamic universe builder feeding Alpha Radar."""

    def __init__(self, db: Session, *, state_path: Path | None = None) -> None:
        self.db = db
        self.market = MarketIntelligenceService(db)
        self.audit = AuditService(db)
        self.state_path = state_path or _DEFAULT_STATE

    def _load_state(self) -> dict[str, Any]:
        try:
            if self.state_path.is_file():
                raw = json.loads(self.state_path.read_text(encoding="utf-8"))
                return raw if isinstance(raw, dict) else {}
        except Exception:  # noqa: BLE001
            pass
        return {}

    def _save_state(self, payload: dict[str, Any]) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(
                json.dumps(payload, indent=2, default=str), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001 — discovery must not fail the worker
            pass

    def latest_snapshot(self) -> dict[str, Any]:
        state = self._load_state()
        if state:
            return state
        return {
            "generated_at": None,
            "markets_scanned": 0,
            "active_opportunities": [],
            "newly_discovered": [],
            "promoted_to_radar": [],
            "rejected": [],
            "paper_only": True,
            "live_trading_enabled": False,
        }

    def list_usd_products(self) -> list[dict[str, Any]]:
        raw = _http_json(COINBASE_PRODUCTS_URL)
        if not isinstance(raw, list):
            return []
        out: list[dict[str, Any]] = []
        for p in raw:
            if not isinstance(p, dict):
                continue
            symbol = str(p.get("id") or "").upper()
            if not symbol.endswith("-USD"):
                continue
            if str(p.get("status") or "").lower() != "online":
                continue
            if p.get("trading_disabled") is True:
                continue
            if p.get("auction_mode") is True:
                continue
            base = str(p.get("base_currency") or symbol.partition("-")[0]).upper()
            if base in STABLE_BASES:
                continue
            out.append(p)
        return out

    def _fetch_stats(self, product_id: str) -> dict[str, Any] | None:
        try:
            data = _http_json(COINBASE_STATS_URL.format(product_id=product_id))
            return data if isinstance(data, dict) else None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return None

    def _fetch_spread_pct(self, product_id: str, last: Decimal) -> Decimal | None:
        try:
            data = _http_json(COINBASE_TICKER_URL.format(product_id=product_id))
            if not isinstance(data, dict) or last <= 0:
                return None
            bid = _dec(data.get("bid"))
            ask = _dec(data.get("ask"))
            if bid <= 0 or ask <= 0 or ask < bid:
                return None
            return (ask - bid) / last
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return None

    def _probe_pool(self, products: list[dict[str, Any]]) -> list[str]:
        """Select a bounded stats probe set: core + prior promotes + rotated remainder."""
        ids = [str(p.get("id") or "").upper() for p in products if p.get("id")]
        state = self._load_state()
        prior = {
            str(x).upper()
            for x in (state.get("promoted_to_radar") or [])
            if isinstance(x, str)
        }
        hour_bucket = datetime.now(UTC).hour
        rotated = sorted(
            [s for s in ids if s not in CORE_SYMBOLS],
            key=lambda s: (hash(f"{hour_bucket}:{s}") & 0xFFFFFFFF),
        )
        pool: list[str] = []
        for s in list(CORE_SYMBOLS) + sorted(prior) + rotated:
            if s not in pool:
                pool.append(s)
            if len(pool) >= MAX_STATS_PROBE:
                break
        return pool

    def rank_markets(
        self, product_ids: list[str]
    ) -> tuple[list[RankedMarket], list[dict[str, Any]]]:
        ranked: list[RankedMarket] = []
        rejected: list[dict[str, Any]] = []
        volumes: list[Decimal] = []
        stats_cache: dict[str, dict[str, Any]] = {}
        for pid in product_ids:
            st = self._fetch_stats(pid)
            if not st:
                rejected.append(
                    {
                        "symbol": pid,
                        "reason": "stale_or_missing_stats",
                        "primary_reason": "stale data",
                    }
                )
                continue
            stats_cache[pid] = st
            last = _dec(st.get("last"))
            vol = _dec(st.get("volume"))
            if last > 0 and vol > 0:
                volumes.append(last * vol)
        median_dv = (
            sorted(volumes)[len(volumes) // 2] if volumes else Decimal("1")
        ) or Decimal("1")

        for pid, st in stats_cache.items():
            last = _dec(st.get("last"))
            open_ = _dec(st.get("open"))
            high = _dec(st.get("high"))
            low = _dec(st.get("low"))
            vol = _dec(st.get("volume"))
            if last <= 0 or vol <= 0:
                rejected.append(
                    {
                        "symbol": pid,
                        "reason": "insufficient_price_volume",
                        "primary_reason": "weak volume confirmation",
                    }
                )
                continue
            dollar = (last * vol).quantize(Decimal("0.01"))
            change = (last - open_) / open_ if open_ > 0 else Decimal("0")
            range_pct = (high - low) / last if last > 0 else Decimal("0")
            rel_vol = dollar / median_dv if median_dv > 0 else Decimal("1")
            opp = classify_opportunity(
                last=last,
                open_24h=open_,
                high_24h=high,
                low_24h=low,
                change_pct=change,
                range_pct=range_pct,
            )
            row = RankedMarket(
                symbol=pid,
                dollar_volume=dollar,
                last=last,
                open_24h=open_,
                high_24h=high,
                low_24h=low,
                change_pct=change,
                range_pct=range_pct,
                relative_volume=rel_vol,
                spread_pct=None,
                opportunity_class=opp,
                rank_score=Decimal("0"),
            )
            # Aggressive filters (analysis quality — not trade triggers alone).
            if dollar < MIN_DOLLAR_VOLUME_24H and pid not in CORE_SYMBOLS:
                rejected.append(
                    {
                        "symbol": pid,
                        "reason": "poor_liquidity",
                        "primary_reason": "poor liquidity",
                        "opportunity_class": opp,
                    }
                )
                continue
            if range_pct > MAX_RANGE_PCT and pid not in CORE_SYMBOLS:
                rejected.append(
                    {
                        "symbol": pid,
                        "reason": "extreme_volatility",
                        "primary_reason": "unsafe volatility",
                        "opportunity_class": opp,
                    }
                )
                continue
            if (
                range_pct < MIN_RANGE_PCT
                and abs(change) < Decimal("0.015")
                and pid not in CORE_SYMBOLS
            ):
                rejected.append(
                    {
                        "symbol": pid,
                        "reason": "no_meaningful_activity",
                        "primary_reason": "weak volume confirmation",
                        "opportunity_class": opp,
                    }
                )
                continue
            if opp == "peak_exhaustion" and pid not in CORE_SYMBOLS:
                # Extreme tip only — keep off Radar. late_stage_chase promotes
                # with a demoted score so strong-day runs are not invisible.
                rejected.append(
                    {
                        "symbol": pid,
                        "reason": opp,
                        "primary_reason": "extreme peak exhaustion",
                        "opportunity_class": opp,
                        "dollar_volume": str(dollar),
                    }
                )
                continue
            spread = self._fetch_spread_pct(pid, last)
            row.spread_pct = spread
            if (
                spread is not None
                and spread > MAX_SPREAD_PCT
                and pid not in CORE_SYMBOLS
            ):
                rejected.append(
                    {
                        "symbol": pid,
                        "reason": "excessive_spread",
                        "primary_reason": "excessive spread",
                        "opportunity_class": opp,
                    }
                )
                continue
            row.rank_score = rank_score_for(row)
            ranked.append(row)

        ranked.sort(key=lambda r: r.rank_score, reverse=True)
        return ranked, rejected

    def run_discovery_cycle(self, *, refresh_prices: bool = True) -> dict[str, Any]:
        """Discover → filter → promote into active instrument universe (PAPER)."""
        products = self.list_usd_products()
        markets_scanned = len(products)
        probe = self._probe_pool(products)
        ranked, rejected = self.rank_markets(probe)

        # Always keep core; fill remaining slots with best discovery names.
        promoted: list[str] = list(sorted(CORE_SYMBOLS))
        newly: list[dict[str, Any]] = []
        active_opps: list[dict[str, Any]] = []
        for row in ranked:
            payload = {
                "symbol": row.symbol,
                "opportunity_class": row.opportunity_class,
                "rank_score": str(row.rank_score),
                "dollar_volume": str(row.dollar_volume),
                "change_pct": str(row.change_pct),
                "relative_volume": str(row.relative_volume),
                "spread_pct": str(row.spread_pct) if row.spread_pct is not None else None,
                "primary_reason": row.opportunity_class.replace("_", " "),
            }
            if row.symbol in CORE_SYMBOLS:
                active_opps.append(payload)
                continue
            if len([s for s in promoted if s not in CORE_SYMBOLS]) >= MAX_DISCOVERY_ACTIVE:
                rejected.append(
                    {
                        "symbol": row.symbol,
                        "reason": "cap_reached",
                        "primary_reason": "universe cap",
                        "opportunity_class": row.opportunity_class,
                    }
                )
                continue
            if row.symbol not in promoted:
                promoted.append(row.symbol)
                newly.append(payload)
            active_opps.append(payload)

        # Ensure + activate promoted; deactivate non-core not promoted.
        for symbol in promoted:
            base, _, quote = symbol.partition("-")
            inst = self.market.ensure_instrument(
                symbol=symbol,
                display_name=symbol,
                asset_class="crypto",
                base_asset=base or None,
                quote_asset=quote or "USD",
            )
            inst.is_active = True
        promote_set = set(promoted)
        extras = list(
            self.db.scalars(
                select(MarketInstrument).where(
                    MarketInstrument.is_active.is_(True),
                )
            )
        )
        deactivated: list[str] = []
        for inst in extras:
            sym = inst.symbol.upper()
            if sym in CORE_SYMBOLS:
                continue
            if sym not in promote_set:
                inst.is_active = False
                deactivated.append(sym)
        self.db.commit()

        price_result: dict[str, Any] | None = None
        if refresh_prices:
            try:
                from app.services.market_price_refresh_service import (
                    MarketPriceRefreshService,
                )

                # Refresh core + newly promoted discovery names (bounded).
                refresh_syms = sorted(promote_set)[: len(CORE_SYMBOLS) + MAX_DISCOVERY_ACTIVE]
                price_result = MarketPriceRefreshService(self.db).refresh_recent_prices(
                    symbols=refresh_syms
                )
            except Exception as exc:  # noqa: BLE001
                price_result = {"ok": False, "error": str(exc)[:200]}

        snapshot = {
            "generated_at": datetime.now(UTC).isoformat(),
            "markets_scanned": markets_scanned,
            "stats_probed": len(probe),
            "active_opportunities": active_opps[:40],
            "newly_discovered": newly[:20],
            "promoted_to_radar": [s for s in promoted if s not in CORE_SYMBOLS],
            "core_symbols": sorted(CORE_SYMBOLS),
            "rejected": rejected[:60],
            "deactivated": deactivated[:40],
            "price_refresh": {
                "ok": bool((price_result or {}).get("ok")),
                "records_accepted": (price_result or {}).get("records_accepted"),
            }
            if price_result
            else None,
            "paper_only": True,
            "live_trading_enabled": False,
            "pipeline": "SCAN BROADLY → FILTER → ALPHA RADAR → WATCH → ENTRY EVALUATION",
        }
        self._save_state(snapshot)
        self.audit.append(
            action="market.discovery_cycle",
            resource_type="market_discovery",
            resource_id="coinbase_usd",
            payload={
                "markets_scanned": markets_scanned,
                "promoted": snapshot["promoted_to_radar"],
                "newly_discovered": [n["symbol"] for n in newly[:20]],
                "rejected_count": len(rejected),
                "paper_only": True,
            },
        )
        self.db.commit()
        return snapshot

    def opportunity_class_for(self, symbol: str) -> str | None:
        state = self._load_state()
        for row in state.get("active_opportunities") or []:
            if isinstance(row, dict) and str(row.get("symbol") or "").upper() == symbol.upper():
                return str(row.get("opportunity_class") or "") or None
        return None

    def enrichment_for(self, symbol: str) -> dict[str, Any]:
        """Metadata to attach onto Alpha Radar candidates (PAPER observation)."""
        sym = symbol.upper()
        state = self._load_state()
        promoted = {
            str(s).upper()
            for s in (state.get("promoted_to_radar") or [])
            if isinstance(s, str)
        }
        opp = self.opportunity_class_for(sym)
        out: dict[str, Any] = {}
        if sym in CORE_SYMBOLS:
            out["discovery_source"] = "core"
        elif sym in promoted:
            out["discovery_source"] = "coinbase_dynamic"
            out["discovered_market"] = True
        if opp:
            out["discovery_opportunity_class"] = opp
            out["trade_pattern"] = opp
            out["primary_reason"] = opp.replace("_", " ")
        return out

    def academy_metrics(self, *, portfolio_id: UUID | None = None) -> dict[str, Any]:
        """Compact discovery → Academy learning stats (PAPER only)."""
        state = self.latest_snapshot()
        promoted = [
            str(s).upper()
            for s in (state.get("promoted_to_radar") or [])
            if isinstance(s, str)
        ]
        newly = state.get("newly_discovered") or []
        rejected = state.get("rejected") or []
        trades_from_discovery = 0
        net_pnl = Decimal("0")
        pattern_pnl: dict[str, dict[str, Any]] = {}
        try:
            from app.models.trading_intelligence import PostTradeReview

            q = select(PostTradeReview).order_by(PostTradeReview.closed_at.desc()).limit(200)
            if portfolio_id is not None:
                q = (
                    select(PostTradeReview)
                    .where(PostTradeReview.portfolio_id == portfolio_id)
                    .order_by(PostTradeReview.closed_at.desc())
                    .limit(200)
                )
            reviews = list(self.db.scalars(q))
            for r in reviews:
                sym = (r.symbol or "").upper()
                if sym in CORE_SYMBOLS:
                    continue
                # Discovered (non-core) closed paper trades.
                trades_from_discovery += 1
                pnl = Decimal(str(r.realized_pnl or 0))
                net_pnl += pnl
                detail = dict(r.detail or {})
                pattern = str(
                    detail.get("discovery_opportunity_class")
                    or detail.get("trade_pattern")
                    or "unclassified"
                )
                bucket = pattern_pnl.setdefault(
                    pattern, {"trades": 0, "net_pnl": Decimal("0")}
                )
                bucket["trades"] += 1
                bucket["net_pnl"] += pnl
        except Exception:  # noqa: BLE001
            pass
        patterns = [
            {
                "pattern": k,
                "trades": v["trades"],
                "net_pnl": str(v["net_pnl"].quantize(Decimal("0.01"))),
            }
            for k, v in sorted(
                pattern_pnl.items(), key=lambda kv: kv[1]["trades"], reverse=True
            )[:12]
        ]
        return {
            "markets_scanned": state.get("markets_scanned") or 0,
            "newly_discovered_count": len(newly),
            "newly_discovered": [
                n.get("symbol") if isinstance(n, dict) else n for n in newly[:12]
            ],
            "promoted_to_radar": promoted[:24],
            "promoted_count": len(promoted),
            "rejected_count": len(rejected),
            "rejected_sample": [
                {
                    "symbol": r.get("symbol"),
                    "primary_reason": r.get("primary_reason") or r.get("reason"),
                }
                for r in rejected[:8]
                if isinstance(r, dict)
            ],
            "trades_from_discovery": trades_from_discovery,
            "net_pnl_from_discovery": str(net_pnl.quantize(Decimal("0.01"))),
            "discovery_pattern_performance": patterns,
            "paper_only": True,
            "volume_never_triggers_trade": True,
        }
