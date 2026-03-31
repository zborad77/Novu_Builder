"""add runtime workflow states

Revision ID: 20260331_0035
Revises: 20260331_0034
Create Date: 2026-03-31 20:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260331_0035"
down_revision = "20260331_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("project_work_items") as batch_op:
        batch_op.add_column(sa.Column("confirmation_status", sa.String(length=32), nullable=False, server_default="pending"))
        batch_op.add_column(sa.Column("confirmed_by_user_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_project_work_items_confirmed_by_user",
            "users",
            ["confirmed_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "idx_project_work_items_project_confirmation",
            ["project_id", "confirmation_status", "updated_at", "id"],
            unique=False,
        )
        batch_op.create_check_constraint(
            "ck_project_work_items_confirmation_status",
            "confirmation_status IN ('pending', 'mixed', 'confirmed')",
        )
        batch_op.drop_constraint("ck_project_work_items_source_type", type_="check")
        batch_op.create_check_constraint(
            "ck_project_work_items_source_type",
            "source_type IN ('manual', 'vision', 'import', 'imported', 'system', 'default')",
        )

    with op.batch_alter_table("project_work_item_values") as batch_op:
        batch_op.add_column(sa.Column("source_detection_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("source_confidence", sa.Numeric(8, 4), nullable=True))
        batch_op.add_column(sa.Column("confirmation_status", sa.String(length=32), nullable=False, server_default="pending"))
        batch_op.add_column(sa.Column("confirmed_by_user_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("operator_note", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_project_work_item_values_source_detection",
            "vision_detections",
            ["source_detection_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_project_work_item_values_confirmed_by_user",
            "users",
            ["confirmed_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "idx_project_work_item_values_item_confirmation",
            ["project_work_item_id", "confirmation_status", "resolved_parameter_code"],
            unique=False,
        )
        batch_op.create_check_constraint(
            "ck_project_work_item_values_confirmation_status",
            "confirmation_status IN ('pending', 'confirmed', 'corrected', 'defaulted')",
        )
        batch_op.drop_constraint("ck_project_work_item_values_source_type", type_="check")
        batch_op.create_check_constraint(
            "ck_project_work_item_values_source_type",
            "source_type IN ('manual', 'vision', 'import', 'imported', 'system', 'default')",
        )


def downgrade() -> None:
    with op.batch_alter_table("project_work_item_values") as batch_op:
        batch_op.drop_constraint("ck_project_work_item_values_source_type", type_="check")
        batch_op.create_check_constraint(
            "ck_project_work_item_values_source_type",
            "source_type IN ('manual', 'vision', 'import', 'system')",
        )
        batch_op.drop_constraint("ck_project_work_item_values_confirmation_status", type_="check")
        batch_op.drop_index("idx_project_work_item_values_item_confirmation")
        batch_op.drop_constraint("fk_project_work_item_values_confirmed_by_user", type_="foreignkey")
        batch_op.drop_constraint("fk_project_work_item_values_source_detection", type_="foreignkey")
        batch_op.drop_column("operator_note")
        batch_op.drop_column("confirmed_at")
        batch_op.drop_column("confirmed_by_user_id")
        batch_op.drop_column("confirmation_status")
        batch_op.drop_column("source_confidence")
        batch_op.drop_column("source_detection_id")

    with op.batch_alter_table("project_work_items") as batch_op:
        batch_op.drop_constraint("ck_project_work_items_source_type", type_="check")
        batch_op.create_check_constraint(
            "ck_project_work_items_source_type",
            "source_type IN ('manual', 'vision', 'import', 'system')",
        )
        batch_op.drop_constraint("ck_project_work_items_confirmation_status", type_="check")
        batch_op.drop_index("idx_project_work_items_project_confirmation")
        batch_op.drop_constraint("fk_project_work_items_confirmed_by_user", type_="foreignkey")
        batch_op.drop_column("confirmed_at")
        batch_op.drop_column("confirmed_by_user_id")
        batch_op.drop_column("confirmation_status")
