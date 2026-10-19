from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db.base import Base
from app.platform.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.modules.cases.models import Project
    from app.modules.identity.models import Organization, User


class ProjectProposalDraft(TimestampMixin, Base):
    __tablename__ = "project_proposal_drafts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    material_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    labor_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    transport_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    amortization: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    margin: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    recommended_supplier: Mapped[str | None] = mapped_column(String(255))
    recommended_company: Mapped[str | None] = mapped_column(String(255))

    project: Mapped["Project"] = relationship(back_populates="proposal_draft")


class ProjectFinalProposal(TimestampMixin, Base):
    __tablename__ = "project_final_proposals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    analysis_result_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_results.id", ondelete="SET NULL"))
    draft_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="ready_for_export", nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CZK", nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="final_proposals")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'canceled', 'dead_letter')",
            name="ck_analysis_jobs_status",
        ),
        Index(
            "idx_analysis_jobs_project_status_created_id",
            "project_id",
            "status",
            "created_at",
            "id",
        ),
        Index(
            "idx_analysis_jobs_project_created_id",
            "project_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_work_type_code: Mapped[str | None] = mapped_column(String(64))
    analysis_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_analysis_profiles.id", ondelete="SET NULL")
    )
    resolved_analysis_profile_code: Mapped[str | None] = mapped_column(String(64))
    resolved_analysis_profile_version: Mapped[int | None] = mapped_column(Integer)
    requested_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    parent_job_id: Mapped[str | None] = mapped_column(String(64))   # set when this is a retry
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_token: Mapped[str | None] = mapped_column(String(128))
    worker_id: Mapped[str | None] = mapped_column(String(255))
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_traceback: Mapped[str | None] = mapped_column(Text)       # full traceback
    input_payload: Mapped[str | None] = mapped_column(Text)         # JSON: co šlo do AI
    input_payload_storage_key: Mapped[str | None] = mapped_column(String(512))
    output_summary: Mapped[str | None] = mapped_column(Text)        # JSON: co přišlo zpět
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="analysis_jobs")
    requested_by_user: Mapped["User | None"] = relationship(back_populates="analysis_jobs")
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(back_populates="analysis_job")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    __table_args__ = (
        Index(
            "idx_analysis_results_project_created_id",
            "project_id",
            "created_at",
            "id",
        ),
        Index(
            "idx_analysis_results_job_created_id",
            "analysis_job_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    analysis_job_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="SET NULL"))
    resolved_work_type_code: Mapped[str | None] = mapped_column(String(64))
    analysis_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_analysis_profiles.id", ondelete="SET NULL")
    )
    resolved_analysis_profile_code: Mapped[str | None] = mapped_column(String(64))
    resolved_analysis_profile_version: Mapped[int | None] = mapped_column(Integer)
    reference_photo_id: Mapped[str | None] = mapped_column(ForeignKey("project_photos.id", ondelete="SET NULL"))
    object_type: Mapped[str | None] = mapped_column(String(64))
    surface_condition: Mapped[str | None] = mapped_column(String(64))
    recommended_scope: Mapped[str | None] = mapped_column(String(64))
    estimated_quantity: Mapped[float | None] = mapped_column(Float)
    estimated_unit: Mapped[str | None] = mapped_column(String(32))
    estimated_area_sqm: Mapped[float | None] = mapped_column(Float)
    area_confidence: Mapped[float | None] = mapped_column(Float)
    selected_repair_polygon_json: Mapped[str | None] = mapped_column(Text)
    manual_area_sqm: Mapped[float | None] = mapped_column(Float)
    final_area_source: Mapped[str] = mapped_column(String(32), default="ai", nullable=False)
    mask_polygon_json: Mapped[str | None] = mapped_column(Text)
    materials_suggestion_json: Mapped[str | None] = mapped_column(Text)
    workflow_suggestion_json: Mapped[str | None] = mapped_column(Text)
    estimated_duration_days: Mapped[float | None] = mapped_column(Float)
    labor_hours_total: Mapped[float | None] = mapped_column(Float)
    model_name: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="analysis_results")
    analysis_job: Mapped["AnalysisJob | None"] = relationship(back_populates="analysis_results")
    quote_variants: Mapped[list["QuoteVariant"]] = relationship(back_populates="analysis_result")


