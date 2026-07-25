"""Market scan cycles, candidates, and decision events for Command Center.

Observation-only instrumentation. Does not enable live trading.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: str | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if "market_scan_cycles" not in tables:
        op.create_table(
            "market_scan_cycles",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("timeframe", sa.String(16), nullable=False, server_default="15m"),
            sa.Column(
                "strategy_key", sa.String(64), nullable=False, server_default="sma_crossover"
            ),
            sa.Column("symbols_total", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("symbols_scanned", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("candidates_found", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_symbol", sa.String(64), nullable=True),
            sa.Column(
                "rejection_counts",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "pipeline_counts",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "detail",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("correlation_id", sa.String(64), nullable=False),
            sa.Column(
                "started_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_market_scan_cycles_started", "market_scan_cycles", ["started_at"]
        )

    if "market_scan_candidates" not in tables:
        op.create_table(
            "market_scan_candidates",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "cycle_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("market_scan_cycles.id"),
                nullable=False,
            ),
            sa.Column("symbol", sa.String(64), nullable=False),
            sa.Column("timeframe", sa.String(16), nullable=False),
            sa.Column("strategy_key", sa.String(64), nullable=False),
            sa.Column("bias", sa.String(16), nullable=False),
            sa.Column("stage", sa.String(32), nullable=False),
            sa.Column("score", sa.Numeric(12, 4), nullable=False),
            sa.Column("risk_status", sa.String(32), nullable=False),
            sa.Column("reason_code", sa.String(64), nullable=True),
            sa.Column("reason_text", sa.Text(), nullable=True),
            sa.Column("current_price", sa.Numeric(36, 18), nullable=True),
            sa.Column("entry_zone", sa.Numeric(36, 18), nullable=True),
            sa.Column("stop_loss", sa.Numeric(36, 18), nullable=True),
            sa.Column("take_profit", sa.Numeric(36, 18), nullable=True),
            sa.Column("market_data_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "evaluated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "detail",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
        op.create_index(
            "ix_market_scan_candidates_cycle", "market_scan_candidates", ["cycle_id"]
        )
        op.create_index(
            "ix_market_scan_candidates_stage", "market_scan_candidates", ["stage"]
        )
        op.create_index(
            "ix_market_scan_candidates_score", "market_scan_candidates", ["score"]
        )

    if "market_scan_events" not in tables:
        op.create_table(
            "market_scan_events",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "cycle_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("market_scan_cycles.id"),
                nullable=True,
            ),
            sa.Column(
                "candidate_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("market_scan_candidates.id"),
                nullable=True,
            ),
            sa.Column(
                "occurred_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("component", sa.String(64), nullable=False),
            sa.Column("symbol", sa.String(64), nullable=True),
            sa.Column("stage", sa.String(32), nullable=True),
            sa.Column("outcome", sa.String(32), nullable=False),
            sa.Column("reason_code", sa.String(64), nullable=True),
            sa.Column("title", sa.String(256), nullable=False),
            sa.Column("detail", sa.Text(), nullable=False, server_default=""),
            sa.Column("strategy_key", sa.String(64), nullable=True),
            sa.Column("correlation_id", sa.String(64), nullable=False),
            sa.Column(
                "payload",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
        op.create_index(
            "ix_market_scan_events_occurred", "market_scan_events", ["occurred_at"]
        )
        op.create_index(
            "ix_market_scan_events_cycle", "market_scan_events", ["cycle_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if "market_scan_events" in tables:
        op.drop_table("market_scan_events")
    if "market_scan_candidates" in tables:
        op.drop_table("market_scan_candidates")
    if "market_scan_cycles" in tables:
        op.drop_table("market_scan_cycles")
