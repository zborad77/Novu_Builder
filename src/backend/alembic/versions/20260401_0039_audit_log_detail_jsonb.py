"""store audit_logs.detail as structured JSON/JSONB

Revision ID: 20260401_0039
Revises: 20260401_0038
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa


revision = "20260401_0039"
down_revision = "20260401_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            ALTER TABLE audit_logs
            ALTER COLUMN detail TYPE JSONB
            USING CASE
                WHEN detail IS NULL THEN NULL
                ELSE detail::jsonb
            END
            """
        )
        return

    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column(
            "detail",
            existing_type=sa.Text(),
            type_=sa.JSON(),
            existing_nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            ALTER TABLE audit_logs
            ALTER COLUMN detail TYPE TEXT
            USING CASE
                WHEN detail IS NULL THEN NULL
                ELSE detail::text
            END
            """
        )
        return

    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column(
            "detail",
            existing_type=sa.JSON(),
            type_=sa.Text(),
            existing_nullable=True,
        )
