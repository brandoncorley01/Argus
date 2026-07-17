"""config and policy lifecycle versioning

Revision ID: c6a1f0e9d2b8
Revises: 5bb9b33b045b
Create Date: 2026-07-16 23:40:00.000000
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c6a1f0e9d2b8"
down_revision: str | None = "5bb9b33b045b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_POLICY_KINDS = (
    "security",
    "audit",
    "authentication",
    "feature_governance",
)

_MAPPED_POLICY_KINDS = (
    "constitution",
    "operating",
    "governance",
    "treasury",
    "research",
)

_IDENTITY_STRING_COLUMNS = (
    "active_constitution_version",
    "active_operating_policy_version",
    "active_governance_version",
    "active_treasury_policy_version",
    "active_research_framework_version",
)

_IMMUTABILITY_FUNCTION = "enforce_version_immutability"


def upgrade() -> None:
    # Extend policy_kind enum with governance-critical kinds.
    for value in _NEW_POLICY_KINDS:
        op.execute(sa.text(f"ALTER TYPE policy_kind ADD VALUE IF NOT EXISTS '{value}'"))

    version_lifecycle_status = postgresql.ENUM(
        "DRAFT",
        "UNDER_REVIEW",
        "APPROVED",
        "ACTIVE",
        "SUPERSEDED",
        "REJECTED",
        "RETIRED",
        name="version_lifecycle_status",
        create_type=False,
    )
    version_lifecycle_status.create(op.get_bind(), checkfirst=True)

    draft_authority = postgresql.ENUM(
        "FOUNDER_ONLY",
        "FOUNDER_OR_OPERATOR",
        name="draft_authority",
        create_type=False,
    )
    draft_authority.create(op.get_bind(), checkfirst=True)

    # --- configuration_documents ---
    op.add_column(
        "configuration_documents",
        sa.Column(
            "schema_identifier",
            sa.String(length=128),
            server_default=sa.text("'config.generic.v1'"),
            nullable=False,
        ),
    )
    op.add_column(
        "configuration_documents",
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "configuration_documents",
        sa.Column(
            "is_retired",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "configuration_documents",
        sa.Column(
            "draft_authority",
            draft_authority,
            server_default=sa.text("'FOUNDER_ONLY'"),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_configuration_documents_created_by_user_id",
        "configuration_documents",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- policy_documents ---
    op.add_column(
        "policy_documents",
        sa.Column(
            "schema_identifier",
            sa.String(length=128),
            server_default=sa.text("'policy.generic.v1'"),
            nullable=False,
        ),
    )
    op.add_column(
        "policy_documents",
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "policy_documents",
        sa.Column(
            "is_retired",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "policy_documents",
        sa.Column(
            "draft_authority",
            draft_authority,
            server_default=sa.text("'FOUNDER_ONLY'"),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_policy_documents_created_by_user_id",
        "policy_documents",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _upgrade_versions_table("configuration_versions", version_lifecycle_status)
    _upgrade_versions_table("policy_versions", version_lifecycle_status)

    # Institutional identity pointers use `{document_key}@{version_number}` (see
    # ADR-014), which can exceed the original 128-character budget once long
    # document keys are combined with the separator and version number.
    for column in _IDENTITY_STRING_COLUMNS:
        op.alter_column(
            "institutional_identities",
            column,
            type_=sa.String(length=256),
            existing_type=sa.String(length=128),
            existing_nullable=False,
        )

    # At most one non-retired PolicyDocument per governance-mapped kind, since
    # each mapped kind projects to exactly one Institutional Identity pointer
    # field (see ADR-014). Documents outside the mapped-kind set are unrestricted.
    mapped_kinds_sql = ", ".join(f"'{kind}'" for kind in _MAPPED_POLICY_KINDS)
    op.create_index(
        "uq_policy_documents_one_per_mapped_kind",
        "policy_documents",
        ["policy_kind"],
        unique=True,
        postgresql_where=sa.text(f"is_retired = false AND policy_kind IN ({mapped_kinds_sql})"),
    )

    _create_immutability_triggers()


def _create_immutability_triggers() -> None:
    """Database-enforced immutability (see ADR-013).

    Once a version's status has left DRAFT, its content and identifying
    attribution columns can no longer change via any code path -- including
    bugs, ad-hoc SQL, or future application code -- other than the lifecycle
    status/attribution columns that the governance service itself manages
    (status, submitted/approved/activated/superseded/rejected/retired
    timestamps and actor ids, and rejection_reason).
    """
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {_IMMUTABILITY_FUNCTION}() RETURNS trigger AS $$
            BEGIN
                IF OLD.status <> 'DRAFT' THEN
                    IF NEW.content IS DISTINCT FROM OLD.content
                       OR NEW.payload_hash IS DISTINCT FROM OLD.payload_hash
                       OR NEW.document_id IS DISTINCT FROM OLD.document_id
                       OR NEW.version_number IS DISTINCT FROM OLD.version_number
                       OR NEW.previous_version_id IS DISTINCT FROM OLD.previous_version_id
                       OR NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id
                       OR NEW.created_at IS DISTINCT FROM OLD.created_at
                       OR NEW.version_label IS DISTINCT FROM OLD.version_label
                       OR NEW.change_summary IS DISTINCT FROM OLD.change_summary
                    THEN
                        RAISE EXCEPTION
                            'immutable version field cannot change once status has left DRAFT (table=%, id=%)',
                            TG_TABLE_NAME, OLD.id
                            USING ERRCODE = '23514';
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    for table in ("configuration_versions", "policy_versions"):
        op.execute(
            sa.text(f"DROP TRIGGER IF EXISTS trg_{table}_immutability ON {table}")
        )
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_{table}_immutability
                BEFORE UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION {_IMMUTABILITY_FUNCTION}()
                """
            )
        )


