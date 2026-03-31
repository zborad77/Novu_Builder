from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import (
    AnalysisProfile,
    AnalysisProfileConfidenceThreshold,
    AnalysisProfileExtractionRule,
    AnalysisProfileIgnoredObject,
    AnalysisProfileOutputMapping,
    AnalysisProfileTargetObject,
    AnalysisProfileValidationRule,
    CatalogPricingProfile,
    CatalogPricingProfileAdjustmentRule,
    CatalogPricingProfileBaseRule,
    CatalogPricingProfileLaborAssumption,
    CatalogPricingProfileMaterialAssumption,
    CatalogPricingProfileRequiredInput,
    Project,
    TenantWorkTypeSetting,
    WorkCategory,
    WorkType,
    WorkTypeParameter,
    WorkTypeParameterOption,
)
from app.repositories.quote_variant_repository import QuoteVariantRepository
from app.repositories.work_catalog_repository import WorkCatalogRepository
from app.schemas.work_catalog import ProjectWorkItemCreate, ProjectWorkItemValueInput
from app.services.pricing_profile_service import PricingProfileResolutionError, PricingProfileService
from app.services.quote_variant_service import QuoteVariantService
from app.services.work_catalog_service import WorkCatalogService
from app.work_catalog.domain import CatalogValidationError, validate_pricing_profile_definition
from app.work_catalog.seeds import GLOBAL_WORK_CATALOG_SEED


async def _ensure_global_catalog_seed(db_session) -> None:
    model_by_key = {
        "categories": WorkCategory,
        "analysis_profiles": AnalysisProfile,
        "analysis_profile_target_objects": AnalysisProfileTargetObject,
        "analysis_profile_ignored_objects": AnalysisProfileIgnoredObject,
        "analysis_profile_extraction_rules": AnalysisProfileExtractionRule,
        "analysis_profile_validation_rules": AnalysisProfileValidationRule,
        "analysis_profile_confidence_thresholds": AnalysisProfileConfidenceThreshold,
        "analysis_profile_output_mappings": AnalysisProfileOutputMapping,
        "catalog_pricing_profiles": CatalogPricingProfile,
        "pricing_profile_required_inputs": CatalogPricingProfileRequiredInput,
        "pricing_profile_base_rules": CatalogPricingProfileBaseRule,
        "pricing_profile_adjustment_rules": CatalogPricingProfileAdjustmentRule,
        "pricing_profile_labor_assumptions": CatalogPricingProfileLaborAssumption,
        "pricing_profile_material_assumptions": CatalogPricingProfileMaterialAssumption,
        "work_types": WorkType,
        "parameters": WorkTypeParameter,
        "parameter_options": WorkTypeParameterOption,
    }
    for key, model in model_by_key.items():
        for row in GLOBAL_WORK_CATALOG_SEED[key]:
            if await db_session.get(model, row["id"]) is None:
                db_session.add(model(**row))
    await db_session.commit()


