"""Paper Training Lab schema — coaching mode + Founder feedback (paper only)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if "paper_training_settings" not in tables:
        op.create_table(
            "paper_training_settings",
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
            sa.Column("mode", sa.String(32), nullable=False, server_default="coaching"),
            sa.Column(
                "default_notional",
                sa.Numeric(24, 8),
                nullable=False,
                server_default="100",
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint("portfolio_id", name="uq_paper_training_settings_portfolio"),
        )

    if "paper_coaching_decisions" not in tables:
        op.create_table(
            "paper_coaching_decisions",
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
            sa.Column(
                "candidate_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("market_scan_candidates.id"),
                nullable=True,
            ),
            sa.Column("symbol", sa.String(64), nullable=False),
            sa.Column("action", sa.String(16), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column(
                "resulting_order_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("paper_orders.id"),
                nullable=True,
            ),
            sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "created_at",
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
            "ix_paper_coaching_candidate", "paper_coaching_decisions", ["candidate_id"]
        )

    if "paper_trade_feedback" not in tables:
        op.create_table(
            "paper_trade_feedback",
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
            sa.Column(
                "fill_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("paper_fills.id"),
                nullable=True,
            ),
            sa.Column(
                "candidate_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("market_scan_candidates.id"),
                nullable=True,
            ),
            sa.Column("symbol", sa.String(64), nullable=False),
            sa.Column("feedback_code", sa.String(64), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("strategy_key", sa.String(64), nullable=True),
            sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "created_at",
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
            "ix_paper_trade_feedback_symbol", "paper_trade_feedback", ["symbol"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if "paper_trade_feedback" in tables:
        op.drop_table("paper_trade_feedback")
    if "paper_coaching_decisions" in tables:
        op.drop_table("paper_coaching_decisions")
    if "paper_training_settings" in tables:
        op.drop_table("paper_training_settings")
