"""Pydantic schemas for Market Intelligence APIs (Phase 10)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MarketProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_key: str
    display_name: str
    provider_kind: str
    priority: int
    is_enabled: bool
    supports_failover: bool
    config: dict[str, Any]
    description: str | None
    created_at: datetime
    updated_at: datetime


class MarketProviderHealthRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider_id: uuid.UUID
    status: str
    last_success_at: datetime | None
    last_failure_at: datetime | None
    consecutive_failures: int
    last_error: str | None
    detail: dict[str, Any]
    updated_at: datetime


class ProviderWithHealthRead(BaseModel):
    provider: MarketProviderRead
    health: MarketProviderHealthRead | None


class MarketInstrumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    display_name: str
    asset_class: str
    base_asset: str | None
    quote_asset: str | None
    is_active: bool
    created_at: datetime


class MarketInstrumentCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    asset_class: str = Field(default="crypto", max_length=32)
    base_asset: str | None = Field(default=None, max_length=32)
    quote_asset: str | None = Field(default=None, max_length=32)


class OhlcvBarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    instrument_id: uuid.UUID
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    source_attribution: str
    ingested_at: datetime


class OhlcvBarIngest(BaseModel):
    symbol: str
    timeframe: str = Field(min_length=1, max_length=16)
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None
    source_attribution: str = Field(min_length=1, max_length=256)
    external_id: str | None = None


class NewsIngest(BaseModel):
    external_id: str = Field(min_length=1, max_length=256)
    headline: str = Field(min_length=1, max_length=512)
    body: str | None = None
    published_at: datetime
    source_attribution: str = Field(min_length=1, max_length=256)
    url: str | None = Field(default=None, max_length=1024)


class EconomicEventIngest(BaseModel):
    external_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=512)
    scheduled_at: datetime
    source_attribution: str = Field(min_length=1, max_length=256)
    country: str | None = Field(default=None, max_length=8)
    importance: str | None = Field(default=None, max_length=16)
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None


class ResearchIngest(BaseModel):
    external_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=512)
    published_at: datetime
    source_attribution: str = Field(min_length=1, max_length=256)
    abstract: str | None = None
    tags: list[str] = Field(default_factory=list)


class IngestBatchRequest(BaseModel):
    """Manual / provider batch ingest. Observation only — no signals or orders."""

    provider_key: str = Field(default="manual", min_length=1, max_length=64)
    channel: str = Field(min_length=1, max_length=32)
    bars: list[OhlcvBarIngest] = Field(default_factory=list)
    news: list[NewsIngest] = Field(default_factory=list)
    economic_events: list[EconomicEventIngest] = Field(default_factory=list)
    research: list[ResearchIngest] = Field(default_factory=list)


class IngestBatchResponse(BaseModel):
    run_id: str
    status: str
    records_attempted: int
    records_accepted: int
    records_duplicate: int
    records_rejected: int
    idempotent_replay: bool = False
    error_summary: str | None = None


class ObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    channel: str
    observed_at: datetime
    title: str
    summary: str | None
    instrument_id: uuid.UUID | None
    external_id: str | None
    source_attribution: str
    normalized: dict[str, Any]
    ingested_at: datetime


class NewsItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    external_id: str
    headline: str
    body: str | None
    published_at: datetime
    source_attribution: str
    url: str | None
    ingested_at: datetime


class EconomicEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    external_id: str
    title: str
    country: str | None
    scheduled_at: datetime
    importance: str | None
    actual: str | None
    forecast: str | None
    previous: str | None
    source_attribution: str
    ingested_at: datetime


class ResearchItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    external_id: str
    title: str
    abstract: str | None
    published_at: datetime
    source_attribution: str
    tags: list[Any]
    ingested_at: datetime


class IngestionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID | None
    channel: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    records_attempted: int
    records_accepted: int
    records_duplicate: int
    records_rejected: int
    error_summary: str | None


class QualityFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    provider_id: uuid.UUID | None
    instrument_id: uuid.UUID | None
    channel: str | None
    message: str
    detail: dict[str, Any]
    detected_at: datetime
    resolved_at: datetime | None


class ProviderProbeResponse(BaseModel):
    provider_key: str
    status: str
    detail: dict[str, Any]
