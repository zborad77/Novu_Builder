"""add analysis reference flag to project photos

Revision ID: 20260318_0005
Revises: 20260318_0004
Create Date: 2026-03-18 00:05:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260318_0005"
down_revision = "20260318_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("project_photos")}
    if "is_analysis_reference" not in existing_columns:
        op.add_column(
            "project_photos",
            sa.Column("is_analysis_reference", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("project_photos")}
    if "is_analysis_reference" in existing_columns:
        op.drop_column("project_photos", "is_analysis_reference")
