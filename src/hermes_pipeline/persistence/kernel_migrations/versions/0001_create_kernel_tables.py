"""create kernel inbox, events, and pipeline snapshot tables

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_PHASE_01

Revision ID: 0001
Revises:
Create Date: 2026-08-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbox",
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("command_id", sa.Text(), nullable=False),
        sa.Column("command_fingerprint", sa.Text(), nullable=False),
        sa.Column("receipt_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("workspace_id", "command_id"),
    )
    op.create_table(
        "events",
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("pipeline_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "pipelines",
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("pipeline_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("workspace_id", "pipeline_id"),
    )


def downgrade() -> None:
    op.drop_table("pipelines")
    op.drop_table("events")
    op.drop_table("inbox")
