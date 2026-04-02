"""add analysis profile subsystem

Revision ID: 20260331_0032
Revises: 20260330_0031
Create Date: 2026-03-31 10:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260331_0032"
down_revision = "20260330_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("catalog_analysis_profiles") as batch_op:
        batch_op.drop_constraint("uq_catalog_analysis_profiles_code", type_="unique")
        batch_op.drop_index("idx_catalog_analysis_profiles_active_code")
        batch_op.add_column(sa.Column("status", sa.String(length=32), nullable=False, server_default="active"))
        batch_op.add_column(sa.Column("scope_code", sa.String(length=64), nullable=False, server_default="legacy-generic"))
        batch_op.add_column(sa.Column("scope_label", sa.String(length=255), nullable=False, server_default="Legacy Generic Scope"))
        batch_op.add_column(sa.Column("scope_description", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("fallback_mode", sa.String(length=32), nullable=False, server_default="manual_review"))
        batch_op.add_column(sa.Column("fallback_instructions", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "fallback_requires_manual_review",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            )
        )
        batch_op.create_unique_constraint(
            "uq_catalog_analysis_profiles_code_version",
            ["code", "profile_version"],
        )
        batch_op.create_index(
            "idx_catalog_analysis_profiles_active_code",
            ["is_active", "code", "profile_version"],
            unique=False,
        )

    op.create_check_constraint(
        "ck_catalog_analysis_profiles_status",
        "catalog_analysis_profiles",
        "status IN ('draft', 'active', 'deprecated', 'archived')",
    )
    op.create_check_constraint(
        "ck_catalog_analysis_profiles_fallback_mode",
        "catalog_analysis_profiles",
        "fallback_mode IN ('manual_review', 'request_more_photos', 'return_partial')",
    )

    op.create_table(
        "catalog_analysis_profile_target_objects",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("analysis_profile_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("object_role", sa.String(length=32), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["analysis_profile_id"], ["catalog_analysis_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_profile_id", "code", name="uq_analysis_profile_target_objects_code"),
        sa.CheckConstraint(
            "object_role IN ('primary', 'secondary', 'context')",
            name="ck_analysis_profile_target_objects_role",
        ),
    )
    op.create_index(
        "idx_analysis_profile_target_objects_profile_sort",
        "catalog_analysis_profile_target_objects",
        ["analysis_profile_id", "sort_order", "code"],
        unique=False,
    )

    op.create_table(
        "catalog_analysis_profile_ignored_objects",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("analysis_profile_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["analysis_profile_id"], ["catalog_analysis_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_profile_id", "code", name="uq_analysis_profile_ignored_objects_code"),
    )
    op.create_index(
        "idx_analysis_profile_ignored_objects_profile_sort",
        "catalog_analysis_profile_ignored_objects",
        ["analysis_profile_id", "sort_order", "code"],
        unique=False,
    )

    op.create_table(
        "catalog_analysis_profile_extraction_rules",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("analysis_profile_id", sa.String(length=64), nullable=False),
        sa.Column("attribute_code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("data_type", sa.String(length=32), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("target_parameter_code", sa.String(length=64), nullable=False),
        sa.Column("source_object_code", sa.String(length=64), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("manual_review_on_missing", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["analysis_profile_id"], ["catalog_analysis_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_profile_id", "attribute_code", name="uq_analysis_profile_extraction_rules_attribute"),
        sa.CheckConstraint(
            "data_type IN ('number', 'text', 'boolean', 'option')",
            name="ck_analysis_profile_extraction_rules_data_type",
        ),
    )
    op.create_index(
        "idx_analysis_profile_extraction_rules_profile_sort",
        "catalog_analysis_profile_extraction_rules",
        ["analysis_profile_id", "sort_order", "attribute_code"],
        unique=False,
    )

    op.create_table(
        "catalog_analysis_profile_validation_rules",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("analysis_profile_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("rule_type", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("target_attribute_code", sa.String(length=64), nullable=True),
        sa.Column("target_parameter_code", sa.String(length=64), nullable=True),
        sa.Column("min_number_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("max_number_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["analysis_profile_id"], ["catalog_analysis_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_profile_id", "code", name="uq_analysis_profile_validation_rules_code"),
        sa.CheckConstraint(
            "rule_type IN ('min_photos', 'required_attribute', 'numeric_range', 'confidence_gate')",
            name="ck_analysis_profile_validation_rules_type",
        ),
        sa.CheckConstraint(
            "severity IN ('warning', 'blocking')",
            name="ck_analysis_profile_validation_rules_severity",
        ),
    )
    op.create_index(
        "idx_analysis_profile_validation_rules_profile_sort",
        "catalog_analysis_profile_validation_rules",
        ["analysis_profile_id", "sort_order", "code"],
        unique=False,
    )

    op.create_table(
        "catalog_analysis_profile_confidence_thresholds",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("analysis_profile_id", sa.String(length=64), nullable=False),
        sa.Column("attribute_code", sa.String(length=64), nullable=False),
        sa.Column("target_object_code", sa.String(length=64), nullable=True),
        sa.Column("min_confidence", sa.Numeric(8, 4), nullable=False),
        sa.Column("preferred_confidence", sa.Numeric(8, 4), nullable=False),
        sa.Column("action_below_threshold", sa.String(length=32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["analysis_profile_id"], ["catalog_analysis_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_profile_id", "attribute_code", name="uq_analysis_profile_confidence_thresholds_attribute"),
        sa.CheckConstraint(
            "action_below_threshold IN ('manual_review', 'drop_attribute', 'fail_analysis')",
            name="ck_analysis_profile_confidence_thresholds_action",
        ),
    )
    op.create_index(
        "idx_analysis_profile_confidence_thresholds_profile_sort",
        "catalog_analysis_profile_confidence_thresholds",
        ["analysis_profile_id", "sort_order", "attribute_code"],
        unique=False,
    )

    op.create_table(
        "catalog_analysis_profile_output_mappings",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("analysis_profile_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("target_entity", sa.String(length=32), nullable=False),
        sa.Column("target_field", sa.String(length=64), nullable=False),
        sa.Column("source_attribute_code", sa.String(length=64), nullable=False),
        sa.Column("target_parameter_code", sa.String(length=64), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["analysis_profile_id"], ["catalog_analysis_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_profile_id", "code", name="uq_analysis_profile_output_mappings_code"),
        sa.CheckConstraint(
            "target_entity IN ('analysis_result', 'project_work_item', 'project_work_item_value', 'vision_detection')",
            name="ck_analysis_profile_output_mappings_target_entity",
        ),
    )
    op.create_index(
        "idx_analysis_profile_output_mappings_profile_sort",
        "catalog_analysis_profile_output_mappings",
        ["analysis_profile_id", "sort_order", "code"],
        unique=False,
    )

    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.add_column(sa.Column("requested_work_type_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("analysis_profile_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("resolved_analysis_profile_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("resolved_analysis_profile_version", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_analysis_jobs_analysis_profile_id",
            "catalog_analysis_profiles",
            ["analysis_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "idx_analysis_jobs_work_type_profile_status",
            ["project_id", "requested_work_type_code", "analysis_profile_id", "status"],
            unique=False,
        )

    with op.batch_alter_table("analysis_results") as batch_op:
        batch_op.add_column(sa.Column("resolved_work_type_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("analysis_profile_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("resolved_analysis_profile_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("resolved_analysis_profile_version", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("estimated_quantity", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("estimated_unit", sa.String(length=32), nullable=True))
        batch_op.create_foreign_key(
            "fk_analysis_results_analysis_profile_id",
            "catalog_analysis_profiles",
            ["analysis_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "idx_analysis_results_work_type_profile_created",
            ["project_id", "resolved_work_type_code", "analysis_profile_id", "created_at", "id"],
            unique=False,
        )

    with op.batch_alter_table("project_work_items") as batch_op:
        batch_op.add_column(sa.Column("resolved_analysis_profile_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("resolved_analysis_profile_version", sa.Integer(), nullable=True))
        batch_op.create_index(
            "idx_project_work_items_analysis_profile",
            ["project_id", "analysis_profile_id", "resolved_work_type_code"],
            unique=False,
        )

    with op.batch_alter_table("vision_detections") as batch_op:
        batch_op.add_column(sa.Column("resolved_analysis_profile_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("resolved_analysis_profile_version", sa.Integer(), nullable=True))
        batch_op.create_index(
            "idx_vision_detections_profile_lookup",
            ["project_id", "analysis_profile_id", "resolved_work_type_code"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("vision_detections") as batch_op:
        batch_op.drop_index("idx_vision_detections_profile_lookup")
        batch_op.drop_column("resolved_analysis_profile_version")
        batch_op.drop_column("resolved_analysis_profile_code")

    with op.batch_alter_table("project_work_items") as batch_op:
        batch_op.drop_index("idx_project_work_items_analysis_profile")
        batch_op.drop_column("resolved_analysis_profile_version")
        batch_op.drop_column("resolved_analysis_profile_code")

    with op.batch_alter_table("analysis_results") as batch_op:
        batch_op.drop_index("idx_analysis_results_work_type_profile_created")
        batch_op.drop_constraint("fk_analysis_results_analysis_profile_id", type_="foreignkey")
        batch_op.drop_column("estimated_unit")
        batch_op.drop_column("estimated_quantity")
        batch_op.drop_column("resolved_analysis_profile_version")
        batch_op.drop_column("resolved_analysis_profile_code")
        batch_op.drop_column("analysis_profile_id")
        batch_op.drop_column("resolved_work_type_code")

    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.drop_index("idx_analysis_jobs_work_type_profile_status")
        batch_op.drop_constraint("fk_analysis_jobs_analysis_profile_id", type_="foreignkey")
        batch_op.drop_column("resolved_analysis_profile_version")
        batch_op.drop_column("resolved_analysis_profile_code")
        batch_op.drop_column("analysis_profile_id")
        batch_op.drop_column("requested_work_type_code")

    op.drop_index("idx_analysis_profile_output_mappings_profile_sort", table_name="catalog_analysis_profile_output_mappings")
    op.drop_table("catalog_analysis_profile_output_mappings")
    op.drop_index("idx_analysis_profile_confidence_thresholds_profile_sort", table_name="catalog_analysis_profile_confidence_thresholds")
    op.drop_table("catalog_analysis_profile_confidence_thresholds")
    op.drop_index("idx_analysis_profile_validation_rules_profile_sort", table_name="catalog_analysis_profile_validation_rules")
    op.drop_table("catalog_analysis_profile_validation_rules")
    op.drop_index("idx_analysis_profile_extraction_rules_profile_sort", table_name="catalog_analysis_profile_extraction_rules")
    op.drop_table("catalog_analysis_profile_extraction_rules")
    op.drop_index("idx_analysis_profile_ignored_objects_profile_sort", table_name="catalog_analysis_profile_ignored_objects")
    op.drop_table("catalog_analysis_profile_ignored_objects")
    op.drop_index("idx_analysis_profile_target_objects_profile_sort", table_name="catalog_analysis_profile_target_objects")
    op.drop_table("catalog_analysis_profile_target_objects")

    op.drop_constraint("ck_catalog_analysis_profiles_fallback_mode", "catalog_analysis_profiles", type_="check")
    op.drop_constraint("ck_catalog_analysis_profiles_status", "catalog_analysis_profiles", type_="check")
    with op.batch_alter_table("catalog_analysis_profiles") as batch_op:
        batch_op.drop_index("idx_catalog_analysis_profiles_active_code")
        batch_op.drop_constraint("uq_catalog_analysis_profiles_code_version", type_="unique")
        batch_op.drop_column("fallback_requires_manual_review")
        batch_op.drop_column("fallback_instructions")
        batch_op.drop_column("fallback_mode")
        batch_op.drop_column("scope_description")
        batch_op.drop_column("scope_label")
        batch_op.drop_column("scope_code")
        batch_op.drop_column("status")
        batch_op.create_unique_constraint("uq_catalog_analysis_profiles_code", ["code"])
        batch_op.create_index("idx_catalog_analysis_profiles_active_code", ["is_active", "code"], unique=False)
