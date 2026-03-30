from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.token_limits import JTI_MAX_LENGTH
from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ico: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    default_currency: Mapped[str] = mapped_column(String(8), default="CZK", nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    clients: Mapped[list["Client"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    projects: Mapped[list["Project"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    pricing_profiles: Mapped[list["PricingProfile"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    material_catalog: Mapped[list["MaterialCatalog"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    suppliers: Mapped[list["Supplier"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tokens_valid_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="users")
    created_projects: Mapped[list["Project"]] = relationship(back_populates="created_by_user")
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(back_populates="requested_by_user")


class Client(TimestampMixin, Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)

    organization: Mapped["Organization"] = relationship(back_populates="clients")
    projects: Mapped[list["Project"]] = relationship(back_populates="client")


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id", ondelete="SET NULL"))
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64), default="draft", nullable=False)
    property_type: Mapped[str | None] = mapped_column(String(64))
    repair_scope: Mapped[str | None] = mapped_column(String(64))
    location_lat: Mapped[float | None] = mapped_column(Float)
    location_lng: Mapped[float | None] = mapped_column(Float)
    address_label: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(32), default="mobile", nullable=False, server_default="mobile")
    reference_expectations_json: Mapped[str | None] = mapped_column(Text)

    organization: Mapped["Organization"] = relationship(back_populates="projects")
    client: Mapped["Client | None"] = relationship(back_populates="projects")
    created_by_user: Mapped["User"] = relationship(back_populates="created_projects")
    photos: Mapped[list["ProjectPhoto"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    quote_variants: Mapped[list["QuoteVariant"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    proposal_draft: Mapped["ProjectProposalDraft | None"] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        uselist=False,
    )
    exports: Mapped[list["ProjectExport"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    final_proposals: Mapped[list["ProjectFinalProposal"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class ProjectPhoto(Base):
    __tablename__ = "project_photos"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'pending_delete', 'deleted')",
            name="ck_project_photos_status",
        ),
        CheckConstraint(
            "processing_status IN ('uploaded', 'processing', 'ready', 'failed')",
            name="ck_project_photos_processing_status",
        ),
        Index("idx_project_photos_project_id", "project_id"),
        Index(
            "idx_project_photos_project_sort_created",
            "project_id",
            "sort_order",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    preview_storage_key: Mapped[str | None] = mapped_column(String(512))
    ai_input_storage_key: Mapped[str | None] = mapped_column(String(512))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    preview_file_size: Mapped[int | None] = mapped_column(Integer)
    preview_width: Mapped[int | None] = mapped_column(Integer)
    preview_height: Mapped[int | None] = mapped_column(Integer)
    ai_input_file_size: Mapped[int | None] = mapped_column(Integer)
    ai_input_width: Mapped[int | None] = mapped_column(Integer)
    ai_input_height: Mapped[int | None] = mapped_column(Integer)
    processing_status: Mapped[str] = mapped_column(String(64), default="ready", nullable=False)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exif_lat: Mapped[float | None] = mapped_column(Float)
    exif_lng: Mapped[float | None] = mapped_column(Float)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_analysis_reference: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="photos")


class ProjectProposalDraft(TimestampMixin, Base):
    __tablename__ = "project_proposal_drafts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    material_cost: Mapped[float | None] = mapped_column(Numeric(14, 4))
    labor_cost: Mapped[float | None] = mapped_column(Numeric(14, 4))
    transport_cost: Mapped[float | None] = mapped_column(Numeric(14, 4))
    amortization: Mapped[float | None] = mapped_column(Numeric(14, 4))
    margin: Mapped[float | None] = mapped_column(Numeric(14, 4))
    recommended_supplier: Mapped[str | None] = mapped_column(String(255))
    recommended_company: Mapped[str | None] = mapped_column(String(255))

    project: Mapped["Project"] = relationship(back_populates="proposal_draft")


class ProjectFinalProposal(TimestampMixin, Base):
    __tablename__ = "project_final_proposals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    draft_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="ready_for_export", nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CZK", nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    total_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="final_proposals")


class ProjectExport(Base):
    __tablename__ = "project_exports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'generating', 'completed', 'failed')",
            name="ck_project_exports_status",
        ),
        Index("idx_project_exports_project_id", "project_id"),
        Index("idx_project_exports_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    export_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="exports")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'canceled')",
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
    requested_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    parent_job_id: Mapped[str | None] = mapped_column(String(64))   # set when this is a retry
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_token: Mapped[str | None] = mapped_column(String(128))
    worker_id: Mapped[str | None] = mapped_column(String(255))
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_traceback: Mapped[str | None] = mapped_column(Text)       # full traceback
    input_payload: Mapped[str | None] = mapped_column(Text)         # JSON: co šlo do AI
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
    reference_photo_id: Mapped[str | None] = mapped_column(ForeignKey("project_photos.id", ondelete="SET NULL"))
    object_type: Mapped[str | None] = mapped_column(String(64))
    surface_condition: Mapped[str | None] = mapped_column(String(64))
    recommended_scope: Mapped[str | None] = mapped_column(String(64))
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
    hourly_rate: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    daily_rate: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    labor_hours_per_sqm: Mapped[float] = mapped_column(Numeric(14, 4), default=0.3, nullable=False)
    margin_economy_pct: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    margin_standard_pct: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    margin_premium_pct: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    vat_pct: Mapped[float] = mapped_column(Numeric(14, 4), default=21, nullable=False)
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
    norm_per_sqm: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    default_unit_price: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
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
    unit_price: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
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

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    analysis_result_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_results.id", ondelete="SET NULL"))
    pricing_profile_id: Mapped[str | None] = mapped_column(ForeignKey("pricing_profiles.id", ondelete="SET NULL"))
    variant_type: Mapped[str] = mapped_column(String(32), nullable=False)
    labor_cost: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    material_cost: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    other_cost: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    margin_pct: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    total_ex_vat: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    vat_amount: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    total_inc_vat: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="quote_variants")
    analysis_result: Mapped["AnalysisResult | None"] = relationship(back_populates="quote_variants")
    pricing_profile: Mapped["PricingProfile | None"] = relationship(back_populates="quote_variants")
    items: Mapped[list["QuoteItem"]] = relationship(back_populates="quote_variant", cascade="all, delete-orphan")


class QuoteItem(TimestampMixin, Base):
    __tablename__ = "quote_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    quote_variant_id: Mapped[str] = mapped_column(ForeignKey("quote_variants.id", ondelete="CASCADE"), nullable=False)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    material_catalog_id: Mapped[str | None] = mapped_column(ForeignKey("material_catalog.id", ondelete="SET NULL"))
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))
    price_source: Mapped[str] = mapped_column(String(64), default="company_catalog", nullable=False)
    is_manual_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_suggested_unit_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    supplier_reference_unit_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    company_default_unit_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    sort_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    quote_variant: Mapped["QuoteVariant"] = relationship(back_populates="items")
    material_catalog: Mapped["MaterialCatalog | None"] = relationship(back_populates="quote_items")
    supplier: Mapped["Supplier | None"] = relationship(back_populates="quote_items")


class RevokedToken(Base):
    """Blocklist for revoked JWT tokens. Checked on every authenticated request."""
    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(JTI_MAX_LENGTH), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RolePermission(Base):
    """DB-backed role → capability mapping for granular RBAC (C8).

    Seeded with defaults on first migration. Superadmin always has all
    capabilities regardless of this table (enforced in deps.py).
    """
    __tablename__ = "role_permissions"

    role: Mapped[str] = mapped_column(String(64), primary_key=True)
    capability: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PasswordResetToken(Base):
    """Single-use token for the email-based password reset flow (C7).

    Created by POST /auth/forgot-password; consumed by POST /auth/reset-password.
    The raw token must never be persisted: the token column stores a SHA-256
    digest, and expired or already-used tokens must never be accepted.
    """
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("ix_password_reset_tokens_expires_at", "expires_at"),
        Index(
            "uq_password_reset_tokens_user_id_unused",
            "user_id",
            unique=True,
            postgresql_where=text("used_at IS NULL"),
            sqlite_where=text("used_at IS NULL"),
        ),
    )

    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship()


class AuditLog(Base):
    """Immutable audit trail — who did what and when."""
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    user_email: Mapped[str | None] = mapped_column(String(255))
    org_id: Mapped[str | None] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
    impersonated_by: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
