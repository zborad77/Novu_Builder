"""Harden password reset token persistence and indexes.

Revision ID: 20260329_0022
Revises: 20260329_0021
Create Date: 2026-03-29

Security hardening:
- backfill stored reset tokens from raw values to SHA-256 digests
- ensure at most one unused reset token row per user
- add expiry index for predictable cleanup
"""

from __future__ import annotations

import hashlib
import string
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "20260329_0022"
down_revision = "20260329_0021"
branch_labels = None
depends_on = None


password_reset_tokens = sa.table(
    "password_reset_tokens",
    sa.column("token", sa.String(length=128)),
    sa.column("user_id", sa.String(length=64)),
    sa.column("used_at", sa.DateTime(timezone=True)),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def _looks_like_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(ch in string.hexdigits for ch in value)


def _token_digest(value: str) -> str:
    if _looks_like_sha256_hex(value):
        return value.lower()
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def upgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    rows = connection.execute(
        sa.select(
            password_reset_tokens.c.token,
            password_reset_tokens.c.user_id,
            password_reset_tokens.c.used_at,
            password_reset_tokens.c.created_at,
        )
    ).mappings().all()

    newest_unused_token_by_user: dict[str, str] = {}
    newest_created_at_by_user: dict[str, datetime] = {}

    for row in rows:
        if row["used_at"] is not None:
            continue
        created_at = row["created_at"] or now
        current_best = newest_created_at_by_user.get(row["user_id"])
        if current_best is None or created_at > current_best:
            newest_created_at_by_user[row["user_id"]] = created_at
            newest_unused_token_by_user[row["user_id"]] = row["token"]

    for row in rows:
        values: dict[str, object] = {}
        token_digest = _token_digest(row["token"])
        if token_digest != row["token"]:
            values["token"] = token_digest

        if row["used_at"] is None and newest_unused_token_by_user.get(row["user_id"]) != row["token"]:
            values["used_at"] = now

        if values:
            connection.execute(
                password_reset_tokens.update()
                .where(password_reset_tokens.c.token == row["token"])
                .values(**values)
            )

    op.create_index(
        "ix_password_reset_tokens_expires_at",
        "password_reset_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "uq_password_reset_tokens_user_id_unused",
        "password_reset_tokens",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("used_at IS NULL"),
        sqlite_where=sa.text("used_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_password_reset_tokens_user_id_unused", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_expires_at", table_name="password_reset_tokens")
    # Token hashing backfill is intentionally not reversed: raw reset tokens must
    # not be restored to the database once they have been hardened to digests.
