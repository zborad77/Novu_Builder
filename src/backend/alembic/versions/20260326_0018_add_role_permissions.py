"""C8: Add role_permissions table for DB-backed RBAC.

Revision ID: 20260326_0018
Revises: 20260326_0017
Create Date: 2026-03-26

Seeded with default permissions:
  superadmin → admin:read, admin:write, admin:jobs, admin:impersonate
  manager    → admin:read, admin:write

Superadmin always has all capabilities regardless of this table
(enforced at the application layer in deps.py).
"""
import sqlalchemy as sa
from alembic import op
from datetime import datetime, UTC

revision = "20260326_0018"
down_revision = "20260326_0017"
branch_labels = None
depends_on = None

_DEFAULT_PERMISSIONS = [
    # superadmin — all capabilities
    ("superadmin", "admin:read"),
    ("superadmin", "admin:write"),
    ("superadmin", "admin:jobs"),
    ("superadmin", "admin:impersonate"),
    # manager — read + write (no job management or impersonation)
    ("manager", "admin:read"),
    ("manager", "admin:write"),
]


def upgrade() -> None:
    op.create_table(
        "role_permissions",
        sa.Column("role", sa.String(64), primary_key=True),
        sa.Column("capability", sa.String(128), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Seed default permissions
    now = datetime.now(UTC)
    op.bulk_insert(
        sa.table(
            "role_permissions",
            sa.column("role", sa.String),
            sa.column("capability", sa.String),
            sa.column("created_at", sa.DateTime),
        ),
        [{"role": role, "capability": cap, "created_at": now} for role, cap in _DEFAULT_PERMISSIONS],
    )


def downgrade() -> None:
    op.drop_table("role_permissions")
