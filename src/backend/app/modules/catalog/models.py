"""ORM modely modulu catalog: cenové profily tenanta, dodavatelé a katalog materiálů."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db.base import Base
from app.platform.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.modules.quoting.public import QuoteItem, QuoteVariant
    from app.modules.identity.public import Organization


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
