"""Record who soft-deleted a photo and when, so deletion can be undone (SA-06).

Revision ID: 20261017_0058
Revises: 20261017_0057

Adds nullable ``project_photos.deleted_at`` and ``project_photos.deleted_by_user_id``.
Photos already in ``pending_delete`` keep NULL in both columns and are purged by
the worker exactly as before; only deletions made after this revision get the
restore window (``PHOTO_DELETE_RETENTION_HOURS``).

Downgrade drops both columns; pending deletions then purge on the next worker run.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261017_0058"
down_revision = "20261017_0057"
branch_labels = None
depends_on = None

_FK = "fk_project_photos_deleted_by_user_id"


def upgrade() -> None:
    with op.batch_alter_table("project_photos") as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("deleted_by_user_id", sa.String(64), nullable=True))
        batch_op.create_foreign_key(_FK, "users", ["deleted_by_user_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("project_photos") as batch_op:
        batch_op.drop_constraint(_FK, type_="foreignkey")
        batch_op.drop_column("deleted_by_user_id")
        batch_op.drop_column("deleted_at")
