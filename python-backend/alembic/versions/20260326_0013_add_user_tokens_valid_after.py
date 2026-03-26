"""add tokens_valid_after to users

Revision ID: 20260326_0013
Revises: 20260324_0012
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa

revision = "20260326_0013"
down_revision = "20260324_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tokens_valid_after", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "tokens_valid_after")