async def _ensure_project(db_session, test_tenants) -> Project:
    project_id = f"prj_pp_{uuid4().hex[:8]}"
    project = Project(
        id=project_id,
        organization_id=test_tenants["org_a"],
        created_by_user_id="usr_e2e_a1",
        title=f"Pricing profile test {project_id}",
        description="Catalog-driven pricing subsystem test",
        status="draft",
        source="mobile",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(project)
    await db_session.commit()
    return project


async def test_pricing_profile_resolution_returns_structured_active_profile(
    db_session,
    test_tenants,
):
    await _ensure_global_catalog_seed(db_session)
    service = PricingProfileService(WorkCatalogRepository(db_session))

    resolved = await service.resolve_for_work_type(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
    )

    assert resolved.work_type.code == "roof-repair"
    assert resolved.catalog_pricing_profile.code == "roof-repair-pricing"
    assert resolved.catalog_pricing_profile.status == "active"
    assert resolved.catalog_pricing_profile.pricing_basis == "area"
    assert {row.code for row in resolved.catalog_pricing_profile.required_inputs} >= {
        "basis-quantity",
        "severity",
        "access",
    }
    assert {row.code for row in resolved.catalog_pricing_profile.base_rules} >= {
        "labor-repair",
        "material-repair",
        "site-setup",
    }


async def test_pricing_engine_calculates_explainable_result_and_minimum_charge(
    db_session,
    test_tenants,
):
    await _ensure_global_catalog_seed(db_session)
    project = await _ensure_project(db_session, test_tenants)
    work_catalog_service = WorkCatalogService(WorkCatalogRepository(db_session))

    work_item = await work_catalog_service.create_project_work_item(
        project_id=project.id,
        organization_id=test_tenants["org_a"],
        payload=ProjectWorkItemCreate(
            workTypeCode="roof-repair",
            measuredQuantity=2.0,
            values=[
                ProjectWorkItemValueInput(parameterCode="work-area-sqm", numberValue=2.0),
                ProjectWorkItemValueInput(parameterCode="roof-covering-type", optionValue="bitumen-membrane"),
                ProjectWorkItemValueInput(parameterCode="damage-type", optionValue="membrane-split"),
                ProjectWorkItemValueInput(parameterCode="severity-band", optionValue="moderate"),
                ProjectWorkItemValueInput(parameterCode="access-method", optionValue="roof-ladder"),
                ProjectWorkItemValueInput(parameterCode="repair-zones-count", numberValue=1),
            ],
        ),
        created_by_user_id="usr_e2e_a1",
    )

    stored_work_item = await WorkCatalogRepository(db_session).get_project_work_item(
        project.id,
        work_item.id,
        organization_id=test_tenants["org_a"],
    )
    assert stored_work_item is not None

    service = PricingProfileService(WorkCatalogRepository(db_session))
    resolved = await service.resolve_for_snapshot(
        organization_id=test_tenants["org_a"],
        work_type_code=stored_work_item.resolved_work_type_code,
        catalog_pricing_profile_id=stored_work_item.catalog_pricing_profile_id,
        tenant_pricing_profile_id=stored_work_item.tenant_pricing_profile_id,
    )
    priced = service.calculate_project_work_item(
        work_item=stored_work_item,
        resolved=resolved,
    )

    assert priced["catalog_pricing_profile_code"] == "roof-repair-pricing"
    assert {line["catalog_pricing_rule_code"] for line in priced["line_items"]} >= {
        "labor-repair",
        "material-repair",
        "site-setup",
        "severity-band-moderate",
        "minimum-job-charge",
    }
    assert priced["minimum_job_adjustment"] > 0
    assert priced["total"] >= 15000


async def test_pricing_profile_resolution_rejects_mismatched_tenant_override(
    db_session,
    test_tenants,
):
    await _ensure_global_catalog_seed(db_session)
    existing_setting = await db_session.execute(
        select(TenantWorkTypeSetting).where(
            TenantWorkTypeSetting.organization_id == test_tenants["org_a"],
            TenantWorkTypeSetting.work_type_id == "wt_roof_repair",
        )
    )
    tenant_setting = existing_setting.scalar_one_or_none()
    if tenant_setting is None:
        tenant_setting = TenantWorkTypeSetting(
            id=f"twts_pp_bad_{uuid4().hex[:8]}",
            organization_id=test_tenants["org_a"],
            work_type_id="wt_roof_repair",
            status="enabled",
            catalog_pricing_profile_id="cpp_painting_pricing_v1",
            config_version=1,
        )
        db_session.add(tenant_setting)
    else:
        tenant_setting.catalog_pricing_profile_id = "cpp_painting_pricing_v1"
    await db_session.commit()

    service = PricingProfileService(WorkCatalogRepository(db_session))
    with pytest.raises(PricingProfileResolutionError, match="inconsistent with work type"):
        await service.resolve_for_work_type(
            organization_id=test_tenants["org_a"],
            work_type_code="roof-repair",
        )


def test_pricing_profile_validation_blocks_unknown_parameter_dependency():
    with pytest.raises(CatalogValidationError, match="unknown parameter"):
        validate_pricing_profile_definition(
            code="roof-repair-pricing",
            version=1,
            status="active",
            pricing_basis="area",
            currency="CZK",
            pricing_strategy="catalog_formula",
            labor_rate_source="tenant_default",
            material_pricing_source="catalog_default",
            min_job_price=1000,
            required_inputs=[
                {
                    "code": "basis-quantity",
                    "label": "Basis Quantity",
                    "source_type": "parameter",
                    "source_key": "missing-parameter",
                }
            ],
            base_rules=[
                {
                    "code": "labor-repair",
                    "line_type": "labor",
                    "calculation_method": "per_unit",
                    "quantity_source_type": "constant",
                    "quantity_multiplier": 1,
                    "unit": "hr",
                    "rate_source": "tenant_hourly_rate",
                }
            ],
            adjustment_rules=[],
            labor_assumptions=[],
            material_assumptions=[],
            parameter_codes={"work-area-sqm"},
        )


async def test_quote_variant_service_uses_catalog_pricing_engine_for_runtime_work_items(
    db_session,
    test_tenants,
):
    await _ensure_global_catalog_seed(db_session)
    project = await _ensure_project(db_session, test_tenants)
    work_catalog_service = WorkCatalogService(WorkCatalogRepository(db_session))
    await work_catalog_service.create_project_work_item(
        project_id=project.id,
        organization_id=test_tenants["org_a"],
        payload=ProjectWorkItemCreate(
            workTypeCode="painting",
            measuredQuantity=24,
            values=[
                ProjectWorkItemValueInput(parameterCode="work-area-sqm", numberValue=24),
                ProjectWorkItemValueInput(parameterCode="coat-count", numberValue=2),
                ProjectWorkItemValueInput(parameterCode="paint-system-type", optionValue="interior-emulsion"),
                ProjectWorkItemValueInput(parameterCode="surface-condition", optionValue="sound"),
                ProjectWorkItemValueInput(parameterCode="access-method", optionValue="clear-interior"),
                ProjectWorkItemValueInput(parameterCode="zone-count", numberValue=2),
            ],
        ),
        created_by_user_id="usr_e2e_a1",
    )

    service = QuoteVariantService(
        QuoteVariantRepository(db_session),
        WorkCatalogRepository(db_session),
    )
    variants = await service.recalculate_quote_variants(project.id)

    assert variants is not None
    assert {variant.variantType for variant in variants} == {"economy", "standard", "premium"}
    assert all(variant.items for variant in variants)
    assert {item.catalogPricingRuleCode for item in variants[0].items} >= {
        "labor-production",
        "material-allowance",
        "mobilization",
    }
    assert {item.workTypeCode for item in variants[0].items} == {"painting"}
