"""Add project exports table with TTL metadata.

Revision ID: 20260330_0024
Revises: 20260329_0023
Create Date: 2026-03-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260330_0024"
down_revision = "20260329_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_exports",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("export_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_project_exports_project_id", "project_exports", ["project_id"], unique=False)
    op.create_index("idx_project_exports_expires_at", "project_exports", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_project_exports_expires_at", table_name="project_exports")
    op.drop_index("idx_project_exports_project_id", table_name="project_exports")
    op.drop_table("project_exports")
