"""Trading intelligence + Founder certification tracking (paper only)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if "trade_decision_snapshots" not in tables:
        op.create_table(
            "trade_decision_snapshots",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "portfolio_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("paper_portfolios.id"),
                nullable=True,
            ),
            sa.Column(
                "candidate_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("market_scan_candidates.id"),
                nullable=True,
            ),
            sa.Column(
                "entry_order_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("paper_orders.id"),
                nullable=True,
            ),
            sa.Column("symbol", sa.String(64), nullable=False),
            sa.Column("strategy_key", sa.String(64), nullable=False),
            sa.Column(
                "strategy_version",
                sa.String(64),
                nullable=False,
                server_default="sma_crossover@1",
            ),
            sa.Column("confidence_score", sa.Numeric(8, 4), nullable=False),
            sa.Column("confidence_label", sa.String(16), nullable=False),
            sa.Column("explanation", sa.Text(), nullable=False),
            sa.Column("market_regime", sa.String(32), nullable=False),
            sa.Column(
                "detail",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
        op.create_index(
            "ix_trade_decision_symbol_created",
            "trade_decision_snapshots",
            ["symbol", "created_at"],
        )
        op.create_index(
            "ix_trade_decision_order",
            "trade_decision_snapshots",
            ["entry_order_id"],
        )

    if "post_trade_reviews" not in tables:
        op.create_table(
            "post_trade_reviews",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "portfolio_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("paper_portfolios.id"),
                nullable=False,
            ),
            sa.Column("symbol", sa.String(64), nullable=False),
            sa.Column(
                "entry_order_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("paper_orders.id"),
                nullable=True,
            ),
            sa.Column(
                "exit_order_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("paper_orders.id"),
                nullable=False,
            ),
            sa.Column(
                "decision_snapshot_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("trade_decision_snapshots.id"),
                nullable=True,
            ),
            sa.Column("confidence_score", sa.Numeric(8, 4), nullable=False),
            sa.Column("outcome", sa.String(32), nullable=False),
            sa.Column("realized_pnl", sa.Numeric(24, 8), nullable=False),
            sa.Column("max_drawdown", sa.Numeric(24, 8), nullable=True),
            sa.Column(
                "holding_seconds", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("exit_reason", sa.String(64), nullable=False),
            sa.Column("market_regime", sa.String(32), nullable=False),
            sa.Column("strategy_key", sa.String(64), nullable=False),
            sa.Column("strategy_version", sa.String(64), nullable=False),
            sa.Column("good_decision", sa.Boolean(), nullable=True),
            sa.Column("explanation", sa.Text(), nullable=False),
            sa.Column(
                "detail",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint("exit_order_id", name="uq_post_trade_reviews_exit_order"),
        )
        op.create_index(
            "ix_post_trade_reviews_symbol",
            "post_trade_reviews",
            ["symbol", "closed_at"],
        )

    if "missed_opportunities" not in tables:
        op.create_table(
            "missed_opportunities",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "candidate_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("market_scan_candidates.id"),
                nullable=True,
            ),
            sa.Column("symbol", sa.String(64), nullable=False),
            sa.Column("strategy_key", sa.String(64), nullable=False),
            sa.Column("confidence_score", sa.Numeric(8, 4), nullable=False),
            sa.Column("market_regime", sa.String(32), nullable=False),
            sa.Column("reason_code", sa.String(64), nullable=True),
            sa.Column("entry_zone", sa.Numeric(24, 8), nullable=True),
            sa.Column("stop_loss", sa.Numeric(24, 8), nullable=True),
            sa.Column("take_profit", sa.Numeric(24, 8), nullable=True),
            sa.Column(
                "outcome", sa.String(32), nullable=False, server_default="pending"
            ),
            sa.Column(
                "detail",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "candidate_id", name="uq_missed_opportunities_candidate"
            ),
        )
        op.create_index(
            "ix_missed_opportunities_symbol",
            "missed_opportunities",
            ["symbol", "created_at"],
        )

    if "founder_certification_state" not in tables:
        op.create_table(
            "founder_certification_state",
            sa.Column("id", sa.Integer(), primary_key=True, server_default="1"),
            sa.Column(
                "founder_approved",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("founder_approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("founder_approved_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("tracking_started_on", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column(
                "detail",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint("id", name="uq_founder_certification_singleton"),
        )
        op.execute(
            "INSERT INTO founder_certification_state (id, founder_approved) "
            "VALUES (1, false) ON CONFLICT DO NOTHING"
        )


def downgrade() -> None:
    for table in (
        "founder_certification_state",
        "missed_opportunities",
        "post_trade_reviews",
        "trade_decision_snapshots",
    ):
        op.drop_table(table)
