"""Expand work catalog with tenant parameter overrides and scaling indexes.

Revision ID: 20260330_0029
Revises: 20260330_0028
Create Date: 2026-03-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260330_0029"
down_revision = "20260330_0028"
branch_labels = None
depends_on = None


def _ts_now():
    return sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_index(
        "idx_work_types_analysis_profile_resolution",
        "work_types",
        ["default_analysis_profile_id", "state", "code"],
    )
    op.create_index(
        "idx_work_types_pricing_profile_resolution",
        "work_types",
        ["default_catalog_pricing_profile_id", "state", "code"],
    )
    op.create_index(
        "idx_tenant_work_type_settings_profile_resolution",
        "tenant_work_type_settings",
        ["organization_id", "analysis_profile_id", "catalog_pricing_profile_id", "work_type_id"],
    )
    op.create_index(
        "idx_project_work_items_org_status_updated",
        "project_work_items",
        ["organization_id", "status", "updated_at", "id"],
    )
    op.create_index(
        "idx_vision_detections_analysis_job_status",
        "vision_detections",
        ["analysis_job_id", "status", "created_at"],
    )
    op.create_index(
        "idx_vision_detections_reference_photo",
        "vision_detections",
        ["reference_photo_id", "created_at"],
    )

    op.create_table(
        "tenant_work_type_parameter_overrides",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_work_type_setting_id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("work_type_id", sa.String(length=64), nullable=False),
        sa.Column("work_type_parameter_id", sa.String(length=64), nullable=False),
        sa.Column("override_status", sa.String(length=32), nullable=False, server_default="inherited"),
        sa.Column("custom_display_name", sa.String(length=255), nullable=True),
        sa.Column("sort_order_override", sa.Integer(), nullable=True),
        sa.Column("default_text_value", sa.Text(), nullable=True),
        sa.Column("default_number_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("default_boolean_value", sa.Boolean(), nullable=True),
        sa.Column("default_option_code", sa.String(length=64), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by_user_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_ts_now()),
        sa.CheckConstraint(
            "override_status IN ('inherited', 'required', 'optional', 'hidden')",
            name="ck_tenant_parameter_overrides_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_work_type_setting_id"],
            ["tenant_work_type_settings.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_type_id"], ["work_types.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_type_parameter_id"], ["work_type_parameters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_work_type_setting_id",
            "work_type_parameter_id",
            name="uq_tenant_parameter_overrides_setting_parameter",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "work_type_parameter_id",
            name="uq_tenant_parameter_overrides_org_parameter",
        ),
    )
    op.create_index(
        "idx_tenant_parameter_overrides_org_work_type",
        "tenant_work_type_parameter_overrides",
        ["organization_id", "work_type_id", "override_status", "sort_order_override"],
    )
    op.create_index(
        "idx_tenant_parameter_overrides_setting_lookup",
        "tenant_work_type_parameter_overrides",
        ["tenant_work_type_setting_id", "work_type_parameter_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_tenant_parameter_overrides_setting_lookup",
        table_name="tenant_work_type_parameter_overrides",
    )
    op.drop_index(
        "idx_tenant_parameter_overrides_org_work_type",
        table_name="tenant_work_type_parameter_overrides",
    )
    op.drop_table("tenant_work_type_parameter_overrides")

    op.drop_index("idx_vision_detections_reference_photo", table_name="vision_detections")
    op.drop_index("idx_vision_detections_analysis_job_status", table_name="vision_detections")
    op.drop_index("idx_project_work_items_org_status_updated", table_name="project_work_items")
    op.drop_index(
        "idx_tenant_work_type_settings_profile_resolution",
        table_name="tenant_work_type_settings",
    )
    op.drop_index("idx_work_types_pricing_profile_resolution", table_name="work_types")
    op.drop_index("idx_work_types_analysis_profile_resolution", table_name="work_types")
