"""Phase 14 Treasury and Executive Analytics schema — simulated ledgers only.

No row created by this migration represents real capital or a completed
external transfer. ``treasury_accounts.is_simulated`` is constrained
``true``. ``external_transfer_instructions.status`` is constrained to
``draft`` / ``proposed`` / ``cancelled`` — there is no ``executed`` status
in this schema at all. See ADR-030.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACCOUNT_CLASSIFICATIONS_SQL = (
    "classification IN ('simulated','available','allocated','reserved',"
    "'deployed','restricted','unsettled','externally_held')"
)
_TRANSFER_STATUSES_SQL = "status IN ('draft','proposed','cancelled')"


def upgrade() -> None:
    op.create_table(
        "treasury_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("classification", sa.String(32), nullable=False, server_default=sa.text("'simulated'")),
        sa.Column("balance", sa.Numeric(24, 8), nullable=False, server_default=sa.text("0")),
        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("name", name="uq_treasury_accounts_name"),
        sa.CheckConstraint(_ACCOUNT_CLASSIFICATIONS_SQL, name="ck_treasury_accounts_classification"),
        sa.CheckConstraint("is_simulated = true", name="ck_treasury_accounts_simulated_only"),
    )
    op.create_index(
        "ix_treasury_accounts_classification", "treasury_accounts", ["classification"]
    )

    op.create_table(
        "capital_pools",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("treasury_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("pool_type", sa.String(64), nullable=False),
        sa.Column("balance", sa.Numeric(24, 8), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("account_id", "name", name="uq_capital_pools_account_name"),
    )

    op.create_table(
        "capital_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("pool_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("capital_pools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("max_amount", sa.Numeric(24, 8), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'requested'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("released_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_capital_allocations_pool_status", "capital_allocations", ["pool_id", "status"]
    )
    op.create_index(
        "ix_capital_allocations_target", "capital_allocations", ["target_type", "target_id"]
    )

    op.create_table(
        "capital_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("allocation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("capital_allocations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("reserved_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("released_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_capital_reservations_allocation", "capital_reservations", ["allocation_id", "status"]
    )

    op.create_table(
        "treasury_ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("treasury_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pool_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("capital_pools.id", ondelete="SET NULL"), nullable=True),
        sa.Column("allocation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("capital_allocations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entry_type", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("balance_after", sa.Numeric(24, 8), nullable=False),
        sa.Column("reference_type", sa.String(32), nullable=True),
        sa.Column("reference_id", sa.String(64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_treasury_ledger_entries_account", "treasury_ledger_entries", ["account_id", "created_at"]
    )

    op.create_table(
        "external_transfer_instructions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("treasury_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("destination_reference", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("environment_label", sa.String(32), nullable=False, server_default=sa.text("'simulated'")),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("execution_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("proposed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(_TRANSFER_STATUSES_SQL, name="ck_external_transfer_instructions_status"),
    )
    op.create_index(
        "ix_external_transfer_instructions_account",
        "external_transfer_instructions",
        ["account_id", "status"],
    )

    op.create_table(
        "performance_attribution_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("scope_ref", sa.String(128), nullable=True),
        sa.Column("environment_class", sa.String(32), nullable=False),
        sa.Column("amounts", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("unavailable_reason", sa.Text(), nullable=True),
        sa.Column("generated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_perf_attribution_scope_as_of", "performance_attribution_snapshots", ["scope", "as_of"]
    )
    op.create_index(
        "ix_perf_attribution_environment", "performance_attribution_snapshots", ["environment_class"]
    )

    op.create_table(
        "executive_kpi_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kpi_key", sa.String(128), nullable=False),
        sa.Column("value", sa.Numeric(30, 8), nullable=True),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("environment_class", sa.String(32), nullable=False),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_estimated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("generated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_executive_kpi_key_as_of", "executive_kpi_snapshots", ["kpi_key", "as_of"]
    )

    op.create_table(
        "institutional_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("report_type", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_immutable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("environment_disclaimer", sa.Text(), nullable=False),
        sa.Column("generated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("report_type", "version", name="uq_institutional_reports_type_version"),
    )
    op.create_index(
        "ix_institutional_reports_type_created", "institutional_reports", ["report_type", "created_at"]
    )

    op.create_table(
        "forecast_scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("scenario_type", sa.String(32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inputs", postgresql.JSONB(), nullable=False),
        sa.Column("outputs", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_deterministic", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("generated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_forecast_scenarios_type_as_of", "forecast_scenarios", ["scenario_type", "as_of"]
    )

    # --- seed: exactly one simulated treasury account + one linked pool; no real capital ---
    op.execute(
        """
        INSERT INTO treasury_accounts
          (name, currency, classification, balance, is_simulated, status, description)
        VALUES
          ('Paper Institutional Capital', 'USD', 'simulated', 0.00000000, true, 'active',
           'Phase 14 seed account. Represents internal paper/simulated capital only — '
           'never real money. No withdrawal or external transfer can ever be executed '
           'from this or any Argus treasury account (see ADR-030).')
        """
    )
    op.execute(
        """
        INSERT INTO capital_pools (account_id, name, pool_type, balance)
        SELECT id, 'General Reserve', 'operating_reserve', 0.00000000
        FROM treasury_accounts
        WHERE name = 'Paper Institutional Capital'
        """
    )


def downgrade() -> None:
    for table in (
        "forecast_scenarios",
        "institutional_reports",
        "executive_kpi_snapshots",
        "performance_attribution_snapshots",
        "external_transfer_instructions",
        "treasury_ledger_entries",
        "capital_reservations",
        "capital_allocations",
        "capital_pools",
        "treasury_accounts",
    ):
        op.drop_table(table)
