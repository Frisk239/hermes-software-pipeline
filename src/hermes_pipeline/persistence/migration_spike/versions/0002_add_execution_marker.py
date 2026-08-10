"""add migration execution marker

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-10
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create a second real migration target for AC-12 fault evidence."""
    _record_execution()
    op.create_table(
        "migration_spike_marker",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("marker", sa.String(32), nullable=False),
    )


def downgrade() -> None:
    """Drop the second temporary spike migration table."""
    _record_execution()
    op.drop_table("migration_spike_marker")


def _record_execution() -> None:
    """Append this fixed revision ID to the helper-owned test trace."""
    config = op.get_context().config
    if config is None:
        return
    trace: object = config.attributes.get("spike_executed_revisions")
    if isinstance(trace, list):
        cast(list[object], trace).append(revision)
