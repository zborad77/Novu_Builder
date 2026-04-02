"""add user_sessions table for per-session revocation

Revision ID: 20260401_0037
Revises: 20260331_0036
Create Date: 2026-04-01 10:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260401_0037"
down_revision = "20260331_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("access_jti", sa.String(length=64), nullable=False, unique=True),
        sa.Column("refresh_jti", sa.String(length=64), nullable=False, unique=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_user_created_at", "user_sessions", ["user_id", "created_at"])
    op.create_index("ix_user_sessions_refresh_expires_at", "user_sessions", ["refresh_expires_at"])
    op.create_index("ix_user_sessions_revoked_at", "user_sessions", ["revoked_at"])


def downgrade() -> None:
    op.drop_index("ix_user_sessions_revoked_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_refresh_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_created_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