class PricingProfile(TimestampMixin, Base):
    __tablename__ = "pricing_profiles"
    __table_args__ = (
        Index(
            "idx_pricing_profiles_org_default_name",
            "organization_id",
            "is_default",
            "name",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    daily_rate: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    labor_hours_per_sqm: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0.3, nullable=False)
    margin_economy_pct: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    margin_standard_pct: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    margin_premium_pct: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    vat_pct: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=21, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CZK", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="pricing_profiles")
    quote_variants: Mapped[list["QuoteVariant"]] = relationship(back_populates="pricing_profile")


class Supplier(TimestampMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        Index(
            "idx_suppliers_org_active_name",
            "organization_id",
            "is_active",
            "name",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64))
    website_url: Mapped[str | None] = mapped_column(String(512))
    integration_type: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_email: Mapped[str | None] = mapped_column(String(255))

    organization: Mapped["Organization"] = relationship(back_populates="suppliers")
    material_catalog_items: Mapped[list["MaterialCatalog"]] = relationship(back_populates="default_supplier")
    supplier_prices: Mapped[list["SupplierMaterialPrice"]] = relationship(back_populates="supplier")
    quote_items: Mapped[list["QuoteItem"]] = relationship(back_populates="supplier")


class MaterialCatalog(TimestampMixin, Base):
    __tablename__ = "material_catalog"
    __table_args__ = (
        Index(
            "idx_material_catalog_org_active_name",
            "organization_id",
            "is_active",
            "name",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64))
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    norm_per_sqm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    default_unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    default_supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    organization: Mapped["Organization"] = relationship(back_populates="material_catalog")
    default_supplier: Mapped["Supplier | None"] = relationship(back_populates="material_catalog_items")
    supplier_prices: Mapped[list["SupplierMaterialPrice"]] = relationship(back_populates="material_catalog")
    quote_items: Mapped[list["QuoteItem"]] = relationship(back_populates="material_catalog")


class SupplierMaterialPrice(TimestampMixin, Base):
    __tablename__ = "supplier_material_prices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    material_catalog_id: Mapped[str] = mapped_column(ForeignKey("material_catalog.id", ondelete="CASCADE"), nullable=False)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    supplier_product_name: Mapped[str | None] = mapped_column(String(255))
    supplier_sku: Mapped[str | None] = mapped_column(String(128))
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CZK", nullable=False)
    availability_status: Mapped[str | None] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(512))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    material_catalog: Mapped["MaterialCatalog"] = relationship(back_populates="supplier_prices")
    supplier: Mapped["Supplier"] = relationship(back_populates="supplier_prices")


class QuoteVariant(TimestampMixin, Base):
    __tablename__ = "quote_variants"
    __table_args__ = (
        Index(
            "idx_quote_variants_project_created_id",
            "project_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    analysis_result_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_results.id", ondelete="SET NULL"))
    pricing_profile_id: Mapped[str | None] = mapped_column(ForeignKey("pricing_profiles.id", ondelete="SET NULL"))
    variant_type: Mapped[str] = mapped_column(String(32), nullable=False)
    labor_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    material_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    other_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    margin_pct: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    total_ex_vat: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    total_inc_vat: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CZK", nullable=False)
    vat_pct: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=21, nullable=False)
    pricing_summary_json: Mapped[str | None] = mapped_column(Text)

    project: Mapped["Project"] = relationship(back_populates="quote_variants")
    analysis_result: Mapped["AnalysisResult | None"] = relationship(back_populates="quote_variants")
    pricing_profile: Mapped["PricingProfile | None"] = relationship(back_populates="quote_variants")
    items: Mapped[list["QuoteItem"]] = relationship(back_populates="quote_variant", cascade="all, delete-orphan")


class QuoteItem(TimestampMixin, Base):
    __tablename__ = "quote_items"
    __table_args__ = (
        Index(
            "idx_quote_items_quote_variant_sort",
            "quote_variant_id",
            "sort_order",
            "id",
        ),
        Index(
            "idx_quote_items_project_work_item",
            "project_work_item_id",
            "sort_order",
            "id",
        ),
        Index(
            "idx_quote_items_pricing_rule_lookup",
            "catalog_pricing_profile_id",
            "catalog_pricing_rule_code",
            "work_type_code",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    quote_variant_id: Mapped[str] = mapped_column(ForeignKey("quote_variants.id", ondelete="CASCADE"), nullable=False)
    project_work_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("project_work_items.id", ondelete="SET NULL")
    )
    catalog_pricing_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_pricing_profiles.id", ondelete="SET NULL")
    )
    work_type_code: Mapped[str | None] = mapped_column(String(64))
    resolved_catalog_pricing_profile_code: Mapped[str | None] = mapped_column(String(64))
    resolved_catalog_pricing_profile_version: Mapped[int | None] = mapped_column(Integer)
    catalog_pricing_rule_code: Mapped[str | None] = mapped_column(String(64))
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    material_catalog_id: Mapped[str | None] = mapped_column(ForeignKey("material_catalog.id", ondelete="SET NULL"))
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))
    price_source: Mapped[str] = mapped_column(String(64), default="company_catalog", nullable=False)
    is_manual_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_suggested_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    supplier_reference_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    company_default_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    sort_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    quote_variant: Mapped["QuoteVariant"] = relationship(back_populates="items")
    material_catalog: Mapped["MaterialCatalog | None"] = relationship(back_populates="quote_items")
    supplier: Mapped["Supplier | None"] = relationship(back_populates="quote_items")


