"""C7: Add password_reset_tokens table for email-based password reset flow.

Revision ID: 20260326_0017
Revises: 20260326_0016
Create Date: 2026-03-26

Single-use tokens created by POST /auth/forgot-password and consumed by
POST /auth/reset-password. Linked to a user via FK with CASCADE delete.
"""
import sqlalchemy as sa
from alembic import op

revision = "20260326_0017"
down_revision = "20260326_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("token", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_password_reset_tokens_user_id", "password_reset_tokens")
    op.drop_table("password_reset_tokens")
