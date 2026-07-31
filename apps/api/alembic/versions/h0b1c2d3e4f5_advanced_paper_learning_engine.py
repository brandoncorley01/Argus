"""Advanced paper learning engine tables (20-day cycle, PAPER only)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "h0b1c2d3e4f5"
down_revision: str | None = "g9a0b1c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if "paper_learning_programs" not in tables:
        op.create_table(
            "paper_learning_programs",
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
            sa.Column("cycle_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("required_days", sa.Integer(), nullable=False, server_default="20"),
            sa.Column("started_on", sa.Date(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("completed_on", sa.Date(), nullable=True),
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
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint(
                "portfolio_id", "cycle_number", name="uq_paper_learning_program_cycle"
            ),
        )
        op.create_index(
            "ix_paper_learning_programs_portfolio",
            "paper_learning_programs",
            ["portfolio_id"],
        )

    if "paper_learning_day_snapshots" not in tables:
        op.create_table(
            "paper_learning_day_snapshots",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "program_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("paper_learning_programs.id"),
                nullable=False,
            ),
            sa.Column(
                "portfolio_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("paper_portfolios.id"),
                nullable=False,
            ),
            sa.Column("day_index", sa.Integer(), nullable=False),
            sa.Column("day_date", sa.Date(), nullable=False),
            sa.Column(
                "net_pnl_after_costs",
                sa.Numeric(24, 8),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "day_pnl_after_costs",
                sa.Numeric(24, 8),
                nullable=False,
                server_default="0",
            ),
            sa.Column("trades_closed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("wins", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("losses", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("win_rate", sa.Numeric(8, 4), nullable=True),
            sa.Column("profit_factor", sa.Numeric(12, 4), nullable=True),
            sa.Column("expectancy_after_costs", sa.Numeric(24, 8), nullable=True),
            sa.Column("max_drawdown", sa.Numeric(24, 8), nullable=True),
            sa.Column("leading_strategy", sa.String(64), nullable=True),
            sa.Column("best_coin", sa.String(64), nullable=True),
            sa.Column("learning_confidence", sa.Numeric(8, 4), nullable=True),
            sa.Column("readiness_score", sa.Numeric(8, 4), nullable=True),
            sa.Column(
                "metrics",
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
            sa.UniqueConstraint(
                "program_id", "day_index", name="uq_paper_learning_day_index"
            ),
            sa.UniqueConstraint(
                "program_id", "day_date", name="uq_paper_learning_day_date"
            ),
        )
        op.create_index(
            "ix_paper_learning_day_program",
            "paper_learning_day_snapshots",
            ["program_id"],
        )

    if "paper_learning_milestones" not in tables:
        op.create_table(
            "paper_learning_milestones",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "program_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("paper_learning_programs.id"),
                nullable=False,
            ),
            sa.Column(
                "portfolio_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("paper_portfolios.id"),
                nullable=False,
            ),
            sa.Column("milestone_key", sa.String(64), nullable=False),
            sa.Column("title", sa.String(128), nullable=False),
            sa.Column("achieved", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "evidence",
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
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint(
                "program_id", "milestone_key", name="uq_paper_learning_milestone"
            ),
        )
        op.create_index(
            "ix_paper_learning_milestones_program",
            "paper_learning_milestones",
            ["program_id"],
        )

    if "paper_strategy_confidence_states" not in tables:
        op.create_table(
            "paper_strategy_confidence_states",
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
            sa.Column("strategy_key", sa.String(64), nullable=False),
            sa.Column(
                "confidence_delta", sa.Numeric(8, 4), nullable=False, server_default="0"
            ),
            sa.Column("sample_trades", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("reversible", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("paper_only", sa.Boolean(), nullable=False, server_default="true"),
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
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint(
                "portfolio_id",
                "strategy_key",
                name="uq_paper_strategy_confidence",
            ),
        )

    if "paper_learning_readiness_reports" not in tables:
        op.create_table(
            "paper_learning_readiness_reports",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "program_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("paper_learning_programs.id"),
                nullable=False,
            ),
            sa.Column(
                "portfolio_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("paper_portfolios.id"),
                nullable=False,
            ),
            sa.Column("report_date", sa.Date(), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column(
                "ready_for_controlled_live_testing",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
            sa.Column(
                "live_trading_enabled",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column(
                "body",
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
            sa.UniqueConstraint(
                "program_id", name="uq_paper_learning_readiness_program"
            ),
        )
        op.create_index(
            "ix_paper_learning_readiness_portfolio",
            "paper_learning_readiness_reports",
            ["portfolio_id"],
        )


def downgrade() -> None:
    op.drop_table("paper_learning_readiness_reports")
    op.drop_table("paper_strategy_confidence_states")
    op.drop_table("paper_learning_milestones")
    op.drop_table("paper_learning_day_snapshots")
    op.drop_table("paper_learning_programs")
