"""Phase 15 Operational Validation schema.

Adds an append-only operational event log, periodic host resource
snapshots, and immutable daily paper-trading operations reports. This
migration introduces no new external services, no trading logic, and no
live-trading capability — it is purely observational/reporting schema for
existing paper/health/incident/treasury subsystems.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OPERATIONAL_COMPONENTS_SQL = (
    "component IN ('api','worker','database','queue','market_data',"
    "'paper_provider','scheduler','host')"
)
_OPERATIONAL_SEVERITIES_SQL = "severity IN ('critical','high','medium','info')"


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("operational_events"):
        op.create_table(
            "operational_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("component", sa.String(32), nullable=False),
            sa.Column("severity", sa.String(16), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("correlation_id", sa.String(64), nullable=False),
            sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.CheckConstraint(_OPERATIONAL_COMPONENTS_SQL, name="ck_operational_events_component"),
            sa.CheckConstraint(_OPERATIONAL_SEVERITIES_SQL, name="ck_operational_events_severity"),
        )
        op.create_index("ix_operational_events_occurred_at", "operational_events", ["occurred_at"])
        op.create_index("ix_operational_events_correlation_id", "operational_events", ["correlation_id"])
        op.create_index("ix_operational_events_component", "operational_events", ["component"])
        op.create_index("ix_operational_events_severity", "operational_events", ["severity"])

    if not insp.has_table("host_resource_snapshots"):
        op.create_table(
            "host_resource_snapshots",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("cpu_percent", sa.Float(), nullable=False),
            sa.Column("memory_percent", sa.Float(), nullable=False),
            sa.Column("memory_used_bytes", sa.BigInteger(), nullable=False),
            sa.Column("disk_percent", sa.Float(), nullable=False),
            sa.Column("disk_used_bytes", sa.BigInteger(), nullable=False),
            sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )
        op.create_index(
            "ix_host_resource_snapshots_captured_at", "host_resource_snapshots", ["captured_at"]
        )
    else:
        existing = {ix["name"] for ix in insp.get_indexes("host_resource_snapshots")}
        if "ix_host_resource_snapshots_captured_at" not in existing:
            op.create_index(
                "ix_host_resource_snapshots_captured_at", "host_resource_snapshots", ["captured_at"]
            )

    if not insp.has_table("daily_trading_reports"):
        op.create_table(
            "daily_trading_reports",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
            sa.Column("report_date", sa.Date(), nullable=False),
            sa.Column("content", postgresql.JSONB(), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("is_immutable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.UniqueConstraint("report_date", name="uq_daily_trading_reports_report_date"),
        )


def downgrade() -> None:
    for table in (
        "daily_trading_reports",
        "host_resource_snapshots",
        "operational_events",
    ):
        op.drop_table(table)
