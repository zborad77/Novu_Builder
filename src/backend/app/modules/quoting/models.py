"""ORM modely modulu quoting: varianty nabídky, položky, draft a finální návrh."""

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db.base import Base
from app.platform.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.modules.analysis.public import AnalysisResult
    from app.modules.catalog.public import MaterialCatalog, PricingProfile, Supplier
    from app.modules.cases.public import Project


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
    currency: Mapped[str] = mapped_column(String(8), default="CZK", nullable=False, server_default=text("'CZK'"))
    vat_pct: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=21, nullable=False, server_default=text("'21'"))
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


class ProjectProposalDraft(TimestampMixin, Base):
    __tablename__ = "project_proposal_drafts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False, server_default=text("1"))
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
    status: Mapped[str] = mapped_column(String(64), default="ready_for_export", nullable=False, server_default=text("'ready_for_export'"))
    currency: Mapped[str] = mapped_column(String(8), default="CZK", nullable=False, server_default=text("'CZK'"))
    subject: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="final_proposals")


# N9: indexy, které vytvářejí migrace (produkční schéma), deklarované i v ORM,
# aby create_all (testy, dev) a autogenerate odpovídaly migracím.
Index("idx_project_final_proposals_analysis_result_id", ProjectFinalProposal.analysis_result_id)
