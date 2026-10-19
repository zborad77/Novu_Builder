"""add work catalog hot path indexes

Revision ID: 20260331_0036
Revises: 20260331_0035
Create Date: 2026-03-31 22:15:00.000000
"""

from alembic import op


revision = "20260331_0036"
down_revision = "20260331_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_types") as batch_op:
        batch_op.create_index(
            "idx_work_types_catalog_sort",
            ["sort_order", "code"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("work_types") as batch_op:
        batch_op.drop_index("idx_work_types_catalog_sort")
