from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db.base import Base
from app.platform.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.modules.catalog.models import MaterialCatalog, PricingProfile, Supplier

if TYPE_CHECKING:
    from app.modules.cases.models import Project
    from app.modules.identity.models import User


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


