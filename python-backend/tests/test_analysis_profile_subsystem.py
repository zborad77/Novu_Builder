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
    Project,
    TenantWorkTypeSetting,
    WorkCategory,
    WorkType,
    WorkTypeParameter,
    WorkTypeParameterOption,
)
from app.repositories.work_catalog_repository import WorkCatalogRepository
from app.services.analysis_profile_service import (
    AnalysisProfileResolutionError,
    AnalysisProfileService,
)
from app.work_catalog.domain import CatalogValidationError
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
    project_id = f"prj_ap_{uuid4().hex[:8]}"
    project = Project(
        id=project_id,
        organization_id=test_tenants["org_a"],
        created_by_user_id="usr_e2e_a1",
        title=f"Analysis profile test {project_id}",
        description="Structured catalog-driven vision test",
        status="draft",
        source="mobile",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(project)
    await db_session.commit()
    return project


def _sample_attribute_value(parameter: WorkTypeParameter):
    if parameter.data_type == "number":
        if parameter.max_number_value is not None:
            return max(1, float(parameter.max_number_value) - 1)
        return 12.0
    if parameter.data_type == "boolean":
        return True
    if parameter.data_type == "text":
        return f"Detected {parameter.code}"
    for option in parameter.options or []:
        if option.is_active:
            return option.code
    raise AssertionError(f"No active option for parameter '{parameter.code}'.")


async def test_analysis_profile_resolution_returns_structured_active_profile(
    db_session,
    test_tenants,
):
    await _ensure_global_catalog_seed(db_session)
    service = AnalysisProfileService(WorkCatalogRepository(db_session))

    resolved = await service.resolve_for_work_type(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
    )

    assert resolved.work_type.code == "roof-repair"
    assert resolved.analysis_profile.code == "roof-repair-vision"
    assert resolved.analysis_profile.status == "active"
    assert resolved.analysis_profile.scope_code == "roof-damage-assessment"
    assert {row.code for row in resolved.analysis_profile.target_objects} >= {"roof-surface", "flashing-line"}
    assert {row.attribute_code for row in resolved.analysis_profile.extraction_rules} >= {"work-area-sqm", "damage-type"}
    assert any(row.target_entity == "project_work_item_value" for row in resolved.analysis_profile.output_mappings)


async def test_analysis_profile_mapping_builds_runtime_value_payloads(
    db_session,
    test_tenants,
):
    await _ensure_global_catalog_seed(db_session)
    service = AnalysisProfileService(WorkCatalogRepository(db_session))
    resolved = await service.resolve_for_work_type(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
    )

    catalog_attributes = {}
    for rule in resolved.analysis_profile.extraction_rules:
        parameter = next(parameter for parameter in resolved.work_type.parameters if parameter.code == rule.target_parameter_code)
        catalog_attributes[rule.attribute_code] = {
            "value": _sample_attribute_value(parameter),
            "confidence": 0.88,
        }

    mapped = service.validate_and_map_output(
        resolved=resolved,
        raw_output={
            "objectType": "roof",
            "surfaceCondition": "requires_attention",
            "recommendedScope": "local_repair",
            "estimatedQuantity": 18.5,
            "estimatedUnit": "m2",
            "estimatedAreaSqm": 18.5,
            "areaConfidence": 0.82,
            "maskPolygon": [{"x": 0.1, "y": 0.1}, {"x": 0.8, "y": 0.1}, {"x": 0.8, "y": 0.8}],
            "materials": [{"name": "Membrane patch", "unit": "pcs", "quantity": 2}],
            "workflowSteps": [{"step": 1, "name": "Inspect leak path"}],
            "estimatedTotalDays": 1.5,
            "laborHoursTotal": 12,
            "catalogAttributes": catalog_attributes,
        },
        photo_count=3,
    )

    assert mapped["resolved_work_type_code"] == "roof-repair"
    assert mapped["analysis_profile_code"] == "roof-repair-vision"
    assert mapped["analysis_result_fields"]["estimated_quantity"] == 18.5
    assert mapped["analysis_result_fields"]["estimated_unit"] == "m2"
    assert {row["parameterCode"] for row in mapped["project_work_item_values"]} >= {
        "work-area-sqm",
        "damage-type",
    }


async def test_analysis_profile_validation_blocks_out_of_range_numeric_attributes(
    db_session,
    test_tenants,
):
    await _ensure_global_catalog_seed(db_session)
    service = AnalysisProfileService(WorkCatalogRepository(db_session))
    resolved = await service.resolve_for_work_type(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
    )

    numeric_parameter = next(
        parameter
        for parameter in resolved.work_type.parameters
        if parameter.vision_extractable and parameter.data_type == "number" and parameter.max_number_value is not None
    )

    with pytest.raises(CatalogValidationError, match=numeric_parameter.code):
        service.validate_and_map_output(
            resolved=resolved,
            raw_output={
                "objectType": "roof",
                "surfaceCondition": "requires_attention",
                "recommendedScope": "local_repair",
                "estimatedQuantity": 10,
                "estimatedUnit": "m2",
                "estimatedAreaSqm": 10,
                "areaConfidence": 0.8,
                "catalogAttributes": {
                    numeric_parameter.code: {
                        "value": float(numeric_parameter.max_number_value) + 10,
                        "confidence": 0.9,
                    }
                },
            },
            photo_count=3,
        )


async def test_analysis_profile_resolution_prefers_tenant_override_snapshot(
    db_session,
    test_tenants,
):
    await _ensure_global_catalog_seed(db_session)
    work_type = await db_session.get(WorkType, "wt_roof_repair")
    assert work_type is not None
    work_type.default_analysis_profile_id = None

    existing_setting = await db_session.execute(
        select(TenantWorkTypeSetting).where(
            TenantWorkTypeSetting.organization_id == test_tenants["org_a"],
            TenantWorkTypeSetting.work_type_id == "wt_roof_repair",
        )
    )
    tenant_setting = existing_setting.scalar_one_or_none()
    if tenant_setting is None:
        tenant_setting = TenantWorkTypeSetting(
            id=f"twts_ap_{uuid4().hex[:8]}",
            organization_id=test_tenants["org_a"],
            work_type_id="wt_roof_repair",
            status="enabled",
            analysis_profile_id="ap_roof_repair_vision_v1",
            config_version=1,
        )
        db_session.add(tenant_setting)
    else:
        tenant_setting.analysis_profile_id = "ap_roof_repair_vision_v1"
    await db_session.commit()

    service = AnalysisProfileService(WorkCatalogRepository(db_session))
    resolved = await service.resolve_for_work_type(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
    )

    assert resolved.analysis_profile.id == "ap_roof_repair_vision_v1"


async def test_analysis_profile_resolution_rejects_mismatched_tenant_override(
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
            id=f"twts_ap_bad_{uuid4().hex[:8]}",
            organization_id=test_tenants["org_a"],
            work_type_id="wt_roof_repair",
            status="enabled",
            analysis_profile_id="ap_painting_vision_v1",
            config_version=1,
        )
        db_session.add(tenant_setting)
    else:
        tenant_setting.analysis_profile_id = "ap_painting_vision_v1"
    await db_session.commit()

    service = AnalysisProfileService(WorkCatalogRepository(db_session))
    with pytest.raises(AnalysisProfileResolutionError, match="inconsistent with work type"):
        await service.resolve_for_work_type(
            organization_id=test_tenants["org_a"],
            work_type_code="roof-repair",
        )

    tenant_setting.analysis_profile_id = None
    await db_session.commit()
