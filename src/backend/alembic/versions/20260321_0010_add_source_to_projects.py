"""add source to projects

Revision ID: 20260321_0010
Revises: 20260321_0009
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

revision = "20260321_0010"
down_revision = "20260321_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("source", sa.String(32), nullable=False, server_default="mobile"),
    )


def downgrade() -> None:
    op.drop_column("projects", "source")
