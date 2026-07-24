"""Phase 13 Micro-Live Institution schema — deny-by-default architecture.

No row created by this migration represents an active live-trading
capability: the singleton activation state seeds to ``PAPER_ONLY``, the
global kill switch seeds inactive-but-present, no credential references are
seeded (none required), and every optional adapter registry row seeds
``is_enabled=false`` / ``supports_live=false`` / ``verification_status`` no
higher than ``contract_tested``. See ADR-029.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- extend execution_providers with the Phase 13 maturity ladder ---
    op.add_column(
        "execution_providers",
        sa.Column(
            "verification_status",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'implemented_unverified'"),
        ),
    )
    op.add_column(
        "execution_providers",
        sa.Column(
            "supports_live", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.execute(
        "UPDATE execution_providers SET verification_status = 'contract_tested' "
        "WHERE provider_key IN ('internal_paper', 'deterministic_test')"
    )

    op.create_table(
        "live_activation_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("singleton_key", sa.String(32), nullable=False, server_default=sa.text("'current'")),
        sa.Column("current_state", sa.String(64), nullable=False, server_default=sa.text("'PAPER_ONLY'")),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("singleton_key", name="uq_live_activation_state_singleton_key"),
    )
    op.create_table(
        "live_activation_transitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("from_state", sa.String(64), nullable=True),
        sa.Column("to_state", sa.String(64), nullable=False),
        sa.Column("previous_state_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("new_state_version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_live_activation_transitions_changed_at", "live_activation_transitions", ["changed_at"]
    )
    op.create_table(
        "credential_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("provider_key", sa.String(64), nullable=False),
        sa.Column("ref_name", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(256), nullable=False),
        sa.Column("is_present_cached", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("provider_key", "ref_name", name="uq_credential_references_provider_ref"),
    )
    op.create_table(
        "kill_switches",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.String(128), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("activated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleared_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_kill_switches_scope", "kill_switches", ["scope_type", "scope_id"])
    op.create_table(
        "micro_capital_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("max_deployable_capital", sa.Numeric(24, 8), nullable=False),
        sa.Column("max_order_notional", sa.Numeric(24, 8), nullable=False),
        sa.Column("max_daily_loss", sa.Numeric(24, 8), nullable=False),
        sa.Column("max_concurrent_exposure", sa.Numeric(24, 8), nullable=False),
        sa.Column("max_provider_exposure", sa.Numeric(24, 8), nullable=False),
        sa.Column("max_strategy_exposure", sa.Numeric(24, 8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "uq_micro_capital_policies_one_active",
        "micro_capital_policies",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("provider_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'running'")),
        sa.Column("discrepancies", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("initiated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_reconciliation_runs_started_at", "reconciliation_runs", ["started_at"])
    op.create_table(
        "reconciliation_discrepancies",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_reconciliation_discrepancies_run", "reconciliation_discrepancies", ["run_id"]
    )

    # --- seeds: PAPER_ONLY singleton, inactive global kill switch, conservative policy ---
    op.execute(
        "INSERT INTO live_activation_state (current_state, state_version, evidence) "
        "VALUES ('PAPER_ONLY', 0, "
        "'{\"reason\": \"phase_13_initial_state\", \"credentials_configured\": false}'::jsonb)"
    )
    op.execute(
        "INSERT INTO kill_switches (scope_type, scope_id, active, reason) "
        "VALUES ('global', NULL, false, 'Phase 13 seed — global kill switch present, inactive')"
    )
    op.execute(
        "INSERT INTO micro_capital_policies "
        "(version, max_deployable_capital, max_order_notional, max_daily_loss, "
        " max_concurrent_exposure, max_provider_exposure, max_strategy_exposure, is_active) "
        "VALUES (1, 100.00000000, 10.00000000, 5.00000000, 100.00000000, 100.00000000, "
        " 50.00000000, true)"
    )

    # --- optional, disabled adapter registry rows (no account required) ---
    op.execute(
        """
        INSERT INTO execution_providers
          (provider_key, display_name, provider_kind, environment, is_default, is_enabled,
           capabilities, config, description, verification_status, supports_live)
        VALUES
        ('coinbase_adapter', 'Coinbase Adapter (optional)', 'live_adapter', 'live', false, false,
         '[]'::jsonb, '{}'::jsonb,
         'Optional plug-in scaffold. No brokerage/exchange account required to run Argus. Live execution permanently disabled in Phase 13.',
         'contract_tested', false),
        ('kraken_adapter', 'Kraken Adapter (optional)', 'live_adapter', 'live', false, false,
         '[]'::jsonb, '{}'::jsonb,
         'Optional plug-in scaffold. No brokerage/exchange account required to run Argus. Live execution permanently disabled in Phase 13.',
         'contract_tested', false),
        ('ibkr_adapter', 'Interactive Brokers Adapter (optional)', 'live_adapter', 'live', false, false,
         '[]'::jsonb, '{}'::jsonb,
         'Optional plug-in scaffold. No brokerage account required to run Argus. Live execution permanently disabled in Phase 13.',
         'contract_tested', false)
        """
    )
    op.execute(
        sa.text(
            """
            INSERT INTO execution_provider_health (provider_id, status, detail)
            SELECT id, 'unknown', CAST(:detail AS jsonb)
            FROM execution_providers
            WHERE provider_key IN ('coinbase_adapter', 'kraken_adapter', 'ibkr_adapter')
            """
        ).bindparams(
            detail='{"external_account_required": false, "credentials_configured": false, "live_enabled": false}'
        )
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM execution_provider_health WHERE provider_id IN ("
        "SELECT id FROM execution_providers WHERE provider_key IN "
        "('coinbase_adapter', 'kraken_adapter', 'ibkr_adapter'))"
    )
    op.execute(
        "DELETE FROM execution_providers WHERE provider_key IN "
        "('coinbase_adapter', 'kraken_adapter', 'ibkr_adapter')"
    )
    for table in (
        "reconciliation_discrepancies",
        "reconciliation_runs",
        "micro_capital_policies",
        "kill_switches",
        "credential_references",
        "live_activation_transitions",
        "live_activation_state",
    ):
        op.drop_table(table)
    op.drop_column("execution_providers", "supports_live")
    op.drop_column("execution_providers", "verification_status")
