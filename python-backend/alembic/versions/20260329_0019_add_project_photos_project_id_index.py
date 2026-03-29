"""add index on project_photos.project_id

Revision ID: 20260329_0019
Revises: 20260326_0018
Create Date: 2026-03-29
"""
from alembic import op


revision = "20260329_0019"
down_revision = "20260326_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("idx_project_photos_project_id", "project_photos", ["project_id"])


def downgrade() -> None:
    op.drop_index("idx_project_photos_project_id", table_name="project_photos")
