"""Phase 7 operating mode state machine schema

Revision ID: a7b8c9d0e1f2
Revises: c6a1f0e9d2b8
Create Date: 2026-07-17 18:10:00.000000

Notes:
- History version backfill is ordered by (changed_at ASC, id ASC) so pre-existing
  rows receive distinct monotonic previous/new state versions.
- system_states.state_version is reconciled to MAX(new_state_version) (or 0).
- current_mode is never rewritten; migration fails if history tip disagrees.
- Downgrade drops Phase 7 columns/tables/triggers; re-upgrade re-applies ordered
  backfill from remaining Phase 6 history columns.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "c6a1f0e9d2b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "system_states",
        sa.Column("state_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "system_states",
        sa.Column(
            "emergency_stop_active",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "system_states",
        sa.Column(
            "recovery_required",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "system_states",
        sa.Column("last_history_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "system_states",
        sa.Column("active_policy_version_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_system_states_active_policy_version_id",
        "system_states",
        "policy_versions",
        ["active_policy_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "operating_mode_history",
        sa.Column(
            "previous_state_version",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "operating_mode_history",
        sa.Column("new_state_version", sa.Integer(), nullable=True),
    )
    # H1 remediation: assign monotonic versions by stable historical order
    # (changed_at ASC, id ASC). Do not collapse all rows to version 1.
    op.execute(
        sa.text(
            """
            WITH ordered AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (ORDER BY changed_at ASC, id ASC) AS rn
                FROM operating_mode_history
            )
            UPDATE operating_mode_history AS h
            SET
                previous_state_version = o.rn - 1,
                new_state_version = o.rn
            FROM ordered AS o
            WHERE h.id = o.id
            """
        )
    )
    op.alter_column("operating_mode_history", "new_state_version", nullable=False)

    # Reconcile singleton state_version to latest history (0 when empty).
    # Preserve current_mode. Fail closed if history tip disagrees with current mode.
    op.execute(
        sa.text(
            """
            UPDATE system_states
            SET state_version = COALESCE(
                (SELECT MAX(new_state_version) FROM operating_mode_history),
                0
            )
            WHERE singleton_key = 'current'
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $guard$
            DECLARE
                hist_count integer;
                latest_to_mode text;
                current_mode_value text;
            BEGIN
                SELECT COUNT(*) INTO hist_count FROM operating_mode_history;
                IF hist_count = 0 THEN
                    RETURN;
                END IF;

                SELECT to_mode::text
                INTO latest_to_mode
                FROM operating_mode_history
                ORDER BY new_state_version DESC, changed_at DESC, id DESC
                LIMIT 1;

                SELECT current_mode::text
                INTO current_mode_value
                FROM system_states
                WHERE singleton_key = 'current';

                IF current_mode_value IS NULL THEN
                    RAISE EXCEPTION
                        'Phase 7 migration refused: operating_mode_history exists but '
                        'system_states singleton is missing'
                        USING ERRCODE = '23514';
                END IF;

                IF latest_to_mode IS DISTINCT FROM current_mode_value THEN
                    RAISE EXCEPTION
                        'Phase 7 migration refused: history tip to_mode=% disagrees with '
                        'system_states.current_mode=%',
                        latest_to_mode,
                        current_mode_value
                        USING ERRCODE = '23514';
                END IF;
            END
            $guard$
            """
        )
    )
    op.add_column(
        "operating_mode_history",
        sa.Column("policy_version_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "operating_mode_history",
        sa.Column("incident_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "operating_mode_history",
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "operating_mode_history",
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "operating_mode_history",
        sa.Column("prerequisite_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        "fk_operating_mode_history_policy_version_id",
        "operating_mode_history",
        "policy_versions",
        ["policy_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_operating_mode_history_incident_id",
        "operating_mode_history",
        "incidents",
        ["incident_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Circular FK: system_states.last_history_id -> operating_mode_history.id
    op.create_foreign_key(
        "fk_system_states_last_history_id",
        "system_states",
        "operating_mode_history",
        ["last_history_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "operating_mode_idempotency",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("history_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'committed'"),
            nullable=False,
        ),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["history_id"], ["operating_mode_history.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key_hash", name="uq_operating_mode_idempotency_key"),
    )
    op.create_index(
        "ix_operating_mode_idempotency_created_at",
        "operating_mode_idempotency",
        ["created_at"],
        unique=False,
    )

    # Append-only history: block UPDATE/DELETE of committed transition rows.
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION enforce_operating_mode_history_immutability()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION
                    'operating_mode_history is append-only (operation=%)',
                    TG_OP
                    USING ERRCODE = '23514';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_operating_mode_history_immutability ON operating_mode_history"))
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_operating_mode_history_immutability
            BEFORE UPDATE OR DELETE ON operating_mode_history
            FOR EACH ROW EXECUTE FUNCTION enforce_operating_mode_history_immutability()
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_operating_mode_history_immutability ON operating_mode_history"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS enforce_operating_mode_history_immutability()"))

    op.drop_index("ix_operating_mode_idempotency_created_at", table_name="operating_mode_idempotency")
    op.drop_table("operating_mode_idempotency")

    op.drop_constraint("fk_system_states_last_history_id", "system_states", type_="foreignkey")
    op.drop_constraint(
        "fk_operating_mode_history_incident_id", "operating_mode_history", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_operating_mode_history_policy_version_id",
        "operating_mode_history",
        type_="foreignkey",
    )
    op.drop_column("operating_mode_history", "prerequisite_summary")
    op.drop_column("operating_mode_history", "request_fingerprint")
    op.drop_column("operating_mode_history", "idempotency_key_hash")
    op.drop_column("operating_mode_history", "incident_id")
    op.drop_column("operating_mode_history", "policy_version_id")
    op.drop_column("operating_mode_history", "new_state_version")
    op.drop_column("operating_mode_history", "previous_state_version")

    op.drop_constraint(
        "fk_system_states_active_policy_version_id", "system_states", type_="foreignkey"
    )
    op.drop_column("system_states", "active_policy_version_id")
    op.drop_column("system_states", "last_history_id")
    op.drop_column("system_states", "recovery_required")
    op.drop_column("system_states", "emergency_stop_active")
    op.drop_column("system_states", "state_version")