def _drop_immutability_triggers() -> None:
    for table in ("configuration_versions", "policy_versions"):
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table}_immutability ON {table}"))
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_IMMUTABILITY_FUNCTION}()"))


def _upgrade_versions_table(table: str, status_enum: postgresql.ENUM) -> None:
    op.drop_index(
        f"uq_{table}_one_active_per_document",
        table_name=table,
        postgresql_where=sa.text("is_active = true"),
    )
    op.drop_constraint(f"uq_{table}_document_version", table, type_="unique")

    op.add_column(table, sa.Column("version_number", sa.Integer(), nullable=True))
    op.add_column(
        table,
        sa.Column(
            "status",
            status_enum,
            server_default=sa.text("'DRAFT'"),
            nullable=False,
        ),
    )
    op.add_column(table, sa.Column("payload_hash", sa.String(length=64), nullable=True))
    op.add_column(table, sa.Column("change_summary", sa.Text(), nullable=True))
    op.add_column(table, sa.Column("previous_version_id", sa.UUID(), nullable=True))
    op.add_column(table, sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table, sa.Column("submitted_by_user_id", sa.UUID(), nullable=True))
    op.add_column(table, sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table, sa.Column("approved_by_user_id", sa.UUID(), nullable=True))
    op.add_column(table, sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table, sa.Column("activated_by_user_id", sa.UUID(), nullable=True))
    op.add_column(table, sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table, sa.Column("superseded_by_user_id", sa.UUID(), nullable=True))
    op.add_column(table, sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table, sa.Column("rejected_by_user_id", sa.UUID(), nullable=True))
    op.add_column(table, sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column(table, sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table, sa.Column("retired_by_user_id", sa.UUID(), nullable=True))

    # Backfill version_number by created_at order within each document.
    op.execute(
        sa.text(
            f"""
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY document_id
                           ORDER BY created_at ASC, id ASC
                       ) AS rn
                FROM {table}
            )
            UPDATE {table} AS v
            SET version_number = ranked.rn
            FROM ranked
            WHERE v.id = ranked.id
            """
        )
    )
    op.execute(sa.text(f"UPDATE {table} SET version_number = 1 WHERE version_number IS NULL"))

    # Backfill payload_hash with the same canonical JSON + SHA-256 algorithm as the app.
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"SELECT id, content FROM {table} WHERE payload_hash IS NULL")).mappings()
    for row in rows:
        payload = row["content"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        digest = _hash_payload(payload)
        conn.execute(
            sa.text(f"UPDATE {table} SET payload_hash = :digest WHERE id = :id"),
            {"digest": digest, "id": row["id"]},
        )

    # Map legacy is_active into lifecycle status. Legacy rows were finalized
    # historical records (the pre-Phase-6 schema only ever tracked a single
    # boolean and never supported a true in-progress DRAFT concept), so
    # is_active=false legacy versions become SUPERSEDED -- never DRAFT -- to
    # avoid implying they are still editable. See ADR-009 addendum.
    op.execute(
        sa.text(
            f"""
            UPDATE {table}
            SET status = CASE
                WHEN is_active = true THEN 'ACTIVE'::version_lifecycle_status
                ELSE 'SUPERSEDED'::version_lifecycle_status
            END
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE {table}
            SET activated_at = created_at
            WHERE is_active = true AND activated_at IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE {table}
            SET superseded_at = created_at
            WHERE is_active = false AND superseded_at IS NULL
            """
        )
    )

    op.alter_column(table, "version_number", nullable=False)
    op.alter_column(table, "payload_hash", nullable=False)

    op.create_foreign_key(
        f"fk_{table}_previous_version_id",
        table,
        table,
        ["previous_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for col in (
        "submitted_by_user_id",
        "approved_by_user_id",
        "activated_by_user_id",
        "superseded_by_user_id",
        "rejected_by_user_id",
        "retired_by_user_id",
    ):
        op.create_foreign_key(
            f"fk_{table}_{col}",
            table,
            "users",
            [col],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_unique_constraint(
        f"uq_{table}_document_number",
        table,
        ["document_id", "version_number"],
    )
    op.create_index(
        f"uq_{table}_one_active_per_document",
        table,
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(f"ix_{table}_status", table, ["status"], unique=False)

    op.drop_column(table, "is_active")


def downgrade() -> None:
    _drop_immutability_triggers()

    # Idempotent: a database may still be stamped at c6a1f0e9d2b8 from the
    # pre-remediation form of this revision (before the mapped-kind index and
    # draft_authority column existed). Downgrade must still reach Phase 5.
    op.execute(sa.text("DROP INDEX IF EXISTS uq_policy_documents_one_per_mapped_kind"))

    # NOTE: narrowing institutional_identities active_* columns is only needed
    # when the widened (256) form was applied. Skip when still at 128.
    conn = op.get_bind()
    for column in _IDENTITY_STRING_COLUMNS:
        length = conn.execute(
            sa.text(
                """
                SELECT character_maximum_length
                FROM information_schema.columns
                WHERE table_name = 'institutional_identities'
                  AND column_name = :column
                """
            ),
            {"column": column},
        ).scalar()
        if length is not None and int(length) > 128:
            op.alter_column(
                "institutional_identities",
                column,
                type_=sa.String(length=128),
                existing_type=sa.String(length=256),
                existing_nullable=False,
            )

    _downgrade_versions_table("policy_versions")
    _downgrade_versions_table("configuration_versions")

    op.drop_constraint(
        "fk_policy_documents_created_by_user_id", "policy_documents", type_="foreignkey"
    )
    op.execute(sa.text("ALTER TABLE policy_documents DROP COLUMN IF EXISTS draft_authority"))
    op.drop_column("policy_documents", "is_retired")
    op.drop_column("policy_documents", "created_by_user_id")
    op.drop_column("policy_documents", "schema_identifier")

    op.drop_constraint(
        "fk_configuration_documents_created_by_user_id",
        "configuration_documents",
        type_="foreignkey",
    )
    op.execute(sa.text("ALTER TABLE configuration_documents DROP COLUMN IF EXISTS draft_authority"))
    op.drop_column("configuration_documents", "is_retired")
    op.drop_column("configuration_documents", "created_by_user_id")
    op.drop_column("configuration_documents", "schema_identifier")

    # draft_authority is introduced entirely within this migration, so (unlike
    # policy_kind below) it can be dropped cleanly once no column references it.
    op.execute(sa.text("DROP TYPE IF EXISTS draft_authority"))
    op.execute(sa.text("DROP TYPE IF EXISTS version_lifecycle_status"))
    # PostgreSQL cannot easily remove enum values; leave extended policy_kind values in place.


def _downgrade_versions_table(table: str) -> None:
    op.add_column(
        table,
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.execute(
        sa.text(
            f"""
            UPDATE {table}
            SET is_active = (status = 'ACTIVE')
            """
        )
    )

    op.drop_index(f"ix_{table}_status", table_name=table)
    op.drop_index(
        f"uq_{table}_one_active_per_document",
        table_name=table,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.drop_constraint(f"uq_{table}_document_number", table, type_="unique")

    for col in (
        "retired_by_user_id",
        "rejected_by_user_id",
        "superseded_by_user_id",
        "activated_by_user_id",
        "approved_by_user_id",
        "submitted_by_user_id",
        "previous_version_id",
    ):
        op.drop_constraint(f"fk_{table}_{col}", table, type_="foreignkey")

    for col in (
        "retired_by_user_id",
        "retired_at",
        "rejection_reason",
        "rejected_by_user_id",
        "rejected_at",
        "superseded_by_user_id",
        "superseded_at",
        "activated_by_user_id",
        "activated_at",
        "approved_by_user_id",
        "approved_at",
        "submitted_by_user_id",
        "submitted_at",
        "previous_version_id",
        "change_summary",
        "payload_hash",
        "status",
        "version_number",
    ):
        op.drop_column(table, col)

    op.create_unique_constraint(
        f"uq_{table}_document_version",
        table,
        ["document_id", "version_label"],
    )
    op.create_index(
        f"uq_{table}_one_active_per_document",
        table,
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def _hash_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        payload = {"_legacy": payload}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()
