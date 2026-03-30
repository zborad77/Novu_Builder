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
        UniqueConstraint("code", name="uq_catalog_analysis_profiles_code"),
        Index("idx_catalog_analysis_profiles_active_code", "is_active", "code"),
        CheckConstraint(
            "task_type IN ('classification', 'detection', 'measurement', 'hybrid')",
            name="ck_catalog_analysis_profiles_task_type",
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

    work_types: Mapped[list["WorkType"]] = relationship(
        back_populates="default_analysis_profile",
        foreign_keys="WorkType.default_analysis_profile_id",
    )
    tenant_settings: Mapped[list["TenantWorkTypeSetting"]] = relationship(
        back_populates="analysis_profile",
        foreign_keys="TenantWorkTypeSetting.analysis_profile_id",
    )


class CatalogPricingProfile(TimestampMixin, Base):
    """Global pricing strategy profile, distinct from tenant pricebooks."""
    __tablename__ = "catalog_pricing_profiles"
    __table_args__ = (
        UniqueConstraint("code", name="uq_catalog_pricing_profiles_code"),
        Index("idx_catalog_pricing_profiles_active_code", "is_active", "code"),
        CheckConstraint(
            "pricing_strategy IN ('tenant_pricebook', 'fixed_formula', 'manual_review')",
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
    pricing_strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    labor_rate_source: Mapped[str] = mapped_column(String(32), nullable=False)
    material_pricing_source: Mapped[str] = mapped_column(String(32), nullable=False)
    default_margin_pct: Mapped[float | None] = mapped_column(Numeric(14, 4))
    default_markup_pct: Mapped[float | None] = mapped_column(Numeric(14, 4))
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


class WorkType(TimestampMixin, Base):
    """Global work type definition resolved into tenant-effective and runtime rows."""
    __tablename__ = "work_types"
    __table_args__ = (
        UniqueConstraint("code", name="uq_work_types_code"),
        UniqueConstraint("slug", name="uq_work_types_slug"),
        Index("idx_work_types_category_state_sort", "category_id", "state", "sort_order", "code"),
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
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("work_categories.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    default_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    measurement_kind: Mapped[str] = mapped_column(String(32), default="area", nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
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
        Index(
            "idx_project_work_items_org_status_updated",
            "organization_id",
            "status",
            "updated_at",
            "id",
        ),
        CheckConstraint(
            "status IN ('draft', 'resolved', 'accepted', 'rejected')",
            name="ck_project_work_items_status",
        ),
        CheckConstraint(
            "source_type IN ('manual', 'vision', 'import', 'system')",
            name="ck_project_work_items_source_type",
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
    item_sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    resolved_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    resolved_work_type_code: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_category_code: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    resolved_catalog_version: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_setting_version: Mapped[int | None] = mapped_column(Integer)
    measured_quantity: Mapped[float | None] = mapped_column(Numeric(18, 4))
    measured_unit: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)
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
        Index("idx_project_work_item_values_item", "project_work_item_id", "resolved_parameter_code"),
        Index("idx_project_work_item_values_parameter_lookup", "work_type_parameter_id", "resolved_parameter_code"),
        CheckConstraint(
            "source_type IN ('manual', 'vision', 'import', 'system')",
            name="ck_project_work_item_values_source_type",
        ),
        CheckConstraint(
            "resolved_data_type IN ('number', 'text', 'boolean', 'option')",
            name="ck_project_work_item_values_data_type",
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
    work_type_parameter_id: Mapped[str] = mapped_column(
        ForeignKey("work_type_parameters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    resolved_parameter_code: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_parameter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    resolved_data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resolved_unit: Mapped[str | None] = mapped_column(String(32))
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[float | None] = mapped_column(Numeric(18, 4))
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)
    value_option_code: Mapped[str | None] = mapped_column(String(64))

    project_work_item: Mapped["ProjectWorkItem"] = relationship(back_populates="values")
    parameter: Mapped["WorkTypeParameter"] = relationship()


class VisionDetection(Base):
    """Append-friendly vision event/detection log with optional work-item linkage."""
    __tablename__ = "vision_detections"
    __table_args__ = (
        UniqueConstraint("project_id", "detection_key", name="uq_vision_detections_project_detection_key"),
        Index("idx_vision_detections_org_project_status", "organization_id", "project_id", "status", "created_at"),
        Index("idx_vision_detections_project_work_item", "project_work_item_id", "created_at"),
        Index("idx_vision_detections_analysis_job_status", "analysis_job_id", "status", "created_at"),
        Index("idx_vision_detections_reference_photo", "reference_photo_id", "created_at"),
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
    source_provider: Mapped[str | None] = mapped_column(String(64))
    source_model: Mapped[str | None] = mapped_column(String(128))
    source_model_version: Mapped[str | None] = mapped_column(String(64))
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project_work_item: Mapped["ProjectWorkItem | None"] = relationship(back_populates="detections")
    work_type: Mapped["WorkType"] = relationship()
