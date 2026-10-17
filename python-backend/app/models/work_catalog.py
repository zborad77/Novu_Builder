from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.domain import TimestampMixin


class WorkCategory(TimestampMixin, Base):
    """Global source-of-truth category taxonomy for work types."""
    __tablename__ = "work_categories"
    __table_args__ = (
        UniqueConstraint("code", name="uq_work_categories_code"),
        UniqueConstraint("slug", name="uq_work_categories_slug"),
        Index("idx_work_categories_active_sort", "is_active", "sort_order", "code"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_cs: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    catalog_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    work_types: Mapped[list["WorkType"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
        order_by="WorkType.sort_order",
    )


class AnalysisProfile(TimestampMixin, Base):
    """Immutable-ish global analysis execution contract referenced by work types."""
    __tablename__ = "catalog_analysis_profiles"
    __table_args__ = (
        UniqueConstraint("code", "profile_version", name="uq_catalog_analysis_profiles_code_version"),
        Index("idx_catalog_analysis_profiles_active_code", "is_active", "code", "profile_version"),
        CheckConstraint(
            "task_type IN ('classification', 'detection', 'measurement', 'hybrid')",
            name="ck_catalog_analysis_profiles_task_type",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'deprecated', 'archived')",
            name="ck_catalog_analysis_profiles_status",
        ),
        CheckConstraint(
            "fallback_mode IN ('manual_review', 'request_more_photos', 'return_partial')",
            name="ck_catalog_analysis_profiles_fallback_mode",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_family: Mapped[str] = mapped_column(String(64), nullable=False)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    output_contract_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    confidence_threshold: Mapped[float | None] = mapped_column(Numeric(8, 4))
    max_detections_per_photo: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    scope_code: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_label: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_description: Mapped[str | None] = mapped_column(Text)
    fallback_mode: Mapped[str] = mapped_column(String(32), default="manual_review", nullable=False)
    fallback_instructions: Mapped[str | None] = mapped_column(Text)
    fallback_requires_manual_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    work_types: Mapped[list["WorkType"]] = relationship(
        back_populates="default_analysis_profile",
        foreign_keys="WorkType.default_analysis_profile_id",
    )
    tenant_settings: Mapped[list["TenantWorkTypeSetting"]] = relationship(
        back_populates="analysis_profile",
        foreign_keys="TenantWorkTypeSetting.analysis_profile_id",
    )
    target_objects: Mapped[list["AnalysisProfileTargetObject"]] = relationship(
        back_populates="analysis_profile",
        cascade="all, delete-orphan",
        order_by="AnalysisProfileTargetObject.sort_order",
    )
    ignored_objects: Mapped[list["AnalysisProfileIgnoredObject"]] = relationship(
        back_populates="analysis_profile",
        cascade="all, delete-orphan",
        order_by="AnalysisProfileIgnoredObject.sort_order",
    )
    extraction_rules: Mapped[list["AnalysisProfileExtractionRule"]] = relationship(
        back_populates="analysis_profile",
        cascade="all, delete-orphan",
        order_by="AnalysisProfileExtractionRule.sort_order",
    )
    validation_rules: Mapped[list["AnalysisProfileValidationRule"]] = relationship(
        back_populates="analysis_profile",
        cascade="all, delete-orphan",
        order_by="AnalysisProfileValidationRule.sort_order",
    )
    confidence_thresholds: Mapped[list["AnalysisProfileConfidenceThreshold"]] = relationship(
        back_populates="analysis_profile",
        cascade="all, delete-orphan",
        order_by="AnalysisProfileConfidenceThreshold.sort_order",
    )
    output_mappings: Mapped[list["AnalysisProfileOutputMapping"]] = relationship(
        back_populates="analysis_profile",
        cascade="all, delete-orphan",
        order_by="AnalysisProfileOutputMapping.sort_order",
    )


class AnalysisProfileTargetObject(TimestampMixin, Base):
    __tablename__ = "catalog_analysis_profile_target_objects"
    __table_args__ = (
        UniqueConstraint("analysis_profile_id", "code", name="uq_analysis_profile_target_objects_code"),
        Index("idx_analysis_profile_target_objects_profile_sort", "analysis_profile_id", "sort_order", "code"),
        CheckConstraint(
            "object_role IN ('primary', 'secondary', 'context')",
            name="ck_analysis_profile_target_objects_role",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    analysis_profile_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_analysis_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    object_role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    analysis_profile: Mapped["AnalysisProfile"] = relationship(back_populates="target_objects")


class AnalysisProfileIgnoredObject(TimestampMixin, Base):
    __tablename__ = "catalog_analysis_profile_ignored_objects"
    __table_args__ = (
        UniqueConstraint("analysis_profile_id", "code", name="uq_analysis_profile_ignored_objects_code"),
        Index("idx_analysis_profile_ignored_objects_profile_sort", "analysis_profile_id", "sort_order", "code"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    analysis_profile_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_analysis_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    analysis_profile: Mapped["AnalysisProfile"] = relationship(back_populates="ignored_objects")


class AnalysisProfileExtractionRule(TimestampMixin, Base):
    __tablename__ = "catalog_analysis_profile_extraction_rules"
    __table_args__ = (
        UniqueConstraint("analysis_profile_id", "attribute_code", name="uq_analysis_profile_extraction_rules_attribute"),
        Index("idx_analysis_profile_extraction_rules_profile_sort", "analysis_profile_id", "sort_order", "attribute_code"),
        CheckConstraint(
            "data_type IN ('number', 'text', 'boolean', 'option')",
            name="ck_analysis_profile_extraction_rules_data_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    analysis_profile_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_analysis_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    attribute_code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    target_parameter_code: Mapped[str] = mapped_column(String(64), nullable=False)
    source_object_code: Mapped[str] = mapped_column(String(64), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    manual_review_on_missing: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    analysis_profile: Mapped["AnalysisProfile"] = relationship(back_populates="extraction_rules")


class AnalysisProfileValidationRule(TimestampMixin, Base):
    __tablename__ = "catalog_analysis_profile_validation_rules"
    __table_args__ = (
        UniqueConstraint("analysis_profile_id", "code", name="uq_analysis_profile_validation_rules_code"),
        Index("idx_analysis_profile_validation_rules_profile_sort", "analysis_profile_id", "sort_order", "code"),
        CheckConstraint(
            "rule_type IN ('min_photos', 'required_attribute', 'numeric_range', 'confidence_gate')",
            name="ck_analysis_profile_validation_rules_type",
        ),
        CheckConstraint(
            "severity IN ('warning', 'blocking')",
            name="ck_analysis_profile_validation_rules_severity",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    analysis_profile_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_analysis_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    target_attribute_code: Mapped[str | None] = mapped_column(String(64))
    target_parameter_code: Mapped[str | None] = mapped_column(String(64))
    min_number_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    max_number_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    analysis_profile: Mapped["AnalysisProfile"] = relationship(back_populates="validation_rules")


class AnalysisProfileConfidenceThreshold(TimestampMixin, Base):
    __tablename__ = "catalog_analysis_profile_confidence_thresholds"
    __table_args__ = (
        UniqueConstraint("analysis_profile_id", "attribute_code", name="uq_analysis_profile_confidence_thresholds_attribute"),
        Index("idx_analysis_profile_confidence_thresholds_profile_sort", "analysis_profile_id", "sort_order", "attribute_code"),
        CheckConstraint(
            "action_below_threshold IN ('manual_review', 'drop_attribute', 'fail_analysis')",
            name="ck_analysis_profile_confidence_thresholds_action",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    analysis_profile_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_analysis_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    attribute_code: Mapped[str] = mapped_column(String(64), nullable=False)
    target_object_code: Mapped[str | None] = mapped_column(String(64))
    min_confidence: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    preferred_confidence: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    action_below_threshold: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    analysis_profile: Mapped["AnalysisProfile"] = relationship(back_populates="confidence_thresholds")


class AnalysisProfileOutputMapping(TimestampMixin, Base):
    __tablename__ = "catalog_analysis_profile_output_mappings"
    __table_args__ = (
        UniqueConstraint("analysis_profile_id", "code", name="uq_analysis_profile_output_mappings_code"),
        Index("idx_analysis_profile_output_mappings_profile_sort", "analysis_profile_id", "sort_order", "code"),
        CheckConstraint(
            "target_entity IN ('analysis_result', 'project_work_item', 'project_work_item_value', 'vision_detection')",
            name="ck_analysis_profile_output_mappings_target_entity",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    analysis_profile_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_analysis_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    target_entity: Mapped[str] = mapped_column(String(32), nullable=False)
    target_field: Mapped[str] = mapped_column(String(64), nullable=False)
    source_attribute_code: Mapped[str] = mapped_column(String(64), nullable=False)
    target_parameter_code: Mapped[str | None] = mapped_column(String(64))
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    analysis_profile: Mapped["AnalysisProfile"] = relationship(back_populates="output_mappings")


class CatalogPricingProfile(TimestampMixin, Base):
    """Global pricing strategy profile, distinct from tenant pricebooks."""
    __tablename__ = "catalog_pricing_profiles"
    __table_args__ = (
        UniqueConstraint("code", "profile_version", name="uq_catalog_pricing_profiles_code_version"),
        Index("idx_catalog_pricing_profiles_active_code", "is_active", "code", "profile_version"),
        CheckConstraint(
            "status IN ('draft', 'active', 'deprecated', 'archived')",
            name="ck_catalog_pricing_profiles_status",
        ),
        CheckConstraint(
            "pricing_basis IN ('area', 'length', 'count', 'volume', 'scope', 'inspection', 'service', 'incident')",
            name="ck_catalog_pricing_profiles_basis",
        ),
        CheckConstraint(
            "pricing_strategy IN ('tenant_pricebook', 'catalog_formula', 'fixed_formula', 'manual_review')",
            name="ck_catalog_pricing_profiles_strategy",
        ),
        CheckConstraint(
            "labor_rate_source IN ('tenant_default', 'catalog_default', 'manual')",
            name="ck_catalog_pricing_profiles_labor_rate_source",
        ),
        CheckConstraint(
            "material_pricing_source IN ('tenant_pricebook', 'catalog_default', 'manual')",
            name="ck_catalog_pricing_profiles_material_pricing_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    pricing_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CZK", nullable=False)
    pricing_strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    labor_rate_source: Mapped[str] = mapped_column(String(32), nullable=False)
    material_pricing_source: Mapped[str] = mapped_column(String(32), nullable=False)
    default_margin_pct: Mapped[float | None] = mapped_column(Numeric(14, 4))
    default_markup_pct: Mapped[float | None] = mapped_column(Numeric(14, 4))
    min_job_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    metadata_json: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    work_types: Mapped[list["WorkType"]] = relationship(
        back_populates="default_catalog_pricing_profile",
        foreign_keys="WorkType.default_catalog_pricing_profile_id",
    )
    tenant_settings: Mapped[list["TenantWorkTypeSetting"]] = relationship(
        back_populates="catalog_pricing_profile",
        foreign_keys="TenantWorkTypeSetting.catalog_pricing_profile_id",
    )
    required_inputs: Mapped[list["CatalogPricingProfileRequiredInput"]] = relationship(
        back_populates="catalog_pricing_profile",
        cascade="all, delete-orphan",
        order_by="CatalogPricingProfileRequiredInput.sort_order",
    )
    base_rules: Mapped[list["CatalogPricingProfileBaseRule"]] = relationship(
        back_populates="catalog_pricing_profile",
        cascade="all, delete-orphan",
        order_by="CatalogPricingProfileBaseRule.sort_order",
    )
    adjustment_rules: Mapped[list["CatalogPricingProfileAdjustmentRule"]] = relationship(
        back_populates="catalog_pricing_profile",
        cascade="all, delete-orphan",
        order_by="CatalogPricingProfileAdjustmentRule.sort_order",
    )
    labor_assumptions: Mapped[list["CatalogPricingProfileLaborAssumption"]] = relationship(
        back_populates="catalog_pricing_profile",
        cascade="all, delete-orphan",
        order_by="CatalogPricingProfileLaborAssumption.sort_order",
    )
    material_assumptions: Mapped[list["CatalogPricingProfileMaterialAssumption"]] = relationship(
        back_populates="catalog_pricing_profile",
        cascade="all, delete-orphan",
        order_by="CatalogPricingProfileMaterialAssumption.sort_order",
    )


class CatalogPricingProfileRequiredInput(TimestampMixin, Base):
    __tablename__ = "catalog_pricing_profile_required_inputs"
    __table_args__ = (
        UniqueConstraint("catalog_pricing_profile_id", "code", name="uq_catalog_pricing_profile_required_inputs_code"),
        Index(
            "idx_catalog_pricing_profile_required_inputs_profile_sort",
            "catalog_pricing_profile_id",
            "sort_order",
            "code",
        ),
        CheckConstraint(
            "source_type IN ('parameter', 'work_item_field')",
            name="ck_catalog_pricing_profile_required_inputs_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    catalog_pricing_profile_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_pricing_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    catalog_pricing_profile: Mapped["CatalogPricingProfile"] = relationship(back_populates="required_inputs")


class CatalogPricingProfileLaborAssumption(TimestampMixin, Base):
    __tablename__ = "catalog_pricing_profile_labor_assumptions"
    __table_args__ = (
        UniqueConstraint("catalog_pricing_profile_id", "code", name="uq_catalog_pricing_profile_labor_assumptions_code"),
        Index(
            "idx_catalog_pricing_profile_labor_assumptions_profile_sort",
            "catalog_pricing_profile_id",
            "sort_order",
            "code",
        ),
        CheckConstraint(
            "quantity_source_type IN ('parameter', 'work_item_field', 'constant')",
            name="ck_catalog_pricing_profile_labor_assumptions_quantity_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    catalog_pricing_profile_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_pricing_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    quantity_source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity_source_key: Mapped[str | None] = mapped_column(String(64))
    hours_per_unit: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    crew_size: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    catalog_pricing_profile: Mapped["CatalogPricingProfile"] = relationship(back_populates="labor_assumptions")


class CatalogPricingProfileMaterialAssumption(TimestampMixin, Base):
    __tablename__ = "catalog_pricing_profile_material_assumptions"
    __table_args__ = (
        UniqueConstraint("catalog_pricing_profile_id", "code", name="uq_catalog_pricing_profile_material_assumptions_code"),
        Index(
            "idx_catalog_pricing_profile_material_assumptions_profile_sort",
            "catalog_pricing_profile_id",
            "sort_order",
            "code",
        ),
        CheckConstraint(
            "quantity_source_type IN ('parameter', 'work_item_field', 'constant')",
            name="ck_catalog_pricing_profile_material_assumptions_quantity_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    catalog_pricing_profile_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_pricing_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    quantity_source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity_source_key: Mapped[str | None] = mapped_column(String(64))
    quantity_per_unit: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    default_unit_cost: Mapped[float | None] = mapped_column(Numeric(14, 4))
    waste_factor_pct: Mapped[float | None] = mapped_column(Numeric(14, 4))
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    catalog_pricing_profile: Mapped["CatalogPricingProfile"] = relationship(back_populates="material_assumptions")


class CatalogPricingProfileBaseRule(TimestampMixin, Base):
    __tablename__ = "catalog_pricing_profile_base_rules"
    __table_args__ = (
        UniqueConstraint("catalog_pricing_profile_id", "code", name="uq_catalog_pricing_profile_base_rules_code"),
        Index(
            "idx_catalog_pricing_profile_base_rules_profile_sort",
            "catalog_pricing_profile_id",
            "sort_order",
            "code",
        ),
        CheckConstraint(
            "line_type IN ('labor', 'material', 'other')",
            name="ck_catalog_pricing_profile_base_rules_line_type",
        ),
        CheckConstraint(
            "calculation_method IN ('per_unit', 'fixed')",
            name="ck_catalog_pricing_profile_base_rules_calculation_method",
        ),
        CheckConstraint(
            "quantity_source_type IN ('parameter', 'work_item_field', 'constant')",
            name="ck_catalog_pricing_profile_base_rules_quantity_source",
        ),
        CheckConstraint(
            "rate_source IN ('tenant_hourly_rate', 'tenant_daily_rate', 'catalog_unit_rate', 'catalog_flat_rate')",
            name="ck_catalog_pricing_profile_base_rules_rate_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    catalog_pricing_profile_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_pricing_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    line_type: Mapped[str] = mapped_column(String(32), nullable=False)
    calculation_method: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity_source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity_source_key: Mapped[str | None] = mapped_column(String(64))
    quantity_multiplier: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    rate_source: Mapped[str] = mapped_column(String(32), nullable=False)
    rate_value: Mapped[float | None] = mapped_column(Numeric(14, 4))
    labor_assumption_code: Mapped[str | None] = mapped_column(String(64))
    material_assumption_code: Mapped[str | None] = mapped_column(String(64))
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    catalog_pricing_profile: Mapped["CatalogPricingProfile"] = relationship(back_populates="base_rules")


class CatalogPricingProfileAdjustmentRule(TimestampMixin, Base):
    __tablename__ = "catalog_pricing_profile_adjustment_rules"
    __table_args__ = (
        UniqueConstraint("catalog_pricing_profile_id", "code", name="uq_catalog_pricing_profile_adjustment_rules_code"),
        Index(
            "idx_catalog_pricing_profile_adjustment_rules_profile_sort",
            "catalog_pricing_profile_id",
            "sort_order",
            "code",
        ),
        CheckConstraint(
            "target_scope IN ('profile_total', 'line_type', 'base_rule')",
            name="ck_catalog_pricing_profile_adjustment_rules_target_scope",
        ),
        CheckConstraint(
            "target_line_type IS NULL OR target_line_type IN ('labor', 'material', 'other')",
            name="ck_catalog_pricing_profile_adjustment_rules_target_line_type",
        ),
        CheckConstraint(
            "operation IN ('multiply', 'add_flat')",
            name="ck_catalog_pricing_profile_adjustment_rules_operation",
        ),
        CheckConstraint(
            "condition_source_type IN ('parameter', 'work_item_field')",
            name="ck_catalog_pricing_profile_adjustment_rules_condition_source",
        ),
        CheckConstraint(
            "condition_operator IN ('eq', 'gte', 'lte', 'true')",
            name="ck_catalog_pricing_profile_adjustment_rules_operator",
        ),
        CheckConstraint(
            "(CASE WHEN condition_text_value IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN condition_number_value IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN condition_boolean_value IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN condition_option_code IS NOT NULL THEN 1 ELSE 0 END) <= 1",
            # Deliberately shorter than the sibling constraints on this table: the
            # full ck_catalog_pricing_profile_adjustment_rules_* form would be 66
            # characters and PostgreSQL rejects identifiers over 63. Migration 0033
            # already creates it under this short name, so the database matches.
            name="ck_pricing_adj_rules_single_condition_value",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    catalog_pricing_profile_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_pricing_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    target_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    target_line_type: Mapped[str | None] = mapped_column(String(32))
    target_base_rule_code: Mapped[str | None] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    adjustment_value: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    condition_source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    condition_source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    condition_operator: Mapped[str] = mapped_column(String(32), nullable=False)
    condition_text_value: Mapped[str | None] = mapped_column(Text)
    condition_number_value: Mapped[float | None] = mapped_column(Numeric(14, 4))
    condition_boolean_value: Mapped[bool | None] = mapped_column(Boolean)
    condition_option_code: Mapped[str | None] = mapped_column(String(64))
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    catalog_pricing_profile: Mapped["CatalogPricingProfile"] = relationship(back_populates="adjustment_rules")


class WorkType(TimestampMixin, Base):
    """Global work type definition resolved into tenant-effective and runtime rows.

    Extended fields
    ---------------
    kind                      — 'leaf' = standalone type, 'composite' = assembles from components
    proposal_step             — true when AI returns a proposal that requires explicit approval
                                before the final detailed solution is generated (e.g. FVE layout)
    geometry_correction_type  — how raw measured area/length is corrected before pricing:
                                'none' | 'slope_coefficient' | 'net_from_gross' |
                                'pipe_length_from_drawing' | 'volume_from_depth'
    output_types_json         — JSON array of what the analysis produces:
                                'material_list' | 'work_procedure' | 'overlay' |
                                'generated_diagram' | 'calculation'
    """
    __tablename__ = "work_types"
    __table_args__ = (
        UniqueConstraint("code", name="uq_work_types_code"),
        UniqueConstraint("slug", name="uq_work_types_slug"),
        Index("idx_work_types_catalog_sort", "sort_order", "code"),
        Index("idx_work_types_category_state_sort", "category_id", "state", "sort_order", "code"),
        Index("idx_work_types_kind_state", "kind", "state", "code"),
        Index(
            "idx_work_types_analysis_profile_resolution",
            "default_analysis_profile_id",
            "state",
            "code",
        ),
        Index(
            "idx_work_types_pricing_profile_resolution",
            "default_catalog_pricing_profile_id",
            "state",
            "code",
        ),
        CheckConstraint("state IN ('active', 'hidden', 'deprecated')", name="ck_work_types_state"),
        CheckConstraint("kind IN ('leaf', 'composite')", name="ck_work_types_kind"),
        CheckConstraint(
            "geometry_correction_type IN ("
            "'none', 'slope_coefficient', 'net_from_gross', "
            "'pipe_length_from_drawing', 'volume_from_depth')",
            name="ck_work_types_geometry_correction_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("work_categories.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_cs: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    default_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    measurement_kind: Mapped[str] = mapped_column(String(32), default="area", nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="leaf", nullable=False)
    proposal_step: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    geometry_correction_type: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    output_types_json: Mapped[str | None] = mapped_column(Text)
    default_analysis_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_analysis_profiles.id", ondelete="SET NULL")
    )
    default_catalog_pricing_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_pricing_profiles.id", ondelete="SET NULL")
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    catalog_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    category: Mapped["WorkCategory"] = relationship(back_populates="work_types")
    default_analysis_profile: Mapped["AnalysisProfile | None"] = relationship(
        back_populates="work_types",
        foreign_keys=[default_analysis_profile_id],
    )
    default_catalog_pricing_profile: Mapped["CatalogPricingProfile | None"] = relationship(
        back_populates="work_types",
        foreign_keys=[default_catalog_pricing_profile_id],
    )
    parameters: Mapped[list["WorkTypeParameter"]] = relationship(
        back_populates="work_type",
        cascade="all, delete-orphan",
        order_by="WorkTypeParameter.sort_order",
    )
    components: Mapped[list["WorkTypeComponent"]] = relationship(
        back_populates="parent_work_type",
        foreign_keys="WorkTypeComponent.parent_work_type_id",
        cascade="all, delete-orphan",
        order_by="WorkTypeComponent.sort_order",
    )
    tenant_settings: Mapped[list["TenantWorkTypeSetting"]] = relationship(
        back_populates="work_type",
        cascade="all, delete-orphan",
    )
    parameter_overrides: Mapped[list["TenantWorkTypeParameterOverride"]] = relationship(
        back_populates="work_type",
        cascade="all, delete-orphan",
    )


class WorkTypeParameter(TimestampMixin, Base):
    """Typed schema field for a work type; used as the basis for runtime validation.

    Extended fields
    ---------------
    section               — logical group for UI rendering and section-scoped filtering
                            (dimensions | materials | condition_or_damage |
                             access_and_complexity | quantity_scope | optional_notes)
    min_number_value      — inclusive lower bound enforced at write time for number params
    max_number_value      — inclusive upper bound enforced at write time for number params
    vision_extractable    — true when AI vision can auto-populate this field
    manual_override_allowed — false locks the field to system-only writes
    """
    __tablename__ = "work_type_parameters"
    __table_args__ = (
        UniqueConstraint("work_type_id", "code", name="uq_work_type_parameters_work_type_code"),
        UniqueConstraint("work_type_id", "slug", name="uq_work_type_parameters_work_type_slug"),
        Index("idx_work_type_parameters_work_type_sort", "work_type_id", "sort_order", "code"),
        Index("idx_work_type_parameters_section_sort", "work_type_id", "section", "sort_order"),
        CheckConstraint(
            "data_type IN ('number', 'text', 'boolean', 'option')",
            name="ck_work_type_parameters_data_type",
        ),
        CheckConstraint(
            "section IS NULL OR section IN ("
            "'dimensions', 'materials', 'condition_or_damage', "
            "'access_and_complexity', 'quantity_scope', 'optional_notes')",
            name="ck_work_type_parameters_section",
        ),
        CheckConstraint(
            "min_number_value IS NULL OR max_number_value IS NULL OR min_number_value <= max_number_value",
            name="ck_work_type_parameters_number_bounds_order",
        ),
        CheckConstraint(
            "(CASE WHEN default_text_value IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN default_number_value IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN default_boolean_value IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN default_option_code IS NOT NULL THEN 1 ELSE 0 END) <= 1",
            name="ck_work_type_parameters_single_default_value",
        ),
        CheckConstraint(
            "data_type = 'text' OR default_text_value IS NULL",
            name="ck_work_type_parameters_default_text_type",
        ),
        CheckConstraint(
            "data_type = 'number' OR (default_number_value IS NULL AND min_number_value IS NULL AND max_number_value IS NULL)",
            name="ck_work_type_parameters_default_number_type",
        ),
        CheckConstraint(
            "data_type = 'boolean' OR default_boolean_value IS NULL",
            name="ck_work_type_parameters_default_boolean_type",
        ),
        CheckConstraint(
            "data_type = 'option' OR default_option_code IS NULL",
            name="ck_work_type_parameters_default_option_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    work_type_id: Mapped[str] = mapped_column(ForeignKey("work_types.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    section: Mapped[str | None] = mapped_column(String(64))
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    min_number_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    max_number_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    vision_extractable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    manual_override_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_text_value: Mapped[str | None] = mapped_column(Text)
    default_number_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    default_boolean_value: Mapped[bool | None] = mapped_column(Boolean)
    default_option_code: Mapped[str | None] = mapped_column(String(64))

    work_type: Mapped["WorkType"] = relationship(back_populates="parameters")
    options: Mapped[list["WorkTypeParameterOption"]] = relationship(
        back_populates="parameter",
        cascade="all, delete-orphan",
        order_by="WorkTypeParameterOption.sort_order",
    )
    tenant_overrides: Mapped[list["TenantWorkTypeParameterOverride"]] = relationship(
        back_populates="parameter",
        cascade="all, delete-orphan",
    )


class WorkTypeParameterOption(TimestampMixin, Base):
    """Allowed option values for option-type work type parameters."""
    __tablename__ = "work_type_parameter_options"
    __table_args__ = (
        UniqueConstraint("work_type_parameter_id", "code", name="uq_work_type_parameter_options_param_code"),
        Index("idx_work_type_parameter_options_param_sort", "work_type_parameter_id", "sort_order", "code"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    work_type_parameter_id: Mapped[str] = mapped_column(
        ForeignKey("work_type_parameters.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    parameter: Mapped["WorkTypeParameter"] = relationship(back_populates="options")


class WorkTypeComponent(TimestampMixin, Base):
    """Links a composite WorkType to its constituent leaf WorkTypes.

    A composite type (e.g. 'rekonstrukce_strechy') assembles multiple leaf types
    (demontaz_krytiny, oprava_krovu, montaz_lati, pokladka_krytiny, ...).
    AI Vision detects which components are needed based on photos and parameters;
    each component is then priced and planned independently.

    condition_code
    --------------
    'always'        — always included when composite is selected
    'if_detected'   — included only when AI Vision detects the need
    'tenant_choice' — included if tenant has enabled it in their settings
    """
    __tablename__ = "work_type_components"
    __table_args__ = (
        UniqueConstraint(
            "parent_work_type_id",
            "component_work_type_id",
            name="uq_work_type_components_parent_component",
        ),
        Index("idx_work_type_components_parent_sort", "parent_work_type_id", "sort_order", "component_work_type_id"),
        Index("idx_work_type_components_component", "component_work_type_id"),
        CheckConstraint(
            "condition_code IN ('always', 'if_detected', 'tenant_choice')",
            name="ck_work_type_components_condition_code",
        ),
        CheckConstraint(
            "parent_work_type_id != component_work_type_id",
            name="ck_work_type_components_no_self_reference",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parent_work_type_id: Mapped[str] = mapped_column(
        ForeignKey("work_types.id", ondelete="CASCADE"),
        nullable=False,
    )
    component_work_type_id: Mapped[str] = mapped_column(
        ForeignKey("work_types.id", ondelete="RESTRICT"),
        nullable=False,
    )
    condition_code: Mapped[str] = mapped_column(String(32), default="always", nullable=False)
    quantity_multiplier: Mapped[float] = mapped_column(Numeric(14, 4), default=1.0, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    parent_work_type: Mapped["WorkType"] = relationship(
        back_populates="components",
        foreign_keys=[parent_work_type_id],
    )
    component_work_type: Mapped["WorkType"] = relationship(
        foreign_keys=[component_work_type_id],
    )


class TenantWorkTypeSetting(TimestampMixin, Base):
    """Sparse per-tenant override row for a global work type definition."""
    __tablename__ = "tenant_work_type_settings"
    __table_args__ = (
        UniqueConstraint("organization_id", "work_type_id", name="uq_tenant_work_type_settings_org_work_type"),
        Index("idx_tenant_work_type_settings_org_status", "organization_id", "status", "work_type_id"),
        Index(
            "idx_tenant_work_type_settings_profile_resolution",
            "organization_id",
            "analysis_profile_id",
            "catalog_pricing_profile_id",
            "work_type_id",
        ),
        CheckConstraint(
            "status IN ('inherited', 'enabled', 'disabled')",
            name="ck_tenant_work_type_settings_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    work_type_id: Mapped[str] = mapped_column(ForeignKey("work_types.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="inherited", nullable=False)
    custom_display_name: Mapped[str | None] = mapped_column(String(255))
    analysis_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_analysis_profiles.id", ondelete="SET NULL")
    )
    catalog_pricing_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_pricing_profiles.id", ondelete="SET NULL")
    )
    tenant_pricing_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("pricing_profiles.id", ondelete="SET NULL")
    )
    is_billable_override: Mapped[bool | None] = mapped_column(Boolean)
    sort_order_override: Mapped[int | None] = mapped_column(Integer)
    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    work_type: Mapped["WorkType"] = relationship(back_populates="tenant_settings")
    analysis_profile: Mapped["AnalysisProfile | None"] = relationship(
        back_populates="tenant_settings",
        foreign_keys=[analysis_profile_id],
    )
    catalog_pricing_profile: Mapped["CatalogPricingProfile | None"] = relationship(
        back_populates="tenant_settings",
        foreign_keys=[catalog_pricing_profile_id],
    )
    parameter_overrides: Mapped[list["TenantWorkTypeParameterOverride"]] = relationship(
        back_populates="tenant_work_type_setting",
        cascade="all, delete-orphan",
        order_by="TenantWorkTypeParameterOverride.sort_order_override",
    )
    extra_parameters: Mapped[list["TenantWorkTypeExtraParameter"]] = relationship(
        back_populates="tenant_work_type_setting",
        cascade="all, delete-orphan",
        order_by="TenantWorkTypeExtraParameter.sort_order",
    )


class TenantWorkTypeParameterOverride(TimestampMixin, Base):
    """Sparse per-tenant parameter delta without copying the global parameter schema."""
    __tablename__ = "tenant_work_type_parameter_overrides"
    __table_args__ = (
        UniqueConstraint(
            "tenant_work_type_setting_id",
            "work_type_parameter_id",
            name="uq_tenant_parameter_overrides_setting_parameter",
        ),
        UniqueConstraint(
            "organization_id",
            "work_type_parameter_id",
            name="uq_tenant_parameter_overrides_org_parameter",
        ),
        Index(
            "idx_tenant_parameter_overrides_org_work_type",
            "organization_id",
            "work_type_id",
            "override_status",
            "sort_order_override",
        ),
        Index(
            "idx_tenant_parameter_overrides_setting_lookup",
            "tenant_work_type_setting_id",
            "work_type_parameter_id",
        ),
        CheckConstraint(
            "override_status IN ('inherited', 'required', 'optional', 'hidden')",
            name="ck_tenant_parameter_overrides_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_work_type_setting_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_work_type_settings.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    work_type_id: Mapped[str] = mapped_column(ForeignKey("work_types.id", ondelete="CASCADE"), nullable=False)
    work_type_parameter_id: Mapped[str] = mapped_column(
        ForeignKey("work_type_parameters.id", ondelete="CASCADE"),
        nullable=False,
    )
    override_status: Mapped[str] = mapped_column(String(32), default="inherited", nullable=False)
    custom_display_name: Mapped[str | None] = mapped_column(String(255))
    sort_order_override: Mapped[int | None] = mapped_column(Integer)
    default_text_value: Mapped[str | None] = mapped_column(Text)
    default_number_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    default_boolean_value: Mapped[bool | None] = mapped_column(Boolean)
    default_option_code: Mapped[str | None] = mapped_column(String(64))
    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    tenant_work_type_setting: Mapped["TenantWorkTypeSetting"] = relationship(back_populates="parameter_overrides")
    work_type: Mapped["WorkType"] = relationship(back_populates="parameter_overrides")
    parameter: Mapped["WorkTypeParameter"] = relationship(back_populates="tenant_overrides")


class TenantWorkTypeExtraParameter(TimestampMixin, Base):
    """Tenant-controlled extension parameter layered on top of the global work type."""
    __tablename__ = "tenant_work_type_extra_parameters"
    __table_args__ = (
        UniqueConstraint(
            "tenant_work_type_setting_id",
            "code",
            name="uq_tenant_extra_parameters_setting_code",
        ),
        UniqueConstraint(
            "tenant_work_type_setting_id",
            "slug",
            name="uq_tenant_extra_parameters_setting_slug",
        ),
        UniqueConstraint(
            "organization_id",
            "work_type_id",
            "code",
            name="uq_tenant_extra_parameters_org_work_type_code",
        ),
        Index(
            "idx_tenant_extra_parameters_org_work_type_status",
            "organization_id",
            "work_type_id",
            "status",
            "sort_order",
        ),
        Index(
            "idx_tenant_extra_parameters_setting_section_sort",
            "tenant_work_type_setting_id",
            "section",
            "sort_order",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_tenant_extra_parameters_status",
        ),
        CheckConstraint(
            "data_type IN ('number', 'text', 'boolean', 'option')",
            name="ck_tenant_extra_parameters_data_type",
        ),
        CheckConstraint(
            "section IN ("
            "'dimensions', 'materials', 'condition_or_damage', "
            "'access_and_complexity', 'quantity_scope', 'optional_notes')",
            name="ck_tenant_extra_parameters_section",
        ),
        CheckConstraint(
            "min_number_value IS NULL OR max_number_value IS NULL OR min_number_value <= max_number_value",
            name="ck_tenant_extra_parameters_number_bounds_order",
        ),
        CheckConstraint(
            "(CASE WHEN default_text_value IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN default_number_value IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN default_boolean_value IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN default_option_code IS NOT NULL THEN 1 ELSE 0 END) <= 1",
            name="ck_tenant_extra_parameters_single_default_value",
        ),
        CheckConstraint(
            "data_type = 'text' OR default_text_value IS NULL",
            name="ck_tenant_extra_parameters_default_text_type",
        ),
        CheckConstraint(
            "data_type = 'number' OR (default_number_value IS NULL AND min_number_value IS NULL AND max_number_value IS NULL)",
            name="ck_tenant_extra_parameters_default_number_type",
        ),
        CheckConstraint(
            "data_type = 'boolean' OR default_boolean_value IS NULL",
            name="ck_tenant_extra_parameters_default_boolean_type",
        ),
        CheckConstraint(
            "data_type = 'option' OR default_option_code IS NULL",
            name="ck_tenant_extra_parameters_default_option_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_work_type_setting_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_work_type_settings.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    work_type_id: Mapped[str] = mapped_column(ForeignKey("work_types.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    section: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    min_number_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    max_number_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    vision_extractable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    manual_override_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_text_value: Mapped[str | None] = mapped_column(Text)
    default_number_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    default_boolean_value: Mapped[bool | None] = mapped_column(Boolean)
    default_option_code: Mapped[str | None] = mapped_column(String(64))
    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    tenant_work_type_setting: Mapped["TenantWorkTypeSetting"] = relationship(back_populates="extra_parameters")
    work_type: Mapped["WorkType"] = relationship()
    options: Mapped[list["TenantWorkTypeExtraParameterOption"]] = relationship(
        back_populates="parameter",
        cascade="all, delete-orphan",
        order_by="TenantWorkTypeExtraParameterOption.sort_order",
    )


class TenantWorkTypeExtraParameterOption(TimestampMixin, Base):
    """Allowed option values for tenant extra parameters."""
    __tablename__ = "tenant_work_type_extra_parameter_options"
    __table_args__ = (
        UniqueConstraint(
            "tenant_work_type_extra_parameter_id",
            "code",
            name="uq_tenant_extra_parameter_options_parameter_code",
        ),
        Index(
            "idx_tenant_extra_parameter_options_parameter_sort",
            "tenant_work_type_extra_parameter_id",
            "sort_order",
            "code",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_work_type_extra_parameter_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_work_type_extra_parameters.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    parameter: Mapped["TenantWorkTypeExtraParameter"] = relationship(back_populates="options")


class ProjectWorkItem(TimestampMixin, Base):
    """Runtime immutable-ish projection of an effective work type into a project."""
    __tablename__ = "project_work_items"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "work_type_id",
            "item_sequence",
            name="uq_project_work_items_project_work_type_sequence",
        ),
        Index("idx_project_work_items_org_project_status", "organization_id", "project_id", "status", "item_sequence"),
        Index("idx_project_work_items_project_work_type", "project_id", "work_type_id", "item_sequence"),
        Index("idx_project_work_items_analysis_profile", "project_id", "analysis_profile_id", "resolved_work_type_code"),
        Index(
            "idx_project_work_items_pricing_profile",
            "project_id",
            "catalog_pricing_profile_id",
            "resolved_work_type_code",
        ),
        Index(
            "idx_project_work_items_org_status_updated",
            "organization_id",
            "status",
            "updated_at",
            "id",
        ),
        Index(
            "idx_project_work_items_project_confirmation",
            "project_id",
            "confirmation_status",
            "updated_at",
            "id",
        ),
        CheckConstraint(
            "status IN ('draft', 'resolved', 'accepted', 'rejected')",
            name="ck_project_work_items_status",
        ),
        CheckConstraint(
            "source_type IN ('manual', 'vision', 'import', 'imported', 'system', 'default')",
            name="ck_project_work_items_source_type",
        ),
        CheckConstraint(
            "confirmation_status IN ('pending', 'mixed', 'confirmed')",
            name="ck_project_work_items_confirmation_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    work_type_id: Mapped[str] = mapped_column(ForeignKey("work_types.id", ondelete="RESTRICT"), nullable=False)
    tenant_work_type_setting_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenant_work_type_settings.id", ondelete="SET NULL")
    )
    analysis_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_analysis_profiles.id", ondelete="SET NULL")
    )
    catalog_pricing_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_pricing_profiles.id", ondelete="SET NULL")
    )
    tenant_pricing_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("pricing_profiles.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    confirmation_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    item_sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    resolved_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    resolved_work_type_code: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_category_code: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_analysis_profile_code: Mapped[str | None] = mapped_column(String(64))
    resolved_analysis_profile_version: Mapped[int | None] = mapped_column(Integer)
    resolved_catalog_pricing_profile_code: Mapped[str | None] = mapped_column(String(64))
    resolved_catalog_pricing_profile_version: Mapped[int | None] = mapped_column(Integer)
    resolved_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    resolved_catalog_version: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_setting_version: Mapped[int | None] = mapped_column(Integer)
    measured_quantity: Mapped[float | None] = mapped_column(Numeric(18, 4))
    measured_unit: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)
    confirmed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    work_type: Mapped["WorkType"] = relationship()
    tenant_work_type_setting: Mapped["TenantWorkTypeSetting | None"] = relationship()
    values: Mapped[list["ProjectWorkItemValue"]] = relationship(
        back_populates="project_work_item",
        cascade="all, delete-orphan",
        order_by="ProjectWorkItemValue.resolved_parameter_code",
    )
    detections: Mapped[list["VisionDetection"]] = relationship(
        back_populates="project_work_item",
        cascade="all, delete-orphan",
        order_by="VisionDetection.created_at",
    )


class ProjectWorkItemValue(TimestampMixin, Base):
    """Typed runtime value row bound to a project work item snapshot."""
    __tablename__ = "project_work_item_values"
    __table_args__ = (
        UniqueConstraint(
            "project_work_item_id",
            "work_type_parameter_id",
            name="uq_project_work_item_values_item_parameter",
        ),
        UniqueConstraint(
            "project_work_item_id",
            "tenant_work_type_extra_parameter_id",
            name="uq_project_work_item_values_item_extra_parameter",
        ),
        Index("idx_project_work_item_values_item", "project_work_item_id", "resolved_parameter_code"),
        Index(
            "idx_project_work_item_values_item_confirmation",
            "project_work_item_id",
            "confirmation_status",
            "resolved_parameter_code",
        ),
        Index("idx_project_work_item_values_parameter_lookup", "work_type_parameter_id", "resolved_parameter_code"),
        Index(
            "idx_project_work_item_values_extra_parameter_lookup",
            "tenant_work_type_extra_parameter_id",
            "resolved_parameter_code",
        ),
        CheckConstraint(
            "source_type IN ('manual', 'vision', 'import', 'imported', 'system', 'default')",
            name="ck_project_work_item_values_source_type",
        ),
        CheckConstraint(
            "confirmation_status IN ('pending', 'confirmed', 'corrected', 'defaulted')",
            name="ck_project_work_item_values_confirmation_status",
        ),
        CheckConstraint(
            "resolved_parameter_scope IN ('global', 'tenant_extra')",
            name="ck_project_work_item_values_parameter_scope",
        ),
        CheckConstraint(
            "resolved_data_type IN ('number', 'text', 'boolean', 'option')",
            name="ck_project_work_item_values_data_type",
        ),
        CheckConstraint(
            "("
            "(resolved_parameter_scope = 'global' AND work_type_parameter_id IS NOT NULL AND tenant_work_type_extra_parameter_id IS NULL) OR "
            "(resolved_parameter_scope = 'tenant_extra' AND tenant_work_type_extra_parameter_id IS NOT NULL AND work_type_parameter_id IS NULL)"
            ")",
            name="ck_project_work_item_values_definition_binding",
        ),
        CheckConstraint(
            "("
            "(resolved_data_type = 'text' AND value_text IS NOT NULL AND value_number IS NULL AND value_boolean IS NULL AND value_option_code IS NULL) OR "
            "(resolved_data_type = 'number' AND value_number IS NOT NULL AND value_text IS NULL AND value_boolean IS NULL AND value_option_code IS NULL) OR "
            "(resolved_data_type = 'boolean' AND value_boolean IS NOT NULL AND value_text IS NULL AND value_number IS NULL AND value_option_code IS NULL) OR "
            "(resolved_data_type = 'option' AND value_option_code IS NOT NULL AND value_text IS NULL AND value_number IS NULL AND value_boolean IS NULL)"
            ")",
            name="ck_project_work_item_values_typed_value_shape",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_work_item_id: Mapped[str] = mapped_column(
        ForeignKey("project_work_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    work_type_parameter_id: Mapped[str | None] = mapped_column(
        ForeignKey("work_type_parameters.id", ondelete="RESTRICT"),
        nullable=True,
    )
    tenant_work_type_extra_parameter_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenant_work_type_extra_parameters.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_detection_id: Mapped[str | None] = mapped_column(
        ForeignKey("vision_detections.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    source_confidence: Mapped[float | None] = mapped_column(Numeric(8, 4))
    confirmation_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    confirmed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operator_note: Mapped[str | None] = mapped_column(Text)
    resolved_parameter_scope: Mapped[str] = mapped_column(String(32), default="global", nullable=False)
    resolved_parameter_code: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_parameter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    resolved_data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resolved_unit: Mapped[str | None] = mapped_column(String(32))
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[float | None] = mapped_column(Numeric(18, 4))
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)
    value_option_code: Mapped[str | None] = mapped_column(String(64))

    project_work_item: Mapped["ProjectWorkItem"] = relationship(back_populates="values")
    parameter: Mapped["WorkTypeParameter | None"] = relationship()
    tenant_extra_parameter: Mapped["TenantWorkTypeExtraParameter | None"] = relationship()
    source_detection: Mapped["VisionDetection | None"] = relationship(foreign_keys=[source_detection_id])


class VisionDetection(Base):
    """Append-friendly vision event/detection log with optional work-item linkage."""
    __tablename__ = "vision_detections"
    __table_args__ = (
        UniqueConstraint("project_id", "detection_key", name="uq_vision_detections_project_detection_key"),
        Index("idx_vision_detections_org_project_status", "organization_id", "project_id", "status", "created_at"),
        Index("idx_vision_detections_project_work_item", "project_work_item_id", "created_at"),
        Index("idx_vision_detections_analysis_job_status", "analysis_job_id", "status", "created_at"),
        Index("idx_vision_detections_reference_photo", "reference_photo_id", "created_at"),
        Index("idx_vision_detections_profile_lookup", "project_id", "analysis_profile_id", "resolved_work_type_code"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'linked')",
            name="ck_vision_detections_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    project_work_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("project_work_items.id", ondelete="SET NULL")
    )
    analysis_job_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="SET NULL"))
    work_type_id: Mapped[str] = mapped_column(ForeignKey("work_types.id", ondelete="RESTRICT"), nullable=False)
    analysis_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_analysis_profiles.id", ondelete="SET NULL")
    )
    reference_photo_id: Mapped[str | None] = mapped_column(
        ForeignKey("project_photos.id", ondelete="SET NULL")
    )
    detection_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(8, 4))
    raw_label: Mapped[str | None] = mapped_column(String(255))
    raw_value: Mapped[str | None] = mapped_column(String(255))
    detected_quantity: Mapped[float | None] = mapped_column(Numeric(18, 4))
    detected_unit: Mapped[str | None] = mapped_column(String(32))
    geometry_type: Mapped[str | None] = mapped_column(String(32))
    bbox_left: Mapped[float | None] = mapped_column(Numeric(10, 4))
    bbox_top: Mapped[float | None] = mapped_column(Numeric(10, 4))
    bbox_right: Mapped[float | None] = mapped_column(Numeric(10, 4))
    bbox_bottom: Mapped[float | None] = mapped_column(Numeric(10, 4))
    geometry_json: Mapped[str | None] = mapped_column(Text)
    resolved_work_type_code: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_analysis_profile_code: Mapped[str | None] = mapped_column(String(64))
    resolved_analysis_profile_version: Mapped[int | None] = mapped_column(Integer)
    source_provider: Mapped[str | None] = mapped_column(String(64))
    source_model: Mapped[str | None] = mapped_column(String(128))
    source_model_version: Mapped[str | None] = mapped_column(String(64))
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project_work_item: Mapped["ProjectWorkItem | None"] = relationship(back_populates="detections")
    work_type: Mapped["WorkType"] = relationship()
