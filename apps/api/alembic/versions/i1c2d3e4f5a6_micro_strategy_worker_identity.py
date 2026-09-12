"""Seed dedicated Micro paper-strategy worker identity."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "i1c2d3e4f5a6"
down_revision: str | None = "h0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO registered_services (
            id, service_key, display_name, service_kind, criticality,
            heartbeat_interval_seconds, heartbeat_timeout_seconds,
            expected_instance_count, is_enabled, metadata
        ) VALUES (
            '11111111-1111-4111-8111-111111111106',
            'micro_strategy', 'Micro Strategy Worker', 'worker', 'important',
            60, 180, 1, true,
            jsonb_build_object(
                'queue', 'arq:queue:micro_strategy', 'paper_only', true
            )
        )
        ON CONFLICT (service_key) DO NOTHING;
        """
    )
    op.execute(
        """
        INSERT INTO worker_identities (
            id, worker_key, service_id, display_name, description, is_enabled
        ) VALUES (
            '22222222-2222-4222-8222-222222222203',
            'micro_strategy_worker',
            '11111111-1111-4111-8111-111111111106',
            'Micro Strategy Worker',
            'Dedicated ARQ lane for range/pullback Micro paper candidates',
            true
        )
        ON CONFLICT (worker_key) DO NOTHING;
        """
    )
    op.execute(
        """
        INSERT INTO service_health_projections (
            service_id, status, consecutive_failures, evaluation_version, detail
        )
        SELECT id, 'healthy', 0, 0, 'seeded awaiting first Micro worker heartbeat'
        FROM registered_services
        WHERE service_key = 'micro_strategy'
        ON CONFLICT (service_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM service_health_projections
        WHERE service_id = '11111111-1111-4111-8111-111111111106';
        """
    )
    op.execute(
        """
        DELETE FROM worker_instances
        WHERE worker_identity_id = '22222222-2222-4222-8222-222222222203';
        """
    )
    op.execute(
        """
        DELETE FROM worker_identities
        WHERE worker_key = 'micro_strategy_worker';
        """
    )
    op.execute(
        """
        DELETE FROM registered_services
        WHERE service_key = 'micro_strategy';
        """
    )
