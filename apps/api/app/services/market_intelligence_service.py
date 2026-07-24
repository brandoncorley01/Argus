"""Market Intelligence services — observe/normalize/store only. No trading."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.market_intelligence import (
    IngestionRunStatus,
    MarketEconomicEvent,
    MarketIngestionIdempotency,
    MarketIngestionRun,
    MarketInstrument,
    MarketNewsItem,
    MarketObservation,
    MarketOhlcvBar,
    MarketProvider,
    MarketProviderHealth,
    MarketQualityFinding,
    MarketResearchItem,
    ObservationChannel,
    ProviderHealthStatus,
    QualityFindingKind,
)
from app.schemas.market import IngestBatchRequest
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedPrincipal


class MarketIntelligenceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class MarketIntelligenceService:
    """Multi-provider observation intake with replay safety and quality checks."""

    STALE_HOURS = 24
    MAX_RETRIES = 3
    BACKOFF_SECONDS = (0.05, 0.1, 0.2)

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def list_providers(self) -> list[tuple[MarketProvider, MarketProviderHealth | None]]:
        providers = list(
            self.db.scalars(select(MarketProvider).order_by(MarketProvider.priority.asc()))
        )
        health_rows = {
            h.provider_id: h
            for h in self.db.scalars(select(MarketProviderHealth)).all()
        }
        return [(p, health_rows.get(p.id)) for p in providers]

    def get_provider(self, provider_key: str) -> MarketProvider:
        row = self.db.scalar(
            select(MarketProvider).where(MarketProvider.provider_key == provider_key)
        )
        if row is None:
            raise MarketIntelligenceError("provider_not_found", f"Unknown provider: {provider_key}")
        return row

    def providers_for_failover(self, kind: str) -> list[MarketProvider]:
        rows = list(
            self.db.scalars(
                select(MarketProvider)
                .where(
                    MarketProvider.is_enabled.is_(True),
                    MarketProvider.supports_failover.is_(True),
                    MarketProvider.provider_kind == kind,
                )
                .order_by(MarketProvider.priority.asc())
            )
        )
        return rows

    def list_instruments(self) -> list[MarketInstrument]:
        return list(
            self.db.scalars(
                select(MarketInstrument).order_by(MarketInstrument.symbol.asc())
            )
        )

    def ensure_instrument(
        self,
        *,
        symbol: str,
        display_name: str | None = None,
        asset_class: str = "crypto",
        base_asset: str | None = None,
        quote_asset: str | None = None,
    ) -> MarketInstrument:
        existing = self.db.scalar(
            select(MarketInstrument).where(MarketInstrument.symbol == symbol.upper())
        )
        if existing:
            return existing
        row = MarketInstrument(
            symbol=symbol.upper(),
            display_name=display_name or symbol.upper(),
            asset_class=asset_class,
            base_asset=base_asset,
            quote_asset=quote_asset,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def create_instrument(
        self,
        *,
        symbol: str,
        display_name: str,
        asset_class: str = "crypto",
        base_asset: str | None = None,
        quote_asset: str | None = None,
    ) -> MarketInstrument:
        row = self.ensure_instrument(
            symbol=symbol,
            display_name=display_name,
            asset_class=asset_class,
            base_asset=base_asset,
            quote_asset=quote_asset,
        )
        self.db.commit()
        return row

    def probe_provider(self, provider_key: str) -> dict[str, Any]:
        provider = self.get_provider(provider_key)
        health = self.db.get(MarketProviderHealth, provider.id)
        if health is None:
            health = MarketProviderHealth(provider_id=provider.id)
            self.db.add(health)

        adapter = (provider.config or {}).get("adapter", provider_key)
        try:
            if adapter == "null_probe":
                detail = {"probe": "ok", "emits_data": False}
                status = ProviderHealthStatus.HEALTHY.value
            elif adapter == "manual":
                detail = {"probe": "ok", "adapter": "manual"}
                status = ProviderHealthStatus.HEALTHY.value
            elif adapter == "http_json":
                detail = self._http_probe_with_backoff(provider.config or {})
                status = ProviderHealthStatus.HEALTHY.value
            else:
                detail = {"probe": "unknown_adapter", "adapter": adapter}
                status = ProviderHealthStatus.DEGRADED.value

            if not provider.is_enabled:
                status = ProviderHealthStatus.DISABLED.value

            health.status = status
            health.last_success_at = _utcnow()
            health.consecutive_failures = 0
            health.last_error = None
            health.detail = detail
            health.updated_at = _utcnow()
            self.db.flush()
            self.db.commit()
            return {"provider_key": provider_key, "status": status, "detail": detail}
        except Exception as exc:  # noqa: BLE001 — probe must record failure
            health.status = ProviderHealthStatus.UNHEALTHY.value
            health.last_failure_at = _utcnow()
            health.consecutive_failures = int(health.consecutive_failures or 0) + 1
            health.last_error = str(exc)[:2000]
            health.detail = {"probe": "failed"}
            health.updated_at = _utcnow()
            self.db.add(
                MarketQualityFinding(
                    kind=QualityFindingKind.PROVIDER_ERROR.value,
                    provider_id=provider.id,
                    message=f"Provider probe failed: {exc}",
                    detail={"provider_key": provider_key},
                )
            )
            self.db.flush()
            self.db.commit()
            return {
                "provider_key": provider_key,
                "status": health.status,
                "detail": {"error": str(exc)},
            }

    def _http_probe_with_backoff(self, config: dict[str, Any]) -> dict[str, Any]:
        url = config.get("health_url")
        if not url:
            raise MarketIntelligenceError(
                "provider_misconfigured",
                "http_json adapter requires config.health_url",
            )
        import urllib.error
        import urllib.request

        last_err: Exception | None = None
        for attempt, delay in enumerate(self.BACKOFF_SECONDS[: self.MAX_RETRIES]):
            if attempt:
                time.sleep(delay)
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
                    return {"http_status": resp.status, "url": url}
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_err = exc
        raise MarketIntelligenceError("provider_unreachable", str(last_err))

    def ingest_batch(
        self,
        *,
        body: IngestBatchRequest,
        actor: AuthenticatedPrincipal,
        idempotency_key: str | None,
        request_id: str | None,
    ) -> dict[str, Any]:
        if idempotency_key:
            existing = self.db.get(MarketIngestionIdempotency, idempotency_key)
            if existing:
                run = self.db.get(MarketIngestionRun, existing.run_id)
                if run is None:
                    raise MarketIntelligenceError(
                        "idempotency_conflict", "Idempotency row missing run"
                    )
                return {
                    "run_id": str(run.id),
                    "status": run.status,
                    "records_attempted": run.records_attempted,
                    "records_accepted": run.records_accepted,
                    "records_duplicate": run.records_duplicate,
                    "records_rejected": run.records_rejected,
                    "idempotent_replay": True,
                    "error_summary": run.error_summary,
                }

        provider = self.get_provider(body.provider_key)
        if not provider.is_enabled:
            raise MarketIntelligenceError("provider_disabled", "Provider is disabled")

        run = MarketIngestionRun(
            provider_id=provider.id,
            channel=body.channel,
            status=IngestionRunStatus.RUNNING.value,
            created_by_user_id=actor.user.id,
        )
        self.db.add(run)
        self.db.flush()

        attempted = accepted = duplicate = rejected = 0
        errors: list[str] = []

        for bar in body.bars:
            attempted += 1
            try:
                result = self._ingest_bar(provider, bar)
                if result == "duplicate":
                    duplicate += 1
                else:
                    accepted += 1
            except Exception as exc:  # noqa: BLE001
                rejected += 1
                errors.append(f"bar:{exc}")

        for news_item in body.news:
            attempted += 1
            try:
                result = self._ingest_news(provider, news_item)
                if result == "duplicate":
                    duplicate += 1
                else:
                    accepted += 1
            except Exception as exc:  # noqa: BLE001
                rejected += 1
                errors.append(f"news:{exc}")

        for econ_item in body.economic_events:
            attempted += 1
            try:
                result = self._ingest_economic(provider, econ_item)
                if result == "duplicate":
                    duplicate += 1
                else:
                    accepted += 1
            except Exception as exc:  # noqa: BLE001
                rejected += 1
                errors.append(f"econ:{exc}")

        for research_item in body.research:
            attempted += 1
            try:
                result = self._ingest_research(provider, research_item)
                if result == "duplicate":
                    duplicate += 1
                else:
                    accepted += 1
            except Exception as exc:  # noqa: BLE001
                rejected += 1
                errors.append(f"research:{exc}")

        if rejected and accepted:
            status = IngestionRunStatus.PARTIAL.value
        elif rejected and not accepted:
            status = IngestionRunStatus.FAILED.value
        else:
            status = IngestionRunStatus.SUCCEEDED.value

        run.records_attempted = attempted
        run.records_accepted = accepted
        run.records_duplicate = duplicate
        run.records_rejected = rejected
        run.status = status
        run.finished_at = _utcnow()
        run.error_summary = "; ".join(errors[:20]) if errors else None
        run.detail = {"channel": body.channel}

        if idempotency_key:
            self.db.add(
                MarketIngestionIdempotency(
                    idempotency_key=idempotency_key,
                    run_id=run.id,
                    response_digest=_digest(
                        {
                            "run_id": str(run.id),
                            "status": status,
                            "accepted": accepted,
                        }
                    ),
                )
            )

        self._record_quality_after_ingest(provider, body.channel)
        self.audit.append(
            action="market.ingest.batch",
            resource_type="market_ingestion_run",
            resource_id=str(run.id),
            actor_user_id=actor.user.id,
            request_id=request_id,
            payload={
                "provider_key": body.provider_key,
                "channel": body.channel,
                "accepted": accepted,
                "duplicate": duplicate,
                "rejected": rejected,
            },
        )
        self.db.flush()
        self.db.commit()
        return {
            "run_id": str(run.id),
            "status": status,
            "records_attempted": attempted,
            "records_accepted": accepted,
            "records_duplicate": duplicate,
            "records_rejected": rejected,
            "idempotent_replay": False,
            "error_summary": run.error_summary,
        }

    def _ingest_bar(self, provider: MarketProvider, bar: Any) -> str:
        instrument = self.ensure_instrument(symbol=bar.symbol)
        if bar.high < bar.low or bar.open < 0 or bar.close < 0:
            raise MarketIntelligenceError("schema_invalid", "Invalid OHLC values")
        obs_key = bar.external_id or (
            f"ohlcv:{provider.provider_key}:{instrument.symbol}:"
            f"{bar.timeframe}:{bar.open_time.isoformat()}"
        )
        existing = self.db.scalar(
            select(MarketObservation).where(MarketObservation.idempotency_key == obs_key)
        )
        if existing:
            self.db.add(
                MarketQualityFinding(
                    kind=QualityFindingKind.DUPLICATE.value,
                    provider_id=provider.id,
                    instrument_id=instrument.id,
                    channel=ObservationChannel.OHLCV.value,
                    message="Duplicate OHLCV observation skipped",
                    detail={"idempotency_key": obs_key},
                )
            )
            return "duplicate"

        prior_bar = self.db.scalar(
            select(MarketOhlcvBar).where(
                MarketOhlcvBar.provider_id == provider.id,
                MarketOhlcvBar.instrument_id == instrument.id,
                MarketOhlcvBar.timeframe == bar.timeframe,
                MarketOhlcvBar.open_time == bar.open_time,
            )
        )
        if prior_bar is not None:
            return "duplicate"

        self.db.add(
            MarketOhlcvBar(
                provider_id=provider.id,
                instrument_id=instrument.id,
                timeframe=bar.timeframe,
                open_time=bar.open_time,
                close_time=bar.close_time,
                open=Decimal(bar.open),
                high=Decimal(bar.high),
                low=Decimal(bar.low),
                close=Decimal(bar.close),
                volume=Decimal(bar.volume) if bar.volume is not None else None,
                source_attribution=bar.source_attribution,
            )
        )
        self.db.add(
            MarketObservation(
                provider_id=provider.id,
                channel=ObservationChannel.OHLCV.value,
                observed_at=bar.open_time,
                title=f"{instrument.symbol} {bar.timeframe} bar",
                instrument_id=instrument.id,
                external_id=bar.external_id,
                idempotency_key=obs_key,
                source_attribution=bar.source_attribution,
                normalized={
                    "symbol": instrument.symbol,
                    "timeframe": bar.timeframe,
                    "open": str(bar.open),
                    "high": str(bar.high),
                    "low": str(bar.low),
                    "close": str(bar.close),
                },
                raw_payload=bar.model_dump(mode="json"),
            )
        )
        self.db.flush()
        return "accepted"

    def _obs_exists(self, key: str) -> bool:
        return (
            self.db.scalar(
                select(MarketObservation).where(MarketObservation.idempotency_key == key)
            )
            is not None
        )

    def _ingest_news(self, provider: MarketProvider, item: Any) -> str:
        key = f"news:{provider.provider_key}:{item.external_id}"
        if self._obs_exists(key):
            return "duplicate"
        obs = MarketObservation(
            provider_id=provider.id,
            channel=ObservationChannel.NEWS.value,
            observed_at=item.published_at,
            title=item.headline,
            summary=item.body,
            external_id=item.external_id,
            idempotency_key=key,
            source_attribution=item.source_attribution,
            normalized={"headline": item.headline, "url": item.url},
            raw_payload=item.model_dump(mode="json"),
        )
        self.db.add(obs)
        self.db.flush()
        self.db.add(
            MarketNewsItem(
                provider_id=provider.id,
                observation_id=obs.id,
                external_id=item.external_id,
                headline=item.headline,
                body=item.body,
                published_at=item.published_at,
                source_attribution=item.source_attribution,
                url=item.url,
            )
        )
        self.db.flush()
        return "accepted"

    def _ingest_economic(self, provider: MarketProvider, item: Any) -> str:
        key = f"econ:{provider.provider_key}:{item.external_id}"
        if self._obs_exists(key):
            return "duplicate"
        obs = MarketObservation(
            provider_id=provider.id,
            channel=ObservationChannel.ECONOMIC_EVENT.value,
            observed_at=item.scheduled_at,
            title=item.title,
            external_id=item.external_id,
            idempotency_key=key,
            source_attribution=item.source_attribution,
            normalized={
                "country": item.country,
                "importance": item.importance,
                "actual": item.actual,
                "forecast": item.forecast,
                "previous": item.previous,
            },
            raw_payload=item.model_dump(mode="json"),
        )
        self.db.add(obs)
        self.db.flush()
        self.db.add(
            MarketEconomicEvent(
                provider_id=provider.id,
                observation_id=obs.id,
                external_id=item.external_id,
                title=item.title,
                country=item.country,
                scheduled_at=item.scheduled_at,
                importance=item.importance,
                actual=item.actual,
                forecast=item.forecast,
                previous=item.previous,
                source_attribution=item.source_attribution,
            )
        )
        self.db.flush()
        return "accepted"

    def _ingest_research(self, provider: MarketProvider, item: Any) -> str:
        key = f"research:{provider.provider_key}:{item.external_id}"
        if self._obs_exists(key):
            return "duplicate"
        obs = MarketObservation(
            provider_id=provider.id,
            channel=ObservationChannel.RESEARCH.value,
            observed_at=item.published_at,
            title=item.title,
            summary=item.abstract,
            external_id=item.external_id,
            idempotency_key=key,
            source_attribution=item.source_attribution,
            normalized={"tags": item.tags},
            raw_payload=item.model_dump(mode="json"),
        )
        self.db.add(obs)
        self.db.flush()
        self.db.add(
            MarketResearchItem(
                provider_id=provider.id,
                observation_id=obs.id,
                external_id=item.external_id,
                title=item.title,
                abstract=item.abstract,
                published_at=item.published_at,
                source_attribution=item.source_attribution,
                tags=item.tags,
            )
        )
        self.db.flush()
        return "accepted"

    def _record_quality_after_ingest(self, provider: MarketProvider, channel: str) -> None:
        cutoff = _utcnow() - timedelta(hours=self.STALE_HOURS)
        latest = self.db.scalar(
            select(MarketObservation.observed_at)
            .where(
                MarketObservation.provider_id == provider.id,
                MarketObservation.channel == channel,
            )
            .order_by(MarketObservation.observed_at.desc())
            .limit(1)
        )
        if latest is not None and latest < cutoff:
            self.db.add(
                MarketQualityFinding(
                    kind=QualityFindingKind.STALE.value,
                    provider_id=provider.id,
                    channel=channel,
                    message=f"Latest observation older than {self.STALE_HOURS}h",
                    detail={"latest": latest.isoformat()},
                )
            )

    def list_bars(
        self,
        *,
        symbol: str | None,
        timeframe: str | None,
        limit: int,
        offset: int,
    ) -> list[MarketOhlcvBar]:
        stmt = select(MarketOhlcvBar).order_by(MarketOhlcvBar.open_time.desc())
        if symbol:
            inst = self.db.scalar(
                select(MarketInstrument).where(MarketInstrument.symbol == symbol.upper())
            )
            if inst is None:
                return []
            stmt = stmt.where(MarketOhlcvBar.instrument_id == inst.id)
        if timeframe:
            stmt = stmt.where(MarketOhlcvBar.timeframe == timeframe)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

    def list_observations(
        self, *, channel: str | None, limit: int, offset: int
    ) -> list[MarketObservation]:
        stmt = select(MarketObservation).order_by(MarketObservation.observed_at.desc())
        if channel:
            stmt = stmt.where(MarketObservation.channel == channel)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

    def list_news(self, *, limit: int, offset: int) -> list[MarketNewsItem]:
        return list(
            self.db.scalars(
                select(MarketNewsItem)
                .order_by(MarketNewsItem.published_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )

    def list_economic(self, *, limit: int, offset: int) -> list[MarketEconomicEvent]:
        return list(
            self.db.scalars(
                select(MarketEconomicEvent)
                .order_by(MarketEconomicEvent.scheduled_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )

    def list_research(self, *, limit: int, offset: int) -> list[MarketResearchItem]:
        return list(
            self.db.scalars(
                select(MarketResearchItem)
                .order_by(MarketResearchItem.published_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )

    def list_runs(self, *, limit: int, offset: int) -> list[MarketIngestionRun]:
        return list(
            self.db.scalars(
                select(MarketIngestionRun)
                .order_by(MarketIngestionRun.started_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )

    def list_quality(self, *, open_only: bool, limit: int) -> list[MarketQualityFinding]:
        stmt = select(MarketQualityFinding).order_by(MarketQualityFinding.detected_at.desc())
        if open_only:
            stmt = stmt.where(MarketQualityFinding.resolved_at.is_(None))
        return list(self.db.scalars(stmt.limit(limit)))
