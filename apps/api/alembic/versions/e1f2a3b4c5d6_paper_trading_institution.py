"""Phase 12 Paper Trading Institution / Execution Gateway schema."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "execution_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("provider_key", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("provider_kind", sa.String(32), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("capabilities", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "execution_provider_health",
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("execution_providers.id"), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "paper_portfolios",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("cash_balance", sa.Numeric(24, 8), nullable=False),
        sa.Column("reserved_cash", sa.Numeric(24, 8), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("kill_switch_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("default_provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("execution_providers.id"), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "paper_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paper_portfolios.id"), nullable=False),
        sa.Column("strategy_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("strategy_versions.id"), nullable=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("execution_providers.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False, server_default=sa.text("42")),
        sa.Column("assumptions", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_table(
        "paper_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paper_portfolios.id"), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("execution_providers.id"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paper_sessions.id"), nullable=True),
        sa.Column("strategy_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("strategy_versions.id"), nullable=True),
        sa.Column("client_order_id", sa.String(128), nullable=False),
        sa.Column("provider_order_id", sa.String(128), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("order_type", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("filled_quantity", sa.Numeric(24, 8), nullable=False, server_default=sa.text("0")),
        sa.Column("limit_price", sa.Numeric(24, 8), nullable=True),
        sa.Column("average_fill_price", sa.Numeric(24, 8), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("idempotency_key", name="uq_paper_orders_idempotency"),
        sa.UniqueConstraint("portfolio_id", "client_order_id", name="uq_paper_orders_client_order"),
    )
    op.create_index("ix_paper_orders_portfolio_status", "paper_orders", ["portfolio_id", "status"])
    op.create_table(
        "paper_order_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paper_orders.id"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
    )
    op.create_index("ix_paper_order_events_order", "paper_order_events", ["order_id", "occurred_at"])
    op.create_table(
        "paper_fills",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paper_orders.id"), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paper_portfolios.id"), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("execution_providers.id"), nullable=False),
        sa.Column("provider_fill_id", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("price", sa.Numeric(24, 8), nullable=False),
        sa.Column("fee", sa.Numeric(24, 8), nullable=False, server_default=sa.text("0")),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("provider_fill_id", "provider_id", name="uq_paper_fills_provider"),
    )
    op.create_table(
        "paper_positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paper_portfolios.id"), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("average_cost", sa.Numeric(24, 8), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(24, 8), nullable=False, server_default=sa.text("0")),
        sa.Column("unrealized_pnl", sa.Numeric(24, 8), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("portfolio_id", "symbol", name="uq_paper_positions_symbol"),
    )
    op.create_table(
        "paper_cash_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paper_portfolios.id"), nullable=False),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("balance_after", sa.Numeric(24, 8), nullable=False),
        sa.Column("reference_type", sa.String(32), nullable=True),
        sa.Column("reference_id", sa.String(64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "paper_risk_limits",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paper_portfolios.id"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("limit_type", sa.String(64), nullable=False),
        sa.Column("threshold", sa.Numeric(24, 8), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("strategy_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("strategy_versions.id"), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "paper_risk_breaches",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paper_portfolios.id"), nullable=False),
        sa.Column("limit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paper_risk_limits.id"), nullable=True),
        sa.Column("limit_type", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paper_orders.id"), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "paper_replay_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paper_sessions.id"), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("state_blob", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("session_id", "sequence_number", name="uq_paper_replay_checkpoint_seq"),
    )
    op.create_table(
        "paper_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paper_portfolios.id"), nullable=False),
        sa.Column("report_type", sa.String(64), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("is_immutable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    caps = (
        '["connect","disconnect","health","readiness","capabilities","account_state",'
        '"balances","buying_power","positions","submit_order","cancel_order",'
        '"get_order","get_open_orders","get_fills","reconcile"]'
    )
    op.execute(
        f"""
        INSERT INTO execution_providers
          (provider_key, display_name, provider_kind, environment, is_default, capabilities, description)
        VALUES
        ('internal_paper', 'Internal Paper Execution Provider', 'paper', 'paper', true,
         '{caps}'::jsonb,
         'Default authoritative paper provider. No brokerage account required.'),
        ('deterministic_test', 'Deterministic Test Provider', 'deterministic_test', 'deterministic_test', false,
         '{caps}'::jsonb,
         'Fixture-oriented deterministic provider for tests.')
        """
    )
    op.execute(
        sa.text(
            """
            INSERT INTO execution_provider_health (provider_id, status, detail)
            SELECT id, 'healthy', CAST(:detail AS jsonb)
            FROM execution_providers
            """
        ).bindparams(detail='{"external_account_required": false}')
    )


def downgrade() -> None:
    for table in (
        "paper_reports",
        "paper_replay_checkpoints",
        "paper_risk_breaches",
        "paper_risk_limits",
        "paper_cash_ledger",
        "paper_positions",
        "paper_fills",
        "paper_order_events",
        "paper_orders",
        "paper_sessions",
        "paper_portfolios",
        "execution_provider_health",
        "execution_providers",
    ):
        op.drop_table(table)
