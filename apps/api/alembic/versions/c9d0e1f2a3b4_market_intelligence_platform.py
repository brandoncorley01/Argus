"""Phase 10 Market Intelligence Platform schema."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c0d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("provider_key", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("provider_kind", sa.String(32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("supports_failover", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "market_provider_health",
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_providers.id"), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "market_instruments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("symbol", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("asset_class", sa.String(32), nullable=False, server_default=sa.text("'crypto'")),
        sa.Column("base_asset", sa.String(32), nullable=True),
        sa.Column("quote_asset", sa.String(32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "market_ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_providers.id"), nullable=True),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_attempted", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("records_accepted", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("records_duplicate", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("records_rejected", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_table(
        "market_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_providers.id"), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_instruments.id"), nullable=True),
        sa.Column("external_id", sa.String(256), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("source_attribution", sa.String(256), nullable=False),
        sa.Column("normalized", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("idempotency_key", name="uq_market_observation_idempotency"),
    )
    op.create_index("ix_market_observations_channel_time", "market_observations", ["channel", "observed_at"])
    op.create_table(
        "market_ohlcv_bars",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_providers.id"), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_instruments.id"), nullable=False),
        sa.Column("timeframe", sa.String(16), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(36, 18), nullable=False),
        sa.Column("high", sa.Numeric(36, 18), nullable=False),
        sa.Column("low", sa.Numeric(36, 18), nullable=False),
        sa.Column("close", sa.Numeric(36, 18), nullable=False),
        sa.Column("volume", sa.Numeric(36, 18), nullable=True),
        sa.Column("source_attribution", sa.String(256), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint(
            "provider_id", "instrument_id", "timeframe", "open_time", name="uq_market_ohlcv_identity"
        ),
    )
    op.create_index("ix_market_ohlcv_instrument_time", "market_ohlcv_bars", ["instrument_id", "open_time"])
    op.create_table(
        "market_news_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_providers.id"), nullable=False),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_observations.id"), nullable=True),
        sa.Column("external_id", sa.String(256), nullable=False),
        sa.Column("headline", sa.String(512), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_attribution", sa.String(256), nullable=False),
        sa.Column("url", sa.String(1024), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("provider_id", "external_id", name="uq_market_news_external"),
    )
    op.create_table(
        "market_economic_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_providers.id"), nullable=False),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_observations.id"), nullable=True),
        sa.Column("external_id", sa.String(256), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("country", sa.String(8), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("importance", sa.String(16), nullable=True),
        sa.Column("actual", sa.String(64), nullable=True),
        sa.Column("forecast", sa.String(64), nullable=True),
        sa.Column("previous", sa.String(64), nullable=True),
        sa.Column("source_attribution", sa.String(256), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("provider_id", "external_id", name="uq_market_econ_external"),
    )
    op.create_table(
        "market_research_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_providers.id"), nullable=False),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_observations.id"), nullable=True),
        sa.Column("external_id", sa.String(256), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_attribution", sa.String(256), nullable=False),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("provider_id", "external_id", name="uq_market_research_external"),
    )
    op.create_table(
        "market_quality_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_providers.id"), nullable=True),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_instruments.id"), nullable=True),
        sa.Column("channel", sa.String(32), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_market_quality_open", "market_quality_findings", ["kind", "detected_at"])
    op.create_table(
        "market_ingestion_idempotency",
        sa.Column("idempotency_key", sa.String(128), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_ingestion_runs.id"), nullable=False),
        sa.Column("response_digest", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Seed governed providers — no fabricated market prices
    op.execute(
        """
        INSERT INTO market_providers (provider_key, display_name, provider_kind, priority, description, config)
        VALUES
        ('manual', 'Manual Observation Intake', 'aggregator', 10,
         'Founder/Operator submitted observations only. Does not invent market prices.',
         '{"adapter":"manual"}'::jsonb),
        ('null_probe', 'Null Health Probe', 'aggregator', 1000,
         'Provider health probe only. Never emits market, news, or research payloads.',
         '{"adapter":"null_probe"}'::jsonb)
        """
    )
    op.execute(
        """
        INSERT INTO market_provider_health (provider_id, status)
        SELECT id, 'unknown' FROM market_providers
        """
    )


def downgrade() -> None:
    op.drop_table("market_ingestion_idempotency")
    op.drop_index("ix_market_quality_open", table_name="market_quality_findings")
    op.drop_table("market_quality_findings")
    op.drop_table("market_research_items")
    op.drop_table("market_economic_events")
    op.drop_table("market_news_items")
    op.drop_index("ix_market_ohlcv_instrument_time", table_name="market_ohlcv_bars")
    op.drop_table("market_ohlcv_bars")
    op.drop_index("ix_market_observations_channel_time", table_name="market_observations")
    op.drop_table("market_observations")
    op.drop_table("market_ingestion_runs")
    op.drop_table("market_instruments")
    op.drop_table("market_provider_health")
    op.drop_table("market_providers")
