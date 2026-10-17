"""Photo ownership and permanent deletion (F0.3).

Revision ID: 20261017_0059
Revises: 20261017_0058

* ``project_photos.uploaded_by_user_id`` (nullable, FK users ON DELETE SET NULL).
  Set by the server from the authenticated uploader. Existing photos stay NULL:
  their author is unknown and is never inferred.
* ``ck_project_photos_status`` gains ``purge_pending``: a permanent deletion has
  been authorised and audited, the photo is no longer served anywhere, and the
  worker keeps retrying storage removal until it can mark the row ``deleted``.

Downgrade drops the column and the new status value. It refuses to run while any
photo is still ``purge_pending``, because that state would otherwise be lost and
its files left in storage.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261017_0059"
down_revision = "20261017_0058"
branch_labels = None
depends_on = None

_FK = "fk_project_photos_uploaded_by_user_id"
_STATUS = "ck_project_photos_status"


def upgrade() -> None:
    with op.batch_alter_table("project_photos") as batch_op:
        batch_op.add_column(sa.Column("uploaded_by_user_id", sa.String(64), nullable=True))
        batch_op.create_foreign_key(_FK, "users", ["uploaded_by_user_id"], ["id"], ondelete="SET NULL")
        batch_op.drop_constraint(_STATUS, type_="check")
        batch_op.create_check_constraint(
            _STATUS,
            "status IN ('active', 'pending_delete', 'purge_pending', 'deleted')",
        )


def downgrade() -> None:
    pending = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM project_photos WHERE status = 'purge_pending'")
    )
    if pending:
        raise RuntimeError(
            f"Cannot downgrade 0059: {pending} photo(s) are purge_pending. "
            "Let the worker finish permanent deletion first."
        )
    with op.batch_alter_table("project_photos") as batch_op:
        batch_op.drop_constraint(_STATUS, type_="check")
        batch_op.create_check_constraint(_STATUS, "status IN ('active', 'pending_delete', 'deleted')")
        batch_op.drop_constraint(_FK, type_="foreignkey")
        batch_op.drop_column("uploaded_by_user_id")
