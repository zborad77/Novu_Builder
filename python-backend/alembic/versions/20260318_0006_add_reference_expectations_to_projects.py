"""add reference expectations json to projects

Revision ID: 20260318_0006
Revises: 20260318_0005
Create Date: 2026-03-18 00:06:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260318_0006"
down_revision = "20260318_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("projects")}
    if "reference_expectations_json" not in existing_columns:
        op.add_column("projects", sa.Column("reference_expectations_json", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("projects")}
    if "reference_expectations_json" in existing_columns:
        op.drop_column("projects", "reference_expectations_json")
