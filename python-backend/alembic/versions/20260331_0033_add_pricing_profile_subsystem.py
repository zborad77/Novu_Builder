"""add pricing profile subsystem

Revision ID: 20260331_0033
Revises: 20260331_0032
Create Date: 2026-03-31 14:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260331_0033"
down_revision = "20260331_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("catalog_pricing_profiles") as batch_op:
        batch_op.drop_constraint("uq_catalog_pricing_profiles_code", type_="unique")
        batch_op.drop_index("idx_catalog_pricing_profiles_active_code")
        batch_op.drop_constraint("ck_catalog_pricing_profiles_strategy", type_="check")
        batch_op.add_column(sa.Column("status", sa.String(length=32), nullable=False, server_default="active"))
        batch_op.add_column(sa.Column("pricing_basis", sa.String(length=32), nullable=False, server_default="area"))
        batch_op.add_column(sa.Column("currency", sa.String(length=8), nullable=False, server_default="CZK"))
        batch_op.add_column(sa.Column("min_job_price", sa.Numeric(14, 4), nullable=True))
        batch_op.add_column(sa.Column("metadata_json", sa.Text(), nullable=True))
        batch_op.create_unique_constraint(
            "uq_catalog_pricing_profiles_code_version",
            ["code", "profile_version"],
        )
        batch_op.create_index(
            "idx_catalog_pricing_profiles_active_code",
            ["is_active", "code", "profile_version"],
            unique=False,
        )

    op.create_check_constraint(
        "ck_catalog_pricing_profiles_status",
        "catalog_pricing_profiles",
        "status IN ('draft', 'active', 'deprecated', 'archived')",
    )
    op.create_check_constraint(
        "ck_catalog_pricing_profiles_basis",
        "catalog_pricing_profiles",
        "pricing_basis IN ('area', 'length', 'count', 'volume', 'scope', 'inspection', 'service', 'incident')",
    )
    op.create_check_constraint(
        "ck_catalog_pricing_profiles_strategy",
        "catalog_pricing_profiles",
        "pricing_strategy IN ('tenant_pricebook', 'catalog_formula', 'fixed_formula', 'manual_review')",
    )

    op.create_table(
        "catalog_pricing_profile_required_inputs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("catalog_pricing_profile_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["catalog_pricing_profile_id"], ["catalog_pricing_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_pricing_profile_id", "code", name="uq_catalog_pricing_profile_required_inputs_code"),
        sa.CheckConstraint(
            "source_type IN ('parameter', 'work_item_field')",
            name="ck_catalog_pricing_profile_required_inputs_source",
        ),
    )
    op.create_index(
        "idx_catalog_pricing_profile_required_inputs_profile_sort",
        "catalog_pricing_profile_required_inputs",
        ["catalog_pricing_profile_id", "sort_order", "code"],
        unique=False,
    )

    op.create_table(
        "catalog_pricing_profile_labor_assumptions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("catalog_pricing_profile_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity_source_type", sa.String(length=32), nullable=False),
        sa.Column("quantity_source_key", sa.String(length=64), nullable=True),
        sa.Column("hours_per_unit", sa.Numeric(14, 4), nullable=False),
        sa.Column("crew_size", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["catalog_pricing_profile_id"], ["catalog_pricing_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_pricing_profile_id", "code", name="uq_catalog_pricing_profile_labor_assumptions_code"),
        sa.CheckConstraint(
            "quantity_source_type IN ('parameter', 'work_item_field', 'constant')",
            name="ck_catalog_pricing_profile_labor_assumptions_quantity_source",
        ),
    )
    op.create_index(
        "idx_catalog_pricing_profile_labor_assumptions_profile_sort",
        "catalog_pricing_profile_labor_assumptions",
        ["catalog_pricing_profile_id", "sort_order", "code"],
        unique=False,
    )

    op.create_table(
        "catalog_pricing_profile_material_assumptions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("catalog_pricing_profile_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity_source_type", sa.String(length=32), nullable=False),
        sa.Column("quantity_source_key", sa.String(length=64), nullable=True),
        sa.Column("quantity_per_unit", sa.Numeric(14, 4), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("default_unit_cost", sa.Numeric(14, 4), nullable=True),
        sa.Column("waste_factor_pct", sa.Numeric(14, 4), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["catalog_pricing_profile_id"], ["catalog_pricing_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_pricing_profile_id", "code", name="uq_catalog_pricing_profile_material_assumptions_code"),
        sa.CheckConstraint(
            "quantity_source_type IN ('parameter', 'work_item_field', 'constant')",
            name="ck_catalog_pricing_profile_material_assumptions_quantity_source",
        ),
    )
    op.create_index(
        "idx_catalog_pricing_profile_material_assumptions_profile_sort",
        "catalog_pricing_profile_material_assumptions",
        ["catalog_pricing_profile_id", "sort_order", "code"],
        unique=False,
    )

    op.create_table(
        "catalog_pricing_profile_base_rules",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("catalog_pricing_profile_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("line_type", sa.String(length=32), nullable=False),
        sa.Column("calculation_method", sa.String(length=32), nullable=False),
        sa.Column("quantity_source_type", sa.String(length=32), nullable=False),
        sa.Column("quantity_source_key", sa.String(length=64), nullable=True),
        sa.Column("quantity_multiplier", sa.Numeric(14, 4), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("rate_source", sa.String(length=32), nullable=False),
        sa.Column("rate_value", sa.Numeric(14, 4), nullable=True),
        sa.Column("labor_assumption_code", sa.String(length=64), nullable=True),
        sa.Column("material_assumption_code", sa.String(length=64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["catalog_pricing_profile_id"], ["catalog_pricing_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_pricing_profile_id", "code", name="uq_catalog_pricing_profile_base_rules_code"),
        sa.CheckConstraint("line_type IN ('labor', 'material', 'other')", name="ck_catalog_pricing_profile_base_rules_line_type"),
        sa.CheckConstraint("calculation_method IN ('per_unit', 'fixed')", name="ck_catalog_pricing_profile_base_rules_calculation_method"),
        sa.CheckConstraint(
            "quantity_source_type IN ('parameter', 'work_item_field', 'constant')",
            name="ck_catalog_pricing_profile_base_rules_quantity_source",
        ),
        sa.CheckConstraint(
            "rate_source IN ('tenant_hourly_rate', 'tenant_daily_rate', 'catalog_unit_rate', 'catalog_flat_rate')",
            name="ck_catalog_pricing_profile_base_rules_rate_source",
        ),
    )
    op.create_index(
        "idx_catalog_pricing_profile_base_rules_profile_sort",
        "catalog_pricing_profile_base_rules",
        ["catalog_pricing_profile_id", "sort_order", "code"],
        unique=False,
    )

    op.create_table(
        "catalog_pricing_profile_adjustment_rules",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("catalog_pricing_profile_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_scope", sa.String(length=32), nullable=False),
        sa.Column("target_line_type", sa.String(length=32), nullable=True),
        sa.Column("target_base_rule_code", sa.String(length=64), nullable=True),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("adjustment_value", sa.Numeric(14, 4), nullable=False),
        sa.Column("condition_source_type", sa.String(length=32), nullable=False),
        sa.Column("condition_source_key", sa.String(length=64), nullable=False),
        sa.Column("condition_operator", sa.String(length=32), nullable=False),
        sa.Column("condition_text_value", sa.Text(), nullable=True),
        sa.Column("condition_number_value", sa.Numeric(14, 4), nullable=True),
        sa.Column("condition_boolean_value", sa.Boolean(), nullable=True),
        sa.Column("condition_option_code", sa.String(length=64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["catalog_pricing_profile_id"], ["catalog_pricing_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_pricing_profile_id", "code", name="uq_catalog_pricing_profile_adjustment_rules_code"),
        sa.CheckConstraint(
            "target_scope IN ('profile_total', 'line_type', 'base_rule')",
            name="ck_catalog_pricing_profile_adjustment_rules_target_scope",
        ),
        sa.CheckConstraint(
            "target_line_type IS NULL OR target_line_type IN ('labor', 'material', 'other')",
            name="ck_catalog_pricing_profile_adjustment_rules_target_line_type",
        ),
        sa.CheckConstraint(
            "operation IN ('multiply', 'add_flat')",
            name="ck_catalog_pricing_profile_adjustment_rules_operation",
        ),
        sa.CheckConstraint(
            "condition_source_type IN ('parameter', 'work_item_field')",
            name="ck_catalog_pricing_profile_adjustment_rules_condition_source",
        ),
        sa.CheckConstraint(
            "condition_operator IN ('eq', 'gte', 'lte', 'true')",
            name="ck_catalog_pricing_profile_adjustment_rules_operator",
        ),
        sa.CheckConstraint(
            "(CASE WHEN condition_text_value IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN condition_number_value IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN condition_boolean_value IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN condition_option_code IS NOT NULL THEN 1 ELSE 0 END) <= 1",
            name="ck_pricing_adj_rules_single_condition_value",
        ),
    )
    op.create_index(
        "idx_catalog_pricing_profile_adjustment_rules_profile_sort",
        "catalog_pricing_profile_adjustment_rules",
        ["catalog_pricing_profile_id", "sort_order", "code"],
        unique=False,
    )

    with op.batch_alter_table("project_work_items") as batch_op:
        batch_op.add_column(sa.Column("resolved_catalog_pricing_profile_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("resolved_catalog_pricing_profile_version", sa.Integer(), nullable=True))
        batch_op.create_index(
            "idx_project_work_items_pricing_profile",
            ["project_id", "catalog_pricing_profile_id", "resolved_work_type_code"],
            unique=False,
        )

    with op.batch_alter_table("quote_variants") as batch_op:
        batch_op.add_column(sa.Column("currency", sa.String(length=8), nullable=False, server_default="CZK"))
        batch_op.add_column(sa.Column("vat_pct", sa.Numeric(14, 4), nullable=False, server_default="21"))
        batch_op.add_column(sa.Column("pricing_summary_json", sa.Text(), nullable=True))
        batch_op.create_index(
            "idx_quote_variants_project_created_id",
            ["project_id", "created_at", "id"],
            unique=False,
        )

    with op.batch_alter_table("quote_items") as batch_op:
        batch_op.add_column(sa.Column("project_work_item_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("catalog_pricing_profile_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("work_type_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("resolved_catalog_pricing_profile_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("resolved_catalog_pricing_profile_version", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("catalog_pricing_rule_code", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            "fk_quote_items_project_work_item_id",
            "project_work_items",
            ["project_work_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_quote_items_catalog_pricing_profile_id",
            "catalog_pricing_profiles",
            ["catalog_pricing_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "idx_quote_items_quote_variant_sort",
            ["quote_variant_id", "sort_order", "id"],
            unique=False,
        )
        batch_op.create_index(
            "idx_quote_items_project_work_item",
            ["project_work_item_id", "sort_order", "id"],
            unique=False,
        )
        batch_op.create_index(
            "idx_quote_items_pricing_rule_lookup",
            ["catalog_pricing_profile_id", "catalog_pricing_rule_code", "work_type_code"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("quote_items") as batch_op:
        batch_op.drop_index("idx_quote_items_pricing_rule_lookup")
        batch_op.drop_index("idx_quote_items_project_work_item")
        batch_op.drop_index("idx_quote_items_quote_variant_sort")
        batch_op.drop_constraint("fk_quote_items_catalog_pricing_profile_id", type_="foreignkey")
        batch_op.drop_constraint("fk_quote_items_project_work_item_id", type_="foreignkey")
        batch_op.drop_column("catalog_pricing_rule_code")
        batch_op.drop_column("resolved_catalog_pricing_profile_version")
        batch_op.drop_column("resolved_catalog_pricing_profile_code")
        batch_op.drop_column("work_type_code")
        batch_op.drop_column("catalog_pricing_profile_id")
        batch_op.drop_column("project_work_item_id")

    with op.batch_alter_table("quote_variants") as batch_op:
        batch_op.drop_index("idx_quote_variants_project_created_id")
        batch_op.drop_column("pricing_summary_json")
        batch_op.drop_column("vat_pct")
        batch_op.drop_column("currency")

    with op.batch_alter_table("project_work_items") as batch_op:
        batch_op.drop_index("idx_project_work_items_pricing_profile")
        batch_op.drop_column("resolved_catalog_pricing_profile_version")
        batch_op.drop_column("resolved_catalog_pricing_profile_code")

    op.drop_index("idx_catalog_pricing_profile_adjustment_rules_profile_sort", table_name="catalog_pricing_profile_adjustment_rules")
    op.drop_table("catalog_pricing_profile_adjustment_rules")
    op.drop_index("idx_catalog_pricing_profile_base_rules_profile_sort", table_name="catalog_pricing_profile_base_rules")
    op.drop_table("catalog_pricing_profile_base_rules")
    op.drop_index("idx_catalog_pricing_profile_material_assumptions_profile_sort", table_name="catalog_pricing_profile_material_assumptions")
    op.drop_table("catalog_pricing_profile_material_assumptions")
    op.drop_index("idx_catalog_pricing_profile_labor_assumptions_profile_sort", table_name="catalog_pricing_profile_labor_assumptions")
    op.drop_table("catalog_pricing_profile_labor_assumptions")
    op.drop_index("idx_catalog_pricing_profile_required_inputs_profile_sort", table_name="catalog_pricing_profile_required_inputs")
    op.drop_table("catalog_pricing_profile_required_inputs")

    op.drop_constraint("ck_catalog_pricing_profiles_strategy", "catalog_pricing_profiles", type_="check")
    op.drop_constraint("ck_catalog_pricing_profiles_basis", "catalog_pricing_profiles", type_="check")
    op.drop_constraint("ck_catalog_pricing_profiles_status", "catalog_pricing_profiles", type_="check")

    with op.batch_alter_table("catalog_pricing_profiles") as batch_op:
        batch_op.drop_constraint("uq_catalog_pricing_profiles_code_version", type_="unique")
        batch_op.drop_index("idx_catalog_pricing_profiles_active_code")
        batch_op.create_unique_constraint("uq_catalog_pricing_profiles_code", ["code"])
        batch_op.create_index("idx_catalog_pricing_profiles_active_code", ["is_active", "code"], unique=False)
        batch_op.drop_column("metadata_json")
        batch_op.drop_column("min_job_price")
        batch_op.drop_column("currency")
        batch_op.drop_column("pricing_basis")
        batch_op.drop_column("status")

    op.create_check_constraint(
        "ck_catalog_pricing_profiles_strategy",
        "catalog_pricing_profiles",
        "pricing_strategy IN ('tenant_pricebook', 'fixed_formula', 'manual_review')",
    )
