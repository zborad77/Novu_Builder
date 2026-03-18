from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    organization: Mapped["Organization"] = relationship(back_populates="projects")
    client: Mapped["Client | None"] = relationship(back_populates="projects")
    created_by_user: Mapped["User"] = relationship(back_populates="created_projects")
    photos: Mapped[list["ProjectPhoto"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    quote_variants: Mapped[list["QuoteVariant"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectPhoto(Base):
    __tablename__ = "project_photos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
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
    sort_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="photos")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="analysis_jobs")
    requested_by_user: Mapped["User | None"] = relationship(back_populates="analysis_jobs")
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(back_populates="analysis_job")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

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
    model_name: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="analysis_results")
    analysis_job: Mapped["AnalysisJob | None"] = relationship(back_populates="analysis_results")
    quote_variants: Mapped[list["QuoteVariant"]] = relationship(back_populates="analysis_result")


class PricingProfile(TimestampMixin, Base):
    __tablename__ = "pricing_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hourly_rate: Mapped[float] = mapped_column(Float, nullable=False)
    daily_rate: Mapped[float] = mapped_column(Float, nullable=False)
    labor_hours_per_sqm: Mapped[float] = mapped_column(Float, default=0.3, nullable=False)
    margin_economy_pct: Mapped[float] = mapped_column(Float, nullable=False)
    margin_standard_pct: Mapped[float] = mapped_column(Float, nullable=False)
    margin_premium_pct: Mapped[float] = mapped_column(Float, nullable=False)
    vat_pct: Mapped[float] = mapped_column(Float, default=21, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CZK", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="pricing_profiles")
    quote_variants: Mapped[list["QuoteVariant"]] = relationship(back_populates="pricing_profile")


class Supplier(TimestampMixin, Base):
    __tablename__ = "suppliers"

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

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64))
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    norm_per_sqm: Mapped[float] = mapped_column(Float, nullable=False)
    default_unit_price: Mapped[float] = mapped_column(Float, nullable=False)
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
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
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
    labor_cost: Mapped[float] = mapped_column(Float, nullable=False)
    material_cost: Mapped[float] = mapped_column(Float, nullable=False)
    other_cost: Mapped[float] = mapped_column(Float, nullable=False)
    margin_pct: Mapped[float] = mapped_column(Float, nullable=False)
    total_ex_vat: Mapped[float] = mapped_column(Float, nullable=False)
    vat_amount: Mapped[float] = mapped_column(Float, nullable=False)
    total_inc_vat: Mapped[float] = mapped_column(Float, nullable=False)

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
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    material_catalog_id: Mapped[str | None] = mapped_column(ForeignKey("material_catalog.id", ondelete="SET NULL"))
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))
    price_source: Mapped[str] = mapped_column(String(64), default="company_catalog", nullable=False)
    is_manual_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_suggested_unit_price: Mapped[float | None] = mapped_column(Float)
    supplier_reference_unit_price: Mapped[float | None] = mapped_column(Float)
    company_default_unit_price: Mapped[float | None] = mapped_column(Float)
    sort_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    quote_variant: Mapped["QuoteVariant"] = relationship(back_populates="items")
    material_catalog: Mapped["MaterialCatalog | None"] = relationship(back_populates="quote_items")
    supplier: Mapped["Supplier | None"] = relationship(back_populates="quote_items")
