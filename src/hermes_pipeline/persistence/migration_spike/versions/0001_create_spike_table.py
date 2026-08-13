"""create spike migration table

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE

Revision ID: 0001
Revises:
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the single spike migration table."""
    _record_execution()
    op.create_table(
        "migration_spike_item",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
    )


def downgrade() -> None:
    """Drop the spike migration table (rollback to the prior revision)."""
    _record_execution()
    op.drop_table("migration_spike_item")


def _record_execution() -> None:
    """Append this fixed revision ID to the helper-owned test trace."""
    config = op.get_context().config
    if config is None:
        return
    trace: object = config.attributes.get("spike_executed_revisions")
    if isinstance(trace, list):
        cast(list[object], trace).append(revision)
