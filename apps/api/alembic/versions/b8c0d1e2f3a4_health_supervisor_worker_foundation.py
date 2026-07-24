"""Phase 8 institutional health supervisor and worker foundation

Revision ID: b8c0d1e2f3a4
Revises: a7b8c9d0e1f2
Create Date: 2026-07-19 15:45:00.000000

Notes:
- Adds governed service registry, worker identities/instances, append-only
  heartbeats with ordering/idempotency, current health projections,
  institutional health aggregation, durable supervisor coordination,
  incident lifecycle history, and protective-action recommendations.
- Seeds foundational critical services (postgres, redis, api, health_supervisor).
- Does not initialize SystemState or mutate Founder accounts.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c0d1e2f3a4"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

service_kind = postgresql.ENUM(
    "postgres",
    "redis",
    "api",
    "worker",
    "supervisor",
    "other",
    name="service_kind",
    create_type=False,
)
service_criticality = postgresql.ENUM(
    "critical",
    "important",
    "informational",
    name="service_criticality",
    create_type=False,
)
worker_instance_status = postgresql.ENUM(
    "starting",
    "running",
    "stopping",
    "stopped",
    "stale",
    name="worker_instance_status",
    create_type=False,
)
protective_action_type = postgresql.ENUM(
    "recommend_safe_mode",
    "enter_safe_mode",
    "recommend_observe_only",
    "escalate_incident",
    name="protective_action_type",
    create_type=False,
)
protective_action_status = postgresql.ENUM(
    "pending",
    "applied",
    "dismissed",
    "expired",
    "superseded",
    name="protective_action_status",
    create_type=False,
)
incident_lifecycle_event_type = postgresql.ENUM(
    "opened",
    "investigating",
    "mitigated",
    "closed",
    "note",
    "severity_changed",
    name="incident_lifecycle_event_type",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE service_kind AS ENUM (
                'postgres', 'redis', 'api', 'worker', 'supervisor', 'other'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE service_criticality AS ENUM (
                'critical', 'important', 'informational'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE worker_instance_status AS ENUM (
                'starting', 'running', 'stopping', 'stopped', 'stale'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE protective_action_type AS ENUM (
                'recommend_safe_mode',
                'enter_safe_mode',
                'recommend_observe_only',
                'escalate_incident'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE protective_action_status AS ENUM (
                'pending', 'applied', 'dismissed', 'expired', 'superseded'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE incident_lifecycle_event_type AS ENUM (
                'opened', 'investigating', 'mitigated', 'closed',
                'note', 'severity_changed'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.create_table(
        "registered_services",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("service_key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("service_kind", service_kind, nullable=False),
        sa.Column("criticality", service_criticality, nullable=False),
        sa.Column("heartbeat_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("heartbeat_timeout_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "expected_instance_count",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "heartbeat_interval_seconds > 0",
            name="ck_registered_services_interval_positive",
        ),
        sa.CheckConstraint(
            "heartbeat_timeout_seconds > heartbeat_interval_seconds",
            name="ck_registered_services_timeout_gt_interval",
        ),
        sa.CheckConstraint(
            "expected_instance_count >= 0",
            name="ck_registered_services_expected_instances_nonneg",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_key", name="uq_registered_services_service_key"),
    )

    op.create_table(
        "worker_identities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("worker_key", sa.String(length=64), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["registered_services.id"],
            name="fk_worker_identities_service_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("worker_key", name="uq_worker_identities_worker_key"),
    )
    op.create_index(
        "ix_worker_identities_service_id",
        "worker_identities",
        ["service_id"],
    )

    op.create_table(
        "worker_instances",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("worker_identity_id", sa.UUID(), nullable=False),
        sa.Column("instance_key", sa.String(length=128), nullable=False),
        sa.Column("hostname", sa.String(length=256), nullable=True),
        sa.Column("status", worker_instance_status, nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["worker_identity_id"],
            ["worker_identities.id"],
            name="fk_worker_instances_worker_identity_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "worker_identity_id",
            "instance_key",
            name="uq_worker_instances_identity_instance",
        ),
    )
    op.create_index(
        "ix_worker_instances_last_seen_at",
        "worker_instances",
        ["last_seen_at"],
    )
    op.create_index(
        "ix_worker_instances_status",
        "worker_instances",
        ["status"],
    )

    op.create_table(
        "health_heartbeats",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("worker_instance_id", sa.UUID(), nullable=True),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("status", postgresql.ENUM(name="health_status", create_type=False), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["registered_services.id"],
            name="fk_health_heartbeats_service_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["worker_instance_id"],
            ["worker_instances.id"],
            name="fk_health_heartbeats_worker_instance_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "service_id",
            "sequence_number",
            name="uq_health_heartbeats_service_sequence",
        ),
    )
    op.create_index(
        "ix_health_heartbeats_service_received",
        "health_heartbeats",
        ["service_id", "received_at"],
    )
    op.create_index(
        "ix_health_heartbeats_observed_at",
        "health_heartbeats",
        ["observed_at"],
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_health_heartbeat_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'health_heartbeats is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_health_heartbeats_immutability
        BEFORE UPDATE OR DELETE ON health_heartbeats
        FOR EACH ROW
        EXECUTE FUNCTION prevent_health_heartbeat_mutation();
        """
    )

    op.create_table(
        "health_heartbeat_idempotency",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("heartbeat_id", sa.UUID(), nullable=True),
        sa.Column(
            "response_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["registered_services.id"],
            name="fk_health_heartbeat_idempotency_service_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["heartbeat_id"],
            ["health_heartbeats.id"],
            name="fk_health_heartbeat_idempotency_heartbeat_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "service_id",
            "idempotency_key_hash",
            name="uq_health_heartbeat_idempotency_service_key",
        ),
    )

    op.create_table(
        "service_health_projections",
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("status", postgresql.ENUM(name="health_status", create_type=False), nullable=False),
        sa.Column("last_heartbeat_id", sa.UUID(), nullable=True),
        sa.Column("last_sequence_number", sa.BigInteger(), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "evaluation_version",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "consecutive_failures >= 0",
            name="ck_service_health_projections_failures_nonneg",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["registered_services.id"],
            name="fk_service_health_projections_service_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_heartbeat_id"],
            ["health_heartbeats.id"],
            name="fk_service_health_projections_last_heartbeat_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("service_id"),
    )

    op.create_table(
        "institutional_health_state",
        sa.Column("singleton_key", sa.String(length=32), nullable=False),
        sa.Column("status", postgresql.ENUM(name="health_status", create_type=False), nullable=False),
        sa.Column(
            "evaluation_version",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "singleton_key = 'current'",
            name="ck_institutional_health_state_singleton",
        ),
        sa.PrimaryKeyConstraint("singleton_key"),
    )

    op.create_table(
        "health_supervisor_leases",
        sa.Column("singleton_key", sa.String(length=32), nullable=False),
        sa.Column("holder_instance_id", sa.UUID(), nullable=True),
        sa.Column("lease_epoch", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cycle_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cycle_result", sa.String(length=64), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "singleton_key = 'current'",
            name="ck_health_supervisor_leases_singleton",
        ),
        sa.ForeignKeyConstraint(
            ["holder_instance_id"],
            ["worker_instances.id"],
            name="fk_health_supervisor_leases_holder_instance_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("singleton_key"),
    )

    op.add_column(
        "incidents",
        sa.Column("source_service_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "incidents",
        sa.Column("correlation_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "incidents",
        sa.Column(
            "opened_by_system",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_incidents_source_service_id",
        "incidents",
        "registered_services",
        ["source_service_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_incidents_correlation_key", "incidents", ["correlation_key"])
    op.create_index(
        "ix_incidents_open_correlation",
        "incidents",
        ["correlation_key"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ("
            "'open'::incident_status, "
            "'investigating'::incident_status, "
            "'mitigated'::incident_status)"
        ),
    )

    op.create_table(
        "incident_lifecycle_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("incident_id", sa.UUID(), nullable=False),
        sa.Column("event_type", incident_lifecycle_event_type, nullable=False),
        sa.Column(
            "from_status",
            postgresql.ENUM(name="incident_status", create_type=False),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            postgresql.ENUM(name="incident_status", create_type=False),
            nullable=True,
        ),
        sa.Column(
            "from_severity",
            postgresql.ENUM(name="incident_severity", create_type=False),
            nullable=True,
        ),
        sa.Column(
            "to_severity",
            postgresql.ENUM(name="incident_severity", create_type=False),
            nullable=True,
        ),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "opened_by_system",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name="fk_incident_lifecycle_events_incident_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_incident_lifecycle_events_actor_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_incident_lifecycle_events_incident_occurred",
        "incident_lifecycle_events",
        ["incident_id", "occurred_at"],
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_incident_lifecycle_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'incident_lifecycle_events is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_incident_lifecycle_events_immutability
        BEFORE UPDATE OR DELETE ON incident_lifecycle_events
        FOR EACH ROW
        EXECUTE FUNCTION prevent_incident_lifecycle_mutation();
        """
    )

    op.create_table(
        "protective_action_recommendations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("action_type", protective_action_type, nullable=False),
        sa.Column("status", protective_action_status, nullable=False),
        sa.Column("incident_id", sa.UUID(), nullable=True),
        sa.Column("source_service_id", sa.UUID(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name="fk_protective_action_recommendations_incident_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_service_id"],
            ["registered_services.id"],
            name="fk_protective_action_recommendations_source_service_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key_hash",
            name="uq_protective_action_recommendations_idempotency",
        ),
    )
    op.create_index(
        "ix_protective_action_recommendations_status",
        "protective_action_recommendations",
        ["status"],
    )

    # Seed foundational registry + supervisor worker identity + singleton rows.
    op.execute(
        """
        INSERT INTO registered_services (
            id, service_key, display_name, service_kind, criticality,
            heartbeat_interval_seconds, heartbeat_timeout_seconds,
            expected_instance_count, is_enabled, metadata
        ) VALUES
        (
            '11111111-1111-4111-8111-111111111101',
            'postgres', 'PostgreSQL', 'postgres', 'critical',
            30, 90, 1, true, '{"probe":"select_1"}'::jsonb
        ),
        (
            '11111111-1111-4111-8111-111111111102',
            'redis', 'Redis', 'redis', 'critical',
            30, 90, 1, true, '{"probe":"ping"}'::jsonb
        ),
        (
            '11111111-1111-4111-8111-111111111103',
            'api', 'Argus API', 'api', 'critical',
            30, 120, 1, true, '{"probe":"process_presence"}'::jsonb
        ),
        (
            '11111111-1111-4111-8111-111111111104',
            'health_supervisor', 'Health Supervisor Worker', 'supervisor', 'critical',
            30, 120, 1, true, '{"probe":"self_heartbeat"}'::jsonb
        );
        """
    )
    op.execute(
        """
        INSERT INTO worker_identities (
            id, worker_key, service_id, display_name, description, is_enabled
        ) VALUES (
            '22222222-2222-4222-8222-222222222201',
            'health_supervisor_worker',
            '11111111-1111-4111-8111-111111111104',
            'Health Supervisor Worker',
            'ARQ-backed institutional health supervisor',
            true
        );
        """
    )
    op.execute(
        """
        INSERT INTO service_health_projections (
            service_id, status, consecutive_failures, evaluation_version, detail
        )
        SELECT id, 'healthy', 0, 0, 'seeded awaiting first heartbeat'
        FROM registered_services;
        """
    )
    op.execute(
        """
        INSERT INTO institutional_health_state (
            singleton_key, status, evaluation_version, summary, evaluated_at
        ) VALUES (
            'current',
            'healthy',
            0,
            '{"note":"seeded awaiting supervisor evaluation"}'::jsonb,
            now()
        );
        """
    )
    op.execute(
        """
        INSERT INTO health_supervisor_leases (
            singleton_key, lease_epoch, metadata
        ) VALUES (
            'current',
            0,
            '{}'::jsonb
        );
        """
    )


def downgrade() -> None:
    op.drop_table("protective_action_recommendations")
    op.execute("DROP TRIGGER IF EXISTS trg_incident_lifecycle_events_immutability ON incident_lifecycle_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_incident_lifecycle_mutation()")
    op.drop_table("incident_lifecycle_events")
    op.drop_index("ix_incidents_open_correlation", table_name="incidents")
    op.drop_index("ix_incidents_correlation_key", table_name="incidents")
    op.drop_constraint("fk_incidents_source_service_id", "incidents", type_="foreignkey")
    op.drop_column("incidents", "opened_by_system")
    op.drop_column("incidents", "correlation_key")
    op.drop_column("incidents", "source_service_id")
    op.drop_table("health_supervisor_leases")
    op.drop_table("institutional_health_state")
    op.drop_table("service_health_projections")
    op.drop_table("health_heartbeat_idempotency")
    op.execute("DROP TRIGGER IF EXISTS trg_health_heartbeats_immutability ON health_heartbeats")
    op.execute("DROP FUNCTION IF EXISTS prevent_health_heartbeat_mutation()")
    op.drop_table("health_heartbeats")
    op.drop_table("worker_instances")
    op.drop_table("worker_identities")
    op.drop_table("registered_services")

    op.execute("DROP TYPE IF EXISTS incident_lifecycle_event_type")
    op.execute("DROP TYPE IF EXISTS protective_action_status")
    op.execute("DROP TYPE IF EXISTS protective_action_type")
    op.execute("DROP TYPE IF EXISTS worker_instance_status")
    op.execute("DROP TYPE IF EXISTS service_criticality")
    op.execute("DROP TYPE IF EXISTS service_kind")
