"""C2: Convert financial Float columns to NUMERIC(14,4).

Revision ID: 20260326_0015
Revises: 20260326_0014
Create Date: 2026-03-26

Precision: NUMERIC(14, 4) — up to 10 digits before the decimal point and 4
after, covering CZK/EUR amounts up to 9,999,999,999.9999. Geographic
coordinates (location_lat/lng, exif_lat/lng) and analytical measurements
(area, confidence, duration) keep Float — they represent physical quantities,
not monetary values.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260326_0015"
down_revision = "20260326_0014"
branch_labels = None
depends_on = None

_NUMERIC = sa.Numeric(14, 4)


def upgrade() -> None:
    # project_proposal_drafts
    with op.batch_alter_table("project_proposal_drafts") as batch_op:
        batch_op.alter_column("material_cost", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=True)
        batch_op.alter_column("labor_cost", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=True)
        batch_op.alter_column("transport_cost", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=True)
        batch_op.alter_column("amortization", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=True)
        batch_op.alter_column("margin", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=True)

    # project_final_proposals
    with op.batch_alter_table("project_final_proposals") as batch_op:
        batch_op.alter_column("total_price", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=True)

    # pricing_profiles
    with op.batch_alter_table("pricing_profiles") as batch_op:
        batch_op.alter_column("hourly_rate", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("daily_rate", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("labor_hours_per_sqm", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("margin_economy_pct", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("margin_standard_pct", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("margin_premium_pct", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("vat_pct", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)

    # material_catalog
    with op.batch_alter_table("material_catalog") as batch_op:
        batch_op.alter_column("norm_per_sqm", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("default_unit_price", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)

    # supplier_material_prices
    with op.batch_alter_table("supplier_material_prices") as batch_op:
        batch_op.alter_column("unit_price", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)

    # quote_variants
    with op.batch_alter_table("quote_variants") as batch_op:
        batch_op.alter_column("labor_cost", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("material_cost", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("other_cost", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("margin_pct", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("total_ex_vat", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("vat_amount", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("total_inc_vat", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)

    # quote_items
    with op.batch_alter_table("quote_items") as batch_op:
        batch_op.alter_column("quantity", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("unit_price", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("total_price", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=False)
        batch_op.alter_column("ai_suggested_unit_price", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=True)
        batch_op.alter_column("supplier_reference_unit_price", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=True)
        batch_op.alter_column("company_default_unit_price", type_=_NUMERIC, existing_type=sa.Float(), existing_nullable=True)


def downgrade() -> None:
    _FLOAT = sa.Float()

    with op.batch_alter_table("quote_items") as batch_op:
        for col in ("quantity", "unit_price", "total_price", "ai_suggested_unit_price",
                    "supplier_reference_unit_price", "company_default_unit_price"):
            batch_op.alter_column(col, type_=_FLOAT, existing_type=_NUMERIC, existing_nullable=col.endswith("price") and col != "unit_price")

    with op.batch_alter_table("quote_variants") as batch_op:
        for col in ("labor_cost", "material_cost", "other_cost", "margin_pct",
                    "total_ex_vat", "vat_amount", "total_inc_vat"):
            batch_op.alter_column(col, type_=_FLOAT, existing_type=_NUMERIC, existing_nullable=False)

    with op.batch_alter_table("supplier_material_prices") as batch_op:
        batch_op.alter_column("unit_price", type_=_FLOAT, existing_type=_NUMERIC, existing_nullable=False)

    with op.batch_alter_table("material_catalog") as batch_op:
        batch_op.alter_column("norm_per_sqm", type_=_FLOAT, existing_type=_NUMERIC, existing_nullable=False)
        batch_op.alter_column("default_unit_price", type_=_FLOAT, existing_type=_NUMERIC, existing_nullable=False)

    with op.batch_alter_table("pricing_profiles") as batch_op:
        for col in ("hourly_rate", "daily_rate", "labor_hours_per_sqm", "margin_economy_pct",
                    "margin_standard_pct", "margin_premium_pct", "vat_pct"):
            batch_op.alter_column(col, type_=_FLOAT, existing_type=_NUMERIC, existing_nullable=False)

    with op.batch_alter_table("project_final_proposals") as batch_op:
        batch_op.alter_column("total_price", type_=_FLOAT, existing_type=_NUMERIC, existing_nullable=True)

    with op.batch_alter_table("project_proposal_drafts") as batch_op:
        for col in ("material_cost", "labor_cost", "transport_cost", "amortization", "margin"):
            batch_op.alter_column(col, type_=_FLOAT, existing_type=_NUMERIC, existing_nullable=True)
