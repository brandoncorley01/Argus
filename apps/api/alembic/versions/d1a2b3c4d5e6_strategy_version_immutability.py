"""Phase 11 remediation: DB immutability for strategy_versions content."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1a2b3c4d5e6"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FN = "prevent_strategy_version_mutation_when_immutable"


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {_FN}() RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    IF OLD.is_immutable IS TRUE THEN
                        RAISE EXCEPTION
                            'strategy_versions is immutable when is_immutable=true (id=%)',
                            OLD.id
                            USING ERRCODE = '23514';
                    END IF;
                    RETURN OLD;
                END IF;

                IF OLD.is_immutable IS TRUE THEN
                    IF NEW.parameters IS DISTINCT FROM OLD.parameters
                       OR NEW.parameter_schema IS DISTINCT FROM OLD.parameter_schema
                       OR NEW.strategy_class IS DISTINCT FROM OLD.strategy_class
                       OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
                       OR NEW.version_label IS DISTINCT FROM OLD.version_label
                       OR NEW.document_id IS DISTINCT FROM OLD.document_id
                       OR NEW.version_number IS DISTINCT FROM OLD.version_number
                    THEN
                        RAISE EXCEPTION
                            'immutable strategy_versions content cannot change '
                            'when is_immutable=true (id=%)',
                            OLD.id
                            USING ERRCODE = '23514';
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_strategy_versions_immutability "
            "ON strategy_versions"
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER trg_strategy_versions_immutability
            BEFORE UPDATE OR DELETE ON strategy_versions
            FOR EACH ROW EXECUTE FUNCTION {_FN}()
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_strategy_versions_immutability "
            "ON strategy_versions"
        )
    )
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FN}()"))
