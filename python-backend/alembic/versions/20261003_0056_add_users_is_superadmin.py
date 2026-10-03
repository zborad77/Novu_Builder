"""Version the previously model-only users.is_superadmin flag.

Revision ID: 20261003_0056
Revises: 20260527_0055

Older installations may already have the ordinary BOOLEAN NOT NULL column
because the former initial revision used live application metadata. Preserve
those values; accept only an absent or literal false server default and fail
closed on incompatible definitions rather than coercing them.

Downgrade drops the flag, including any existing superadmin assignments. Back up
those assignments before downgrading: a subsequent upgrade initializes all users
to false and cannot recover lost privileges. It never infers administrator roles.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.interfaces import ReflectedColumn


revision = "20261003_0056"
down_revision = "20260527_0055"
branch_labels = None
depends_on = None


def _column() -> ReflectedColumn | None:
    columns = sa.inspect(op.get_bind()).get_columns("users")
    return next((column for column in columns if column["name"] == "is_superadmin"), None)


def _require_compatible(column: ReflectedColumn) -> None:
    if (
        not isinstance(column["type"], sa.Boolean)
        or column["nullable"]
        or column.get("computed") is not None
        or column.get("identity") is not None
        # PostgreSQL reflects false Boolean literals/casts as "false". Do not
        # evaluate expressions: they must fail closed even if they return false.
        or column.get("default") not in (None, "false")
    ):
        raise RuntimeError(
            "Incompatible users.is_superadmin: expected an ordinary BOOLEAN NOT NULL column "
            "with no server default or a literal false default; "
            "refusing to coerce values or infer administrator privileges."
        )


def upgrade() -> None:
    column = _column()
    if column is not None:
        _require_compatible(column)
        return

    # The temporary default backfills every existing row without promoting anyone.
    op.add_column(
        "users",
        sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Match the application's client-side default; do not leave a new DB policy.
    op.alter_column("users", "is_superadmin", server_default=None)


def downgrade() -> None:
    column = _column()
    if column is None:
        raise RuntimeError("Cannot downgrade 0056: users.is_superadmin is missing.")
    _require_compatible(column)
    op.drop_column("users", "is_superadmin")
