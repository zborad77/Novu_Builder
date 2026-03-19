"""add project final proposals

Revision ID: 20260318_0004
Revises: 20260318_0003
Create Date: 2026-03-18 22:35:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260318_0004"
down_revision = "20260318_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("project_final_proposals"):
        return

    op.create_table(
        "project_final_proposals",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("draft_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="ready_for_export"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CZK"),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("total_price", sa.Float(), nullable=True),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("project_final_proposals"):
        op.drop_table("project_final_proposals")
