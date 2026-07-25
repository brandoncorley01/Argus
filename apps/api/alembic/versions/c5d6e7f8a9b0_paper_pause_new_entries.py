"""Add paper portfolio pause_new_entries_active flag.

Allows Founders to pause new paper entries while Argus continues
monitoring and may still submit risk-reducing exit sells.
Does not enable live trading.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: str | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("paper_portfolios"):
        cols = {c["name"] for c in insp.get_columns("paper_portfolios")}
        if "pause_new_entries_active" not in cols:
            op.add_column(
                "paper_portfolios",
                sa.Column(
                    "pause_new_entries_active",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("paper_portfolios"):
        cols = {c["name"] for c in insp.get_columns("paper_portfolios")}
        if "pause_new_entries_active" in cols:
            op.drop_column("paper_portfolios", "pause_new_entries_active")
