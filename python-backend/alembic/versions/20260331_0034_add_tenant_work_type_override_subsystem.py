"""add tenant work type override subsystem

Revision ID: 20260331_0034
Revises: 20260331_0033
Create Date: 2026-03-31 17:25:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260331_0034"
down_revision = "20260331_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_work_type_extra_parameters",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_work_type_setting_id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("work_type_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("data_type", sa.String(length=32), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("section", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("min_number_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("max_number_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("vision_extractable", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("manual_override_allowed", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("default_text_value", sa.Text(), nullable=True),
        sa.Column("default_number_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("default_boolean_value", sa.Boolean(), nullable=True),
        sa.Column("default_option_code", sa.String(length=64), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by_user_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_work_type_setting_id"], ["tenant_work_type_settings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_type_id"], ["work_types.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_work_type_setting_id", "code", name="uq_tenant_extra_parameters_setting_code"),
        sa.UniqueConstraint("tenant_work_type_setting_id", "slug", name="uq_tenant_extra_parameters_setting_slug"),
        sa.UniqueConstraint("organization_id", "work_type_id", "code", name="uq_tenant_extra_parameters_org_work_type_code"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_tenant_extra_parameters_status"),
        sa.CheckConstraint("data_type IN ('number', 'text', 'boolean', 'option')", name="ck_tenant_extra_parameters_data_type"),
        sa.CheckConstraint(
            "section IN ('dimensions', 'materials', 'condition_or_damage', 'access_and_complexity', 'quantity_scope', 'optional_notes')",
            name="ck_tenant_extra_parameters_section",
        ),
        sa.CheckConstraint(
            "min_number_value IS NULL OR max_number_value IS NULL OR min_number_value <= max_number_value",
            name="ck_tenant_extra_parameters_number_bounds_order",
        ),
        sa.CheckConstraint(
            "(CASE WHEN default_text_value IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN default_number_value IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN default_boolean_value IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN default_option_code IS NOT NULL THEN 1 ELSE 0 END) <= 1",
            name="ck_tenant_extra_parameters_single_default_value",
        ),
        sa.CheckConstraint("data_type = 'text' OR default_text_value IS NULL", name="ck_tenant_extra_parameters_default_text_type"),
        sa.CheckConstraint(
            "data_type = 'number' OR (default_number_value IS NULL AND min_number_value IS NULL AND max_number_value IS NULL)",
            name="ck_tenant_extra_parameters_default_number_type",
        ),
        sa.CheckConstraint("data_type = 'boolean' OR default_boolean_value IS NULL", name="ck_tenant_extra_parameters_default_boolean_type"),
        sa.CheckConstraint("data_type = 'option' OR default_option_code IS NULL", name="ck_tenant_extra_parameters_default_option_type"),
    )
    op.create_index(
        "idx_tenant_extra_parameters_org_work_type_status",
        "tenant_work_type_extra_parameters",
        ["organization_id", "work_type_id", "status", "sort_order"],
        unique=False,
    )
    op.create_index(
        "idx_tenant_extra_parameters_setting_section_sort",
        "tenant_work_type_extra_parameters",
        ["tenant_work_type_setting_id", "section", "sort_order"],
        unique=False,
    )

    op.create_table(
        "tenant_work_type_extra_parameter_options",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_work_type_extra_parameter_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["tenant_work_type_extra_parameter_id"],
            ["tenant_work_type_extra_parameters.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_work_type_extra_parameter_id",
            "code",
            name="uq_tenant_extra_parameter_options_parameter_code",
        ),
    )
    op.create_index(
        "idx_tenant_extra_parameter_options_parameter_sort",
        "tenant_work_type_extra_parameter_options",
        ["tenant_work_type_extra_parameter_id", "sort_order", "code"],
        unique=False,
    )

    with op.batch_alter_table("project_work_item_values") as batch_op:
        batch_op.alter_column("work_type_parameter_id", existing_type=sa.String(length=64), nullable=True)
        batch_op.add_column(sa.Column("tenant_work_type_extra_parameter_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("resolved_parameter_scope", sa.String(length=32), nullable=False, server_default="global"))
        batch_op.create_foreign_key(
            "fk_project_work_item_values_tenant_extra_parameter",
            "tenant_work_type_extra_parameters",
            ["tenant_work_type_extra_parameter_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_unique_constraint(
            "uq_project_work_item_values_item_extra_parameter",
            ["project_work_item_id", "tenant_work_type_extra_parameter_id"],
        )
        batch_op.create_index(
            "idx_project_work_item_values_extra_parameter_lookup",
            ["tenant_work_type_extra_parameter_id", "resolved_parameter_code"],
            unique=False,
        )
        batch_op.create_check_constraint(
            "ck_project_work_item_values_parameter_scope",
            "resolved_parameter_scope IN ('global', 'tenant_extra')",
        )
        batch_op.create_check_constraint(
            "ck_project_work_item_values_definition_binding",
            "("
            "(resolved_parameter_scope = 'global' AND work_type_parameter_id IS NOT NULL AND tenant_work_type_extra_parameter_id IS NULL) OR "
            "(resolved_parameter_scope = 'tenant_extra' AND tenant_work_type_extra_parameter_id IS NOT NULL AND work_type_parameter_id IS NULL)"
            ")",
        )


def downgrade() -> None:
    with op.batch_alter_table("project_work_item_values") as batch_op:
        batch_op.drop_constraint("ck_project_work_item_values_definition_binding", type_="check")
        batch_op.drop_constraint("ck_project_work_item_values_parameter_scope", type_="check")
        batch_op.drop_index("idx_project_work_item_values_extra_parameter_lookup")
        batch_op.drop_constraint("uq_project_work_item_values_item_extra_parameter", type_="unique")
        batch_op.drop_constraint("fk_project_work_item_values_tenant_extra_parameter", type_="foreignkey")
        batch_op.drop_column("resolved_parameter_scope")
        batch_op.drop_column("tenant_work_type_extra_parameter_id")
        batch_op.alter_column("work_type_parameter_id", existing_type=sa.String(length=64), nullable=False)

    op.drop_index("idx_tenant_extra_parameter_options_parameter_sort", table_name="tenant_work_type_extra_parameter_options")
    op.drop_table("tenant_work_type_extra_parameter_options")

    op.drop_index("idx_tenant_extra_parameters_setting_section_sort", table_name="tenant_work_type_extra_parameters")
    op.drop_index("idx_tenant_extra_parameters_org_work_type_status", table_name="tenant_work_type_extra_parameters")
    op.drop_table("tenant_work_type_extra_parameters")
