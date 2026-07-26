"""Seed market ops worker identity for scan + price refresh ARQ process."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "g9a0b1c2d3e4"
down_revision: str | None = "f8a9b0c1d2e3"
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
            '11111111-1111-4111-8111-111111111105',
            'market_ops', 'Market Ops Worker', 'worker', 'important',
            60, 180, 1, true, '{"probe":"scan_cycle","role":"paper_scan_prices"}'::jsonb
        )
        ON CONFLICT (service_key) DO NOTHING;
        """
    )
    op.execute(
        """
        INSERT INTO worker_identities (
            id, worker_key, service_id, display_name, description, is_enabled
        ) VALUES (
            '22222222-2222-4222-8222-222222222202',
            'market_ops_worker',
            '11111111-1111-4111-8111-111111111105',
            'Market Ops Worker',
            'ARQ-backed market scan and short-TF price refresh (paper only)',
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
        SELECT id, 'healthy', 0, 0, 'seeded awaiting first market-ops heartbeat'
        FROM registered_services
        WHERE service_key = 'market_ops'
        ON CONFLICT (service_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM service_health_projections
        WHERE service_id = '11111111-1111-4111-8111-111111111105';
        """
    )
    op.execute(
        """
        DELETE FROM worker_identities
        WHERE worker_key = 'market_ops_worker';
        """
    )
    op.execute(
        """
        DELETE FROM registered_services
        WHERE service_key = 'market_ops';
        """
    )
