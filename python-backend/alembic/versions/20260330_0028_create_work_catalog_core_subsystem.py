"""Create work catalog core subsystem tables.

Revision ID: 20260330_0028
Revises: 20260330_0027
Create Date: 2026-03-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260330_0028"
down_revision = "20260330_0027"
branch_labels = None
depends_on = None


def _ts_now():
    return sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "work_categories",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("catalog_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_work_categories_code"),
        sa.UniqueConstraint("slug", name="uq_work_categories_slug"),
    )
    op.create_index("idx_work_categories_active_sort", "work_categories", ["is_active", "sort_order", "code"])

    op.create_table(
        "catalog_analysis_profiles",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider_family", sa.String(length=64), nullable=False),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("output_contract_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confidence_threshold", sa.Numeric(8, 4), nullable=True),
        sa.Column("max_detections_per_photo", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("profile_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.CheckConstraint(
            "task_type IN ('classification', 'detection', 'measurement', 'hybrid')",
            name="ck_catalog_analysis_profiles_task_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_catalog_analysis_profiles_code"),
    )
    op.create_index(
        "idx_catalog_analysis_profiles_active_code",
        "catalog_analysis_profiles",
        ["is_active", "code"],
    )

    op.create_table(
        "catalog_pricing_profiles",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("pricing_strategy", sa.String(length=32), nullable=False),
        sa.Column("labor_rate_source", sa.String(length=32), nullable=False),
        sa.Column("material_pricing_source", sa.String(length=32), nullable=False),
        sa.Column("default_margin_pct", sa.Numeric(14, 4), nullable=True),
        sa.Column("default_markup_pct", sa.Numeric(14, 4), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("profile_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.CheckConstraint(
            "pricing_strategy IN ('tenant_pricebook', 'fixed_formula', 'manual_review')",
            name="ck_catalog_pricing_profiles_strategy",
        ),
        sa.CheckConstraint(
            "labor_rate_source IN ('tenant_default', 'catalog_default', 'manual')",
            name="ck_catalog_pricing_profiles_labor_rate_source",
        ),
        sa.CheckConstraint(
            "material_pricing_source IN ('tenant_pricebook', 'catalog_default', 'manual')",
            name="ck_catalog_pricing_profiles_material_pricing_source",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_catalog_pricing_profiles_code"),
    )
    op.create_index(
        "idx_catalog_pricing_profiles_active_code",
        "catalog_pricing_profiles",
        ["is_active", "code"],
    )

    op.create_table(
        "work_types",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("category_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_unit", sa.String(length=32), nullable=False),
        sa.Column("measurement_kind", sa.String(length=32), nullable=False, server_default="area"),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("default_analysis_profile_id", sa.String(length=64), nullable=True),
        sa.Column("default_catalog_pricing_profile_id", sa.String(length=64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("catalog_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.CheckConstraint("state IN ('active', 'hidden', 'deprecated')", name="ck_work_types_state"),
        sa.ForeignKeyConstraint(["category_id"], ["work_categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["default_analysis_profile_id"],
            ["catalog_analysis_profiles.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["default_catalog_pricing_profile_id"],
            ["catalog_pricing_profiles.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_work_types_code"),
        sa.UniqueConstraint("slug", name="uq_work_types_slug"),
    )
    op.create_index("idx_work_types_category_state_sort", "work_types", ["category_id", "state", "sort_order", "code"])

    op.create_table(
        "work_type_parameters",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("work_type_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("data_type", sa.String(length=32), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("default_text_value", sa.Text(), nullable=True),
        sa.Column("default_number_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("default_boolean_value", sa.Boolean(), nullable=True),
        sa.Column("default_option_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.CheckConstraint(
            "data_type IN ('number', 'text', 'boolean', 'option')",
            name="ck_work_type_parameters_data_type",
        ),
        sa.ForeignKeyConstraint(["work_type_id"], ["work_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("work_type_id", "code", name="uq_work_type_parameters_work_type_code"),
        sa.UniqueConstraint("work_type_id", "slug", name="uq_work_type_parameters_work_type_slug"),
    )
    op.create_index("idx_work_type_parameters_work_type_sort", "work_type_parameters", ["work_type_id", "sort_order", "code"])

    op.create_table(
        "work_type_parameter_options",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("work_type_parameter_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.ForeignKeyConstraint(["work_type_parameter_id"], ["work_type_parameters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("work_type_parameter_id", "code", name="uq_work_type_parameter_options_param_code"),
    )
    op.create_index(
        "idx_work_type_parameter_options_param_sort",
        "work_type_parameter_options",
        ["work_type_parameter_id", "sort_order", "code"],
    )

    op.create_table(
        "tenant_work_type_settings",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("work_type_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="inherited"),
        sa.Column("custom_display_name", sa.String(length=255), nullable=True),
        sa.Column("analysis_profile_id", sa.String(length=64), nullable=True),
        sa.Column("catalog_pricing_profile_id", sa.String(length=64), nullable=True),
        sa.Column("tenant_pricing_profile_id", sa.String(length=64), nullable=True),
        sa.Column("is_billable_override", sa.Boolean(), nullable=True),
        sa.Column("sort_order_override", sa.Integer(), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by_user_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.CheckConstraint(
            "status IN ('inherited', 'enabled', 'disabled')",
            name="ck_tenant_work_type_settings_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_type_id"], ["work_types.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["analysis_profile_id"], ["catalog_analysis_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["catalog_pricing_profile_id"], ["catalog_pricing_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_pricing_profile_id"], ["pricing_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "work_type_id", name="uq_tenant_work_type_settings_org_work_type"),
    )
    op.create_index(
        "idx_tenant_work_type_settings_org_status",
        "tenant_work_type_settings",
        ["organization_id", "status", "work_type_id"],
    )

    op.create_table(
        "project_work_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("work_type_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_work_type_setting_id", sa.String(length=64), nullable=True),
        sa.Column("analysis_profile_id", sa.String(length=64), nullable=True),
        sa.Column("catalog_pricing_profile_id", sa.String(length=64), nullable=True),
        sa.Column("tenant_pricing_profile_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("source_type", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("item_sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("resolved_display_name", sa.String(length=255), nullable=False),
        sa.Column("resolved_work_type_code", sa.String(length=64), nullable=False),
        sa.Column("resolved_category_code", sa.String(length=64), nullable=False),
        sa.Column("resolved_unit", sa.String(length=32), nullable=False),
        sa.Column("resolved_catalog_version", sa.Integer(), nullable=False),
        sa.Column("resolved_setting_version", sa.Integer(), nullable=True),
        sa.Column("measured_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("measured_unit", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.CheckConstraint(
            "status IN ('draft', 'resolved', 'accepted', 'rejected')",
            name="ck_project_work_items_status",
        ),
        sa.CheckConstraint(
            "source_type IN ('manual', 'vision', 'import', 'system')",
            name="ck_project_work_items_source_type",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_type_id"], ["work_types.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_work_type_setting_id"], ["tenant_work_type_settings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["analysis_profile_id"], ["catalog_analysis_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["catalog_pricing_profile_id"], ["catalog_pricing_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_pricing_profile_id"], ["pricing_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "work_type_id",
            "item_sequence",
            name="uq_project_work_items_project_work_type_sequence",
        ),
    )
    op.create_index(
        "idx_project_work_items_org_project_status",
        "project_work_items",
        ["organization_id", "project_id", "status", "item_sequence"],
    )
    op.create_index(
        "idx_project_work_items_project_work_type",
        "project_work_items",
        ["project_id", "work_type_id", "item_sequence"],
    )

    op.create_table(
        "project_work_item_values",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_work_item_id", sa.String(length=64), nullable=False),
        sa.Column("work_type_parameter_id", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("resolved_parameter_code", sa.String(length=64), nullable=False),
        sa.Column("resolved_parameter_name", sa.String(length=255), nullable=False),
        sa.Column("resolved_data_type", sa.String(length=32), nullable=False),
        sa.Column("resolved_unit", sa.String(length=32), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_number", sa.Numeric(18, 4), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.Column("value_option_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.CheckConstraint(
            "source_type IN ('manual', 'vision', 'import', 'system')",
            name="ck_project_work_item_values_source_type",
        ),
        sa.ForeignKeyConstraint(["project_work_item_id"], ["project_work_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_type_parameter_id"], ["work_type_parameters.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_work_item_id",
            "work_type_parameter_id",
            name="uq_project_work_item_values_item_parameter",
        ),
    )
    op.create_index("idx_project_work_item_values_item", "project_work_item_values", ["project_work_item_id", "resolved_parameter_code"])

    op.create_table(
        "vision_detections",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("project_work_item_id", sa.String(length=64), nullable=True),
        sa.Column("analysis_job_id", sa.String(length=64), nullable=True),
        sa.Column("work_type_id", sa.String(length=64), nullable=False),
        sa.Column("analysis_profile_id", sa.String(length=64), nullable=True),
        sa.Column("reference_photo_id", sa.String(length=64), nullable=True),
        sa.Column("detection_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("confidence_score", sa.Numeric(8, 4), nullable=True),
        sa.Column("raw_label", sa.String(length=255), nullable=True),
        sa.Column("raw_value", sa.String(length=255), nullable=True),
        sa.Column("detected_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("detected_unit", sa.String(length=32), nullable=True),
        sa.Column("geometry_type", sa.String(length=32), nullable=True),
        sa.Column("bbox_left", sa.Numeric(10, 4), nullable=True),
        sa.Column("bbox_top", sa.Numeric(10, 4), nullable=True),
        sa.Column("bbox_right", sa.Numeric(10, 4), nullable=True),
        sa.Column("bbox_bottom", sa.Numeric(10, 4), nullable=True),
        sa.Column("geometry_json", sa.Text(), nullable=True),
        sa.Column("resolved_work_type_code", sa.String(length=64), nullable=False),
        sa.Column("source_provider", sa.String(length=64), nullable=True),
        sa.Column("source_model", sa.String(length=128), nullable=True),
        sa.Column("source_model_version", sa.String(length=64), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'linked')",
            name="ck_vision_detections_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_work_item_id"], ["project_work_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["analysis_job_id"], ["analysis_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_type_id"], ["work_types.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["analysis_profile_id"], ["catalog_analysis_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reference_photo_id"], ["project_photos.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "detection_key", name="uq_vision_detections_project_detection_key"),
    )
    op.create_index(
        "idx_vision_detections_org_project_status",
        "vision_detections",
        ["organization_id", "project_id", "status", "created_at"],
    )
    op.create_index(
        "idx_vision_detections_project_work_item",
        "vision_detections",
        ["project_work_item_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_vision_detections_project_work_item", table_name="vision_detections")
    op.drop_index("idx_vision_detections_org_project_status", table_name="vision_detections")
    op.drop_table("vision_detections")

    op.drop_index("idx_project_work_item_values_item", table_name="project_work_item_values")
    op.drop_table("project_work_item_values")

    op.drop_index("idx_project_work_items_project_work_type", table_name="project_work_items")
    op.drop_index("idx_project_work_items_org_project_status", table_name="project_work_items")
    op.drop_table("project_work_items")

    op.drop_index("idx_tenant_work_type_settings_org_status", table_name="tenant_work_type_settings")
    op.drop_table("tenant_work_type_settings")

    op.drop_index("idx_work_type_parameter_options_param_sort", table_name="work_type_parameter_options")
    op.drop_table("work_type_parameter_options")

    op.drop_index("idx_work_type_parameters_work_type_sort", table_name="work_type_parameters")
    op.drop_table("work_type_parameters")

    op.drop_index("idx_work_types_category_state_sort", table_name="work_types")
    op.drop_table("work_types")

    op.drop_index("idx_catalog_pricing_profiles_active_code", table_name="catalog_pricing_profiles")
    op.drop_table("catalog_pricing_profiles")

    op.drop_index("idx_catalog_analysis_profiles_active_code", table_name="catalog_analysis_profiles")
    op.drop_table("catalog_analysis_profiles")

    op.drop_index("idx_work_categories_active_sort", table_name="work_categories")
    op.drop_table("work_categories")
