"""add proposal draft version

Revision ID: 20260318_0003
Revises: 20260318_0002
Create Date: 2026-03-18 22:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260318_0003"
down_revision = "20260318_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("project_proposal_drafts"):
        return

    columns = {column["name"] for column in inspector.get_columns("project_proposal_drafts")}
    if "version" not in columns:
        op.add_column(
            "project_proposal_drafts",
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("project_proposal_drafts"):
        return

    columns = {column["name"] for column in inspector.get_columns("project_proposal_drafts")}
    if "version" in columns:
        op.drop_column("project_proposal_drafts", "version")
