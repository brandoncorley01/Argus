"""Refresh recent crypto prices from a public market API into OHLCV storage.

Uses Coinbase Exchange public candles (no account / no live trading).
Does not invent prices — only stores what the exchange returns.

Primary practice charts are 1m and 5m so the scanner can re-evaluate quickly.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import InstitutionalRole, User, UserRole
from app.models.market_intelligence import MarketInstrument
from app.schemas.market import IngestBatchRequest, OhlcvBarIngest
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedPrincipal
from app.services.market_intelligence_service import (
    MarketIntelligenceError,
    MarketIntelligenceService,
)

# Default paper-training universe — multi-symbol scan needs instruments registered.
DEFAULT_SYMBOLS: tuple[str, ...] = (
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "XRP-USD",
    "ADA-USD",
    "DOGE-USD",
    "AVAX-USD",
    "LINK-USD",
    "DOT-USD",
    "LTC-USD",
    "BCH-USD",
    "ATOM-USD",
    "UNI-USD",
    "NEAR-USD",
    "APT-USD",
    "ARB-USD",
    "OP-USD",
    "SUI-USD",
)

# Coinbase Exchange public API: [time, low, high, open, close, volume]
COINBASE_CANDLES_URL = (
    "https://api.exchange.coinbase.com/products/{product_id}/candles"
    "?granularity={granularity}&start={start}&end={end}"
)

# (timeframe label, granularity seconds, bars to request)
# Short charts only — refreshed every minute for opportunity scanning.
REFRESH_TIMEFRAMES: tuple[tuple[str, int, int], ...] = (
    ("1m", 60, 80),
    ("5m", 300, 50),
)


class MarketPriceRefreshError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class MarketPriceRefreshService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.market = MarketIntelligenceService(db)
        self.audit = AuditService(db)

    def ensure_default_instruments(self) -> list[str]:
        ensured: list[str] = []
        for symbol in DEFAULT_SYMBOLS:
            base, _, quote = symbol.partition("-")
            self.market.ensure_instrument(
                symbol=symbol,
                display_name=symbol,
                asset_class="crypto",
                base_asset=base or None,
                quote_asset=quote or None,
            )
            ensured.append(symbol)
        self.db.commit()
        return ensured

    def _resolve_actor(
        self, actor: AuthenticatedPrincipal | None
    ) -> AuthenticatedPrincipal:
        if actor is not None:
            return actor
        # Worker / system path: attribute ingest to an active Founder account.
        founder = self.db.scalars(
            select(User)
            .options(selectinload(User.roles))
            .join(UserRole, UserRole.user_id == User.id)
            .where(
                UserRole.role == InstitutionalRole.FOUNDER,
                User.is_active.is_(True),
            )
            .limit(1)
        ).first()
        if founder is None:
            raise MarketPriceRefreshError(
                "no_actor",
                "No Founder account is available to attribute price refresh.",
            )
        from types import SimpleNamespace

        return AuthenticatedPrincipal(
            user=founder,
            session=SimpleNamespace(id=None),  # type: ignore[arg-type]
            roles=frozenset({InstitutionalRole.FOUNDER}),
        )

    def refresh_recent_prices(
        self,
        *,
        actor: AuthenticatedPrincipal | None = None,
        symbols: list[str] | None = None,
        timeframes: tuple[tuple[str, int, int], ...] | None = None,
    ) -> dict[str, Any]:
        """Fetch fresh short-TF candles and ingest via the governed path.

        Uses provider_key=manual with source_attribution naming the public feed so
        operators can see provenance. Failures are returned per-symbol; never invents bars.
        """
        principal = self._resolve_actor(actor)
        self.ensure_default_instruments()
        if symbols is None:
            # Dynamic discovery may have activated additional USD markets.
            active = list(
                self.db.scalars(
                    select(MarketInstrument)
                    .where(MarketInstrument.is_active.is_(True))
                    .order_by(MarketInstrument.symbol.asc())
                )
            )
            target = [i.symbol.upper() for i in active] or list(DEFAULT_SYMBOLS)
        else:
            target = [s.upper() for s in symbols]
        # Cap refresh size so discovery cannot blow the 2-minute price cron.
        # Raised with MAX_DISCOVERY_ACTIVE so promoted runners keep fresh bars.
        _MAX_REFRESH = 72
        if len(target) > _MAX_REFRESH:
            core = [s for s in DEFAULT_SYMBOLS if s in target]
            extra = [s for s in target if s not in core][: _MAX_REFRESH - len(core)]
            target = list(core) + extra
        frames = timeframes or REFRESH_TIMEFRAMES
        now = datetime.now(UTC).replace(microsecond=0)
        accepted = 0
        failed: list[dict[str, str]] = []
        per_symbol: dict[str, int] = {}

        bars: list[OhlcvBarIngest] = []
        for symbol in target:
            # Drop test/manual junk bars so the next mark uses the public feed.
            try:
                from app.services.paper_trading_service import PaperTradingService

                PaperTradingService(self.db).purge_untrusted_bars(symbol)
                self.db.commit()
            except Exception:  # noqa: BLE001 — refresh must continue even if purge fails
                self.db.rollback()

            symbol_count = 0
            for tf_label, granularity, bar_count in frames:
                start = now - timedelta(seconds=granularity * bar_count)
                try:
                    raw = self._fetch_candles(
                        symbol, start=start, end=now, granularity=granularity
                    )
                except MarketPriceRefreshError as exc:
                    failed.append(
                        {
                            "symbol": f"{symbol}:{tf_label}",
                            "code": exc.code,
                            "message": exc.message,
                        }
                    )
                    continue
                if not raw:
                    failed.append(
                        {
                            "symbol": f"{symbol}:{tf_label}",
                            "code": "empty_feed",
                            "message": (
                                f"The public price feed returned no {tf_label} candles "
                                f"for {symbol}. Argus will not invent prices."
                            ),
                        }
                    )
                    continue
                for row in raw:
                    # Coinbase: [time, low, high, open, close, volume]
                    ts, low, high, open_, close, volume = row
                    open_time = datetime.fromtimestamp(int(ts), tz=UTC)
                    close_time = open_time + timedelta(seconds=granularity)
                    bars.append(
                        OhlcvBarIngest(
                            symbol=symbol,
                            timeframe=tf_label,
                            open_time=open_time,
                            close_time=close_time,
                            open=Decimal(str(open_)),
                            high=Decimal(str(high)),
                            low=Decimal(str(low)),
                            close=Decimal(str(close)),
                            volume=Decimal(str(volume)),
                            source_attribution="coinbase_exchange_public_candles",
                            external_id=f"cb-{symbol}-{tf_label}-{int(ts)}",
                        )
                    )
                    symbol_count += 1
            if symbol_count:
                per_symbol[symbol] = symbol_count
            elif not any(f.get("symbol", "").startswith(f"{symbol}:") for f in failed):
                failed.append(
                    {
                        "symbol": symbol,
                        "code": "empty_feed",
                        "message": (
                            f"The public price feed returned no candles for {symbol}. "
                            "Argus will not invent prices."
                        ),
                    }
                )

        if not bars:
            raise MarketPriceRefreshError(
                "refresh_failed",
                "Could not download recent prices for any market. "
                "Check network access to api.exchange.coinbase.com, then try again.",
            )

        # Chunk ingest to keep payloads reasonable. Include a run id so concurrent
        # UI refresh + scan refresh in the same minute do not collide on keys.
        refresh_id = uuid.uuid4().hex[:12]
        chunk_size = 200
        for i in range(0, len(bars), chunk_size):
            chunk = bars[i : i + chunk_size]
            body = IngestBatchRequest(
                provider_key="manual",
                channel="ohlcv",
                bars=chunk,
            )
            try:
                bucket = now.strftime("%Y%m%dT%H%M")
                result = self.market.ingest_batch(
                    body=body,
                    actor=principal,
                    idempotency_key=f"price-refresh:{bucket}:{refresh_id}:{i}",
                    request_id=None,
                )
                accepted += int(result.get("records_accepted") or 0)
            except MarketIntelligenceError as exc:
                try:
                    self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                failed.append(
                    {"symbol": "*", "code": exc.code, "message": exc.message}
                )
            except Exception as exc:  # noqa: BLE001 — keep refresh resilient
                try:
                    self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                failed.append(
                    {
                        "symbol": "*",
                        "code": "ingest_error",
                        "message": str(exc)[:240],
                    }
                )

        try:
            self.audit.append(
                action="market.prices.refresh",
                resource_type="market_ohlcv_bars",
                resource_id="batch",
                actor_user_id=principal.user.id,
                payload={
                    "symbols": target,
                    "timeframes": [tf for tf, _, _ in frames],
                    "bars_submitted": len(bars),
                    "records_accepted": accepted,
                    "failed_count": len(failed),
                },
            )
            self.db.commit()
        except Exception:
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                pass
            raise

        ready_note = (
            "Recent 1m/5m price history was updated from the public Coinbase Exchange feed. "
            "Argus will re-evaluate on the next automatic scan."
            if accepted > 0
            else "No new price bars were accepted. See failed symbols for next steps."
        )
        return {
            "ok": accepted > 0,
            "records_accepted": accepted,
            "bars_submitted": len(bars),
            "symbols_requested": target,
            "timeframes": [tf for tf, _, _ in frames],
            "per_symbol_bars": per_symbol,
            "failed": failed,
            "next_step": ready_note,
            "disclaimer": (
                "Prices come from a public market feed for paper practice only. "
                "This does not place trades or unlock live trading."
            ),
        }

    def _fetch_candles(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        granularity: int,
    ) -> list[list[float]]:
        url = COINBASE_CANDLES_URL.format(
            product_id=symbol,
            granularity=granularity,
            start=start.isoformat().replace("+00:00", "Z"),
            end=end.isoformat().replace("+00:00", "Z"),
        )
        req = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": "ArgusPaperTraining/1.0", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — public HTTPS
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise MarketPriceRefreshError(
                    "symbol_unavailable",
                    f"{symbol} is not available on the public price feed.",
                ) from exc
            raise MarketPriceRefreshError(
                "feed_http_error",
                f"Public price feed returned HTTP {exc.code} for {symbol}.",
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise MarketPriceRefreshError(
                "feed_unreachable",
                f"Could not reach the public price feed for {symbol}: {exc}",
            ) from exc
        if not isinstance(payload, list):
            raise MarketPriceRefreshError(
                "feed_shape",
                f"Unexpected response shape from price feed for {symbol}.",
            )
        # Newest first from Coinbase — return chronological for clarity
        rows = [row for row in payload if isinstance(row, list) and len(row) >= 6]
        rows.sort(key=lambda r: int(r[0]))
        return rows
