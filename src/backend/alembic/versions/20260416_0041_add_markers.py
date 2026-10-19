"""Add markers table for user and AI annotations on project photos.

Revision ID: 20260416_0041
Revises: 20260401_0040
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260416_0041"
down_revision = "20260401_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "markers",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("image_id", sa.String(length=64), nullable=True),
        sa.Column("marker_type", sa.String(length=32), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("width", sa.Float(), nullable=True),
        sa.Column("height", sa.Float(), nullable=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "marker_type IN ('defect', 'note', 'ai_detection', 'measurement')",
            name="ck_markers_marker_type",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["image_id"], ["project_photos.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_markers_case_id", "markers", ["case_id"], unique=False)
    op.create_index("idx_markers_image_id", "markers", ["image_id"], unique=False)
    op.create_index("idx_markers_case_type", "markers", ["case_id", "marker_type"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_markers_case_type", table_name="markers")
    op.drop_index("idx_markers_image_id", table_name="markers")
    op.drop_index("idx_markers_case_id", table_name="markers")
    op.drop_table("markers")
