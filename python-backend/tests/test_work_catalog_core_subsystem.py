from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

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
    ProjectWorkItemValue,
    TenantWorkTypeExtraParameter,
    TenantWorkTypeExtraParameterOption,
    TenantWorkTypeParameterOverride,
    TenantWorkTypeSetting,
    WorkCategory,
    WorkType,
    WorkTypeParameter,
    WorkTypeParameterOption,
)
from app.repositories.work_catalog_repository import WorkCatalogRepository
from app.schemas.work_catalog import (
    ProjectWorkItemCreate,
    ProjectWorkItemValueConfirmationInput,
    ProjectWorkItemValueInput,
    TenantWorkTypeSettingUpsert,
    TenantWorkTypeSettingWithParametersUpsert,
)
from app.services.work_catalog_service import WorkCatalogNotFoundError, WorkCatalogService
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


async def _ensure_tenant_setting(db_session, test_tenants) -> None:
    await _ensure_global_catalog_seed(db_session)
    row_id = "twts_test_org_a_roof_repair"
    setting = await db_session.get(TenantWorkTypeSetting, row_id)
    if setting is None:
        setting = TenantWorkTypeSetting(
            id=row_id,
            organization_id=test_tenants["org_a"],
            work_type_id="wt_roof_repair",
            status="enabled",
            custom_display_name="Tenant A Crack Repair",
            catalog_pricing_profile_id="cpp_roof_repair_pricing_v1",
            tenant_pricing_profile_id=test_tenants["pricebook_a"],
            config_version=1,
        )
        db_session.add(setting)
    else:
        setting.organization_id = test_tenants["org_a"]
        setting.work_type_id = "wt_roof_repair"
        setting.status = "enabled"
        setting.custom_display_name = "Tenant A Crack Repair"
        setting.catalog_pricing_profile_id = "cpp_roof_repair_pricing_v1"
        setting.tenant_pricing_profile_id = test_tenants["pricebook_a"]
    await db_session.commit()
    parameter_override_id = "twpo_test_org_a_roof_repair_severity"
    parameter_override = await db_session.get(TenantWorkTypeParameterOverride, parameter_override_id)
    if parameter_override is None:
        parameter_override = TenantWorkTypeParameterOverride(
            id=parameter_override_id,
            tenant_work_type_setting_id=row_id,
            organization_id=test_tenants["org_a"],
            work_type_id="wt_roof_repair",
            work_type_parameter_id="wtp_roof_repair_severity",
            override_status="optional",
            custom_display_name="Zavaznost opravy",
            sort_order_override=25,
            config_version=1,
        )
        db_session.add(parameter_override)
    else:
        parameter_override.tenant_work_type_setting_id = row_id
        parameter_override.organization_id = test_tenants["org_a"]
        parameter_override.work_type_id = "wt_roof_repair"
        parameter_override.work_type_parameter_id = "wtp_roof_repair_severity"
        parameter_override.override_status = "optional"
        parameter_override.custom_display_name = "Zavaznost opravy"
        parameter_override.sort_order_override = 25
    await db_session.commit()


async def _create_project(db_session, test_tenants) -> str:
    project_id = f"prj_wc_{uuid4().hex[:10]}"
    now = datetime.now(UTC)
    db_session.add(
        Project(
            id=project_id,
            organization_id=test_tenants["org_a"],
            created_by_user_id="usr_e2e_a1",
            title=f"Work catalog test {project_id}",
            description="Core subsystem test project",
            status="draft",
            source="mobile",
            created_at=now,
            updated_at=now,
        )
    )
    await db_session.commit()
    return project_id


async def test_effective_work_type_resolution_applies_tenant_override_without_cloning_globals(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    effective = await service.get_effective_work_type(test_tenants["org_a"], "roof-repair")

    assert effective.code == "roof-repair"
    assert effective.effectiveDisplayName == "Tenant A Crack Repair"
    assert effective.tenantPricingProfileId == test_tenants["pricebook_a"]
    assert effective.analysisProfile is not None
    assert effective.catalogPricingProfile is not None
    assert {
        parameter.code
        for parameter in effective.parameters
    } >= {
        "work-area-sqm",
        "roof-covering-type",
        "damage-type",
        "severity-band",
        "access-method",
        "operator-notes",
    }
    severity_parameter = next(
        parameter for parameter in effective.parameters if parameter.code == "severity-band"
    )
    assert severity_parameter.required is False
    assert severity_parameter.effectiveLabel == "Zavaznost opravy"
    assert severity_parameter.section == "condition_or_damage"
    assert severity_parameter.visionExtractable is True
    assert effective.parameterSections
    assert {section.code for section in effective.parameterSections} == {
        "dimensions",
        "materials",
        "condition_or_damage",
        "access_and_complexity",
        "quantity_scope",
        "optional_notes",
    }

    repo = WorkCatalogRepository(db_session)
    global_work_type = await repo.get_work_type_by_code("roof-repair")
    assert global_work_type is not None
    assert global_work_type.name == "Roof Repair"


async def test_project_work_item_creation_snapshots_effective_config_and_respects_tenant_scope(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    project_id = await _create_project(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    created = await service.create_project_work_item(
        project_id=project_id,
        organization_id=test_tenants["org_a"],
        payload=ProjectWorkItemCreate(
            workTypeCode="roof-repair",
            sourceType="vision",
            measuredQuantity=12.4,
            values=[
                ProjectWorkItemValueInput(parameterCode="work-area-sqm", numberValue=12.4, sourceType="vision"),
                ProjectWorkItemValueInput(parameterCode="roof-covering-type", optionValue="bitumen-membrane"),
                ProjectWorkItemValueInput(parameterCode="damage-type", optionValue="membrane-split", sourceType="vision"),
                ProjectWorkItemValueInput(parameterCode="severity-band", optionValue="moderate", sourceType="vision"),
                ProjectWorkItemValueInput(parameterCode="access-method", optionValue="roof-ladder"),
            ],
        ),
        created_by_user_id="usr_e2e_a1",
    )

    assert created.workTypeCode == "roof-repair"
    assert created.categoryCode == "roofing"
    assert created.title == "Tenant A Crack Repair"
    assert created.settingVersion == 1
    assert created.tenantPricingProfileId == test_tenants["pricebook_a"]
    assert len(created.values) == 5
    assert {value.parameterCode for value in created.values} == {
        "work-area-sqm",
        "roof-covering-type",
        "damage-type",
        "severity-band",
        "access-method",
    }

    visible = await service.list_project_work_items(project_id=project_id, organization_id=test_tenants["org_a"])

    assert [item.id for item in visible] == [created.id]
    with pytest.raises(WorkCatalogNotFoundError):
        await service.list_project_work_items(project_id=project_id, organization_id=test_tenants["org_b"])


async def test_project_work_item_creation_rejects_invalid_parameter_type_payload(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    project_id = await _create_project(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    with pytest.raises(CatalogValidationError, match="numberValue is required"):
        await service.create_project_work_item(
            project_id=project_id,
            organization_id=test_tenants["org_a"],
            payload=ProjectWorkItemCreate(
                workTypeCode="roof-repair",
                values=[
                    ProjectWorkItemValueInput(parameterCode="work-area-sqm", textValue="wrong-shape"),
                    ProjectWorkItemValueInput(parameterCode="roof-covering-type", optionValue="bitumen-membrane"),
                    ProjectWorkItemValueInput(parameterCode="damage-type", optionValue="membrane-split"),
                    ProjectWorkItemValueInput(parameterCode="access-method", optionValue="roof-ladder"),
                    ProjectWorkItemValueInput(parameterCode="severity-band", optionValue="moderate"),
                ],
            ),
            created_by_user_id="usr_e2e_a1",
        )


async def test_work_catalog_has_unique_code_guards_and_hot_path_indexes(db_session, test_tenants):
    await _ensure_global_catalog_seed(db_session)

    work_type_index_names = {index.name for index in WorkType.__table__.indexes}
    tenant_setting_index_names = {index.name for index in TenantWorkTypeSetting.__table__.indexes}

    assert "idx_work_types_catalog_sort" in work_type_index_names
    assert "idx_work_types_category_state_sort" in work_type_index_names
    assert "idx_tenant_work_type_settings_org_status" in tenant_setting_index_names

    db_session.add(
        WorkType(
            id=f"wt_dup_{uuid4().hex[:8]}",
            category_id="wc_roofing",
            code="roof-repair",
            slug=f"dup-{uuid4().hex[:8]}",
            name="Duplicate code",
            default_unit="m2",
            measurement_kind="area",
            state="active",
            sort_order=999,
            catalog_version=1,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_tenant_setting_upsert_bumps_config_version(db_session, test_tenants):
    await _ensure_tenant_setting(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    effective = await service.upsert_tenant_setting(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
        payload=TenantWorkTypeSettingUpsert(
            status="enabled",
            customDisplayName="Tenant A Crack Repair Premium",
            catalogPricingProfileCode="roof-repair-pricing",
            tenantPricingProfileId=test_tenants["pricebook_a"],
        ),
        updated_by_user_id="usr_e2e_a1",
    )

    assert effective.effectiveDisplayName == "Tenant A Crack Repair Premium"
    assert effective.settingVersion == 2


async def test_parameter_override_upsert_changes_effective_requiredness_without_catalog_copy(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    effective = await service.upsert_tenant_setting(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
        payload=TenantWorkTypeSettingWithParametersUpsert(
            status="enabled",
            customDisplayName="Tenant A Crack Repair",
            parameterOverrides=[
                {
                    "parameterCode": "severity-band",
                    "overrideStatus": "hidden",
                    "customDisplayName": "Interni zavaznost",
                }
            ],
        ),
        updated_by_user_id="usr_e2e_a1",
    )

    severity_parameter = next(
        parameter for parameter in effective.parameters if parameter.code == "severity-band"
    )
    assert severity_parameter.enabled is False
    assert severity_parameter.overrideStatus == "hidden"
    assert severity_parameter.effectiveLabel == "Interni zavaznost"

    global_parameter = await db_session.get(WorkTypeParameter, "wtp_roof_repair_severity")
    assert global_parameter is not None
    assert global_parameter.name == "Severity Band"

    tenant_override = await db_session.get(
        TenantWorkTypeParameterOverride,
        "twpo_test_org_a_roof_repair_severity",
    )
    assert tenant_override is not None
    tenant_override.override_status = "optional"
    tenant_override.custom_display_name = "Zavaznost opravy"
    await db_session.commit()


async def test_project_work_item_uses_parameter_override_requiredness(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    project_id = await _create_project(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    created = await service.create_project_work_item(
        project_id=project_id,
        organization_id=test_tenants["org_a"],
        payload=ProjectWorkItemCreate(
            workTypeCode="roof-repair",
            values=[
                ProjectWorkItemValueInput(parameterCode="work-area-sqm", numberValue=9.5),
                ProjectWorkItemValueInput(parameterCode="roof-covering-type", optionValue="bitumen-membrane"),
                ProjectWorkItemValueInput(parameterCode="damage-type", optionValue="membrane-split"),
                ProjectWorkItemValueInput(parameterCode="access-method", optionValue="roof-ladder"),
            ],
        ),
        created_by_user_id="usr_e2e_a1",
    )

    assert created.workTypeCode == "roof-repair"
    assert {value.parameterCode for value in created.values} == {
        "work-area-sqm",
        "roof-covering-type",
        "damage-type",
        "access-method",
    }


async def test_parameter_seed_schema_covers_all_seeded_work_types_with_required_sections(db_session):
    await _ensure_global_catalog_seed(db_session)

    work_types = (await WorkCatalogRepository(db_session).list_work_types())
    assert len(work_types) == len(GLOBAL_WORK_CATALOG_SEED["work_types"])
    for work_type in work_types:
        sections = {parameter.section for parameter in work_type.parameters}
        assert sections == {
            "dimensions",
            "materials",
            "condition_or_damage",
            "access_and_complexity",
            "quantity_scope",
            "optional_notes",
        }


async def test_project_work_item_creation_enforces_number_bounds_from_parameter_schema(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    project_id = await _create_project(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    with pytest.raises(CatalogValidationError, match="roof-pitch-deg"):
        await service.create_project_work_item(
            project_id=project_id,
            organization_id=test_tenants["org_a"],
            payload=ProjectWorkItemCreate(
                workTypeCode="roof-repair",
                values=[
                    ProjectWorkItemValueInput(parameterCode="work-area-sqm", numberValue=10),
                    ProjectWorkItemValueInput(parameterCode="roof-pitch-deg", numberValue=95),
                    ProjectWorkItemValueInput(parameterCode="roof-covering-type", optionValue="bitumen-membrane"),
                    ProjectWorkItemValueInput(parameterCode="damage-type", optionValue="membrane-split"),
                    ProjectWorkItemValueInput(parameterCode="severity-band", optionValue="moderate"),
                    ProjectWorkItemValueInput(parameterCode="access-method", optionValue="roof-ladder"),
                ],
            ),
            created_by_user_id="usr_e2e_a1",
        )


async def test_project_work_item_creation_blocks_vision_values_for_non_extractable_parameters(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    project_id = await _create_project(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    with pytest.raises(CatalogValidationError, match="not marked as vision extractable"):
        await service.create_project_work_item(
            project_id=project_id,
            organization_id=test_tenants["org_a"],
            payload=ProjectWorkItemCreate(
                workTypeCode="roof-repair",
                values=[
                    ProjectWorkItemValueInput(parameterCode="work-area-sqm", numberValue=10, sourceType="vision"),
                    ProjectWorkItemValueInput(parameterCode="roof-covering-type", optionValue="bitumen-membrane"),
                    ProjectWorkItemValueInput(parameterCode="damage-type", optionValue="membrane-split", sourceType="vision"),
                    ProjectWorkItemValueInput(parameterCode="access-method", optionValue="roof-ladder", sourceType="vision"),
                ],
            ),
            created_by_user_id="usr_e2e_a1",
        )


async def test_tenant_parameter_override_table_has_expected_uniqueness_and_indexes(db_session):
    override_index_names = {index.name for index in TenantWorkTypeParameterOverride.__table__.indexes}
    extra_index_names = {index.name for index in TenantWorkTypeExtraParameter.__table__.indexes}
    extra_option_index_names = {index.name for index in TenantWorkTypeExtraParameterOption.__table__.indexes}
    assert "idx_tenant_parameter_overrides_org_work_type" in override_index_names
    assert "idx_tenant_parameter_overrides_setting_lookup" in override_index_names
    assert "idx_tenant_extra_parameters_org_work_type_status" in extra_index_names
    assert "idx_tenant_extra_parameter_options_parameter_sort" in extra_option_index_names
    value_index_names = {index.name for index in ProjectWorkItemValue.__table__.indexes}
    assert "idx_project_work_item_values_parameter_lookup" in value_index_names
    assert "idx_project_work_item_values_extra_parameter_lookup" in value_index_names


async def test_effective_work_type_falls_back_to_global_catalog_when_tenant_has_no_override(
    db_session,
    test_tenants,
):
    await _ensure_global_catalog_seed(db_session)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    effective = await service.get_effective_work_type(test_tenants["org_b"], "roof-repair")

    assert effective.code == "roof-repair"
    assert effective.effectiveDisplayName == "Roof Repair"
    assert effective.tenantSetting is None
    assert effective.analysisProfile is not None
    assert effective.catalogPricingProfile is not None


async def test_tenant_extra_parameter_is_resolved_without_leaking_to_other_tenant(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    effective = await service.upsert_tenant_setting(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
        payload=TenantWorkTypeSettingWithParametersUpsert(
            status="enabled",
            extraParameters=[
                {
                    "code": "tenant.internal-priority",
                    "slug": "tenant.internal-priority",
                    "label": "Internal Priority",
                    "dataType": "option",
                    "section": "quantity_scope",
                    "required": False,
                    "defaultOptionCode": "standard",
                    "enumOptions": [
                        {"code": "standard", "label": "Standard"},
                        {"code": "rush", "label": "Rush"},
                    ],
                }
            ],
        ),
        updated_by_user_id="usr_e2e_a1",
    )

    tenant_parameter = next(parameter for parameter in effective.parameters if parameter.code == "tenant.internal-priority")
    assert tenant_parameter.parameterScope == "tenant_extra"
    assert tenant_parameter.defaultOptionCode == "standard"
    assert tenant_parameter.enabled is True
    assert effective.extraParameters[0].code == "tenant.internal-priority"

    other_tenant_effective = await service.get_effective_work_type(test_tenants["org_b"], "roof-repair")
    assert "tenant.internal-priority" not in {parameter.code for parameter in other_tenant_effective.parameters}


async def test_tenant_extra_parameter_defaults_are_materialized_into_runtime_values(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    project_id = await _create_project(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    await service.upsert_tenant_setting(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
        payload=TenantWorkTypeSettingWithParametersUpsert(
            status="enabled",
            extraParameters=[
                {
                    "code": "tenant.internal-priority",
                    "slug": "tenant.internal-priority",
                    "label": "Internal Priority",
                    "dataType": "option",
                    "section": "quantity_scope",
                    "required": True,
                    "defaultOptionCode": "standard",
                    "enumOptions": [
                        {"code": "standard", "label": "Standard"},
                        {"code": "rush", "label": "Rush"},
                    ],
                }
            ],
        ),
        updated_by_user_id="usr_e2e_a1",
    )

    created = await service.create_project_work_item(
        project_id=project_id,
        organization_id=test_tenants["org_a"],
        payload=ProjectWorkItemCreate(
            workTypeCode="roof-repair",
            values=[
                ProjectWorkItemValueInput(parameterCode="work-area-sqm", numberValue=12),
                ProjectWorkItemValueInput(parameterCode="roof-covering-type", optionValue="bitumen-membrane"),
                ProjectWorkItemValueInput(parameterCode="damage-type", optionValue="membrane-split"),
                ProjectWorkItemValueInput(parameterCode="access-method", optionValue="roof-ladder"),
            ],
        ),
        created_by_user_id="usr_e2e_a1",
    )

    tenant_value = next(value for value in created.values if value.parameterCode == "tenant.internal-priority")
    assert tenant_value.parameterScope == "tenant_extra"
    assert tenant_value.optionValue == "standard"
    assert tenant_value.sourceType == "default"
    assert tenant_value.confirmationStatus == "defaulted"


async def test_tenant_extra_parameter_rejects_global_code_collision(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    with pytest.raises(CatalogValidationError, match="collides with a global parameter"):
        await service.upsert_tenant_setting(
            organization_id=test_tenants["org_a"],
            work_type_code="roof-repair",
            payload=TenantWorkTypeSettingWithParametersUpsert(
                status="enabled",
                extraParameters=[
                    {
                        "code": "severity-band",
                        "slug": "tenant.severity-band",
                        "label": "Bad Collision",
                        "dataType": "text",
                        "section": "optional_notes",
                    }
                ],
            ),
            updated_by_user_id="usr_e2e_a1",
        )


async def test_runtime_values_track_source_confidence_and_confirmation_state(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    project_id = await _create_project(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    created = await service.create_project_work_item(
        project_id=project_id,
        organization_id=test_tenants["org_a"],
        payload=ProjectWorkItemCreate(
            workTypeCode="roof-repair",
            sourceType="vision",
            values=[
                ProjectWorkItemValueInput(parameterCode="work-area-sqm", numberValue=8.4, sourceType="vision", sourceConfidence=0.91),
                ProjectWorkItemValueInput(parameterCode="roof-covering-type", optionValue="bitumen-membrane"),
                ProjectWorkItemValueInput(parameterCode="damage-type", optionValue="membrane-split", sourceType="vision", sourceConfidence=0.82),
                ProjectWorkItemValueInput(parameterCode="access-method", optionValue="roof-ladder"),
            ],
        ),
        created_by_user_id="usr_e2e_a1",
    )

    work_area = next(value for value in created.values if value.parameterCode == "work-area-sqm")
    manual_access = next(value for value in created.values if value.parameterCode == "access-method")
    assert created.confirmationStatus == "mixed"
    assert work_area.sourceType == "vision"
    assert work_area.sourceConfidence == 0.91
    assert work_area.confirmationStatus == "pending"
    assert manual_access.sourceType == "manual"
    assert manual_access.confirmationStatus == "confirmed"


async def test_merge_runtime_values_prefers_manual_and_keeps_confirmed_values(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    project_id = await _create_project(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    created = await service.create_project_work_item(
        project_id=project_id,
        organization_id=test_tenants["org_a"],
        payload=ProjectWorkItemCreate(
            workTypeCode="roof-repair",
            values=[
                ProjectWorkItemValueInput(parameterCode="work-area-sqm", numberValue=5.0),
                ProjectWorkItemValueInput(parameterCode="roof-covering-type", optionValue="bitumen-membrane"),
                ProjectWorkItemValueInput(parameterCode="damage-type", optionValue="membrane-split"),
                ProjectWorkItemValueInput(parameterCode="access-method", optionValue="roof-ladder"),
            ],
        ),
        created_by_user_id="usr_e2e_a1",
    )

    merged = await service.merge_project_work_item_values(
        project_id=project_id,
        project_work_item_id=created.id,
        organization_id=test_tenants["org_a"],
        values=[
            ProjectWorkItemValueInput(parameterCode="work-area-sqm", numberValue=11.0, sourceType="vision", sourceConfidence=0.97),
            ProjectWorkItemValueInput(parameterCode="damage-type", optionValue="membrane-puncture", sourceType="vision", sourceConfidence=0.97),
        ],
    )

    work_area = next(value for value in merged.values if value.parameterCode == "work-area-sqm")
    damage_type = next(value for value in merged.values if value.parameterCode == "damage-type")
    assert work_area.numberValue == 5.0
    assert work_area.sourceType == "manual"
    assert damage_type.optionValue == "membrane-split"


async def test_confirm_project_work_item_values_can_correct_pending_vision_value(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    project_id = await _create_project(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    created = await service.create_project_work_item(
        project_id=project_id,
        organization_id=test_tenants["org_a"],
        payload=ProjectWorkItemCreate(
            workTypeCode="roof-repair",
            sourceType="vision",
            values=[
                ProjectWorkItemValueInput(parameterCode="work-area-sqm", numberValue=7.0, sourceType="vision", sourceConfidence=0.72),
                ProjectWorkItemValueInput(parameterCode="roof-covering-type", optionValue="bitumen-membrane"),
                ProjectWorkItemValueInput(parameterCode="damage-type", optionValue="membrane-split", sourceType="vision", sourceConfidence=0.75),
                ProjectWorkItemValueInput(parameterCode="access-method", optionValue="roof-ladder"),
            ],
        ),
        created_by_user_id="usr_e2e_a1",
    )

    confirmed = await service.confirm_project_work_item_values(
        project_id=project_id,
        project_work_item_id=created.id,
        organization_id=test_tenants["org_a"],
        confirmations=[
            ProjectWorkItemValueConfirmationInput(
                parameterCode="work-area-sqm",
                action="correct",
                numberValue=6.5,
                operatorNote="Operator checked ladder shadow and corrected area.",
            ),
            ProjectWorkItemValueConfirmationInput(
                parameterCode="damage-type",
                action="confirm",
            ),
        ],
        confirmed_by_user_id="usr_e2e_a1",
    )

    corrected_area = next(value for value in confirmed.values if value.parameterCode == "work-area-sqm")
    confirmed_damage = next(value for value in confirmed.values if value.parameterCode == "damage-type")
    assert corrected_area.numberValue == 6.5
    assert corrected_area.sourceType == "manual"
    assert corrected_area.confirmationStatus == "corrected"
    assert corrected_area.operatorNote == "Operator checked ladder shadow and corrected area."
    assert confirmed_damage.confirmationStatus == "confirmed"


async def test_get_project_work_item_detail_enforces_project_and_tenant_scope(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    project_id = await _create_project(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    created = await service.create_project_work_item(
        project_id=project_id,
        organization_id=test_tenants["org_a"],
        payload=ProjectWorkItemCreate(
            workTypeCode="roof-repair",
            values=[
                ProjectWorkItemValueInput(parameterCode="work-area-sqm", numberValue=4.5),
                ProjectWorkItemValueInput(parameterCode="roof-covering-type", optionValue="bitumen-membrane"),
                ProjectWorkItemValueInput(parameterCode="damage-type", optionValue="membrane-split"),
                ProjectWorkItemValueInput(parameterCode="access-method", optionValue="roof-ladder"),
            ],
        ),
        created_by_user_id="usr_e2e_a1",
    )

    detail = await service.get_project_work_item_detail(
        project_id=project_id,
        project_work_item_id=created.id,
        organization_id=test_tenants["org_a"],
    )
    assert detail.workItem.id == created.id
    assert detail.effectiveConfiguration.workTypeCode == created.workTypeCode
    assert detail.workflow.supportsPricing is True

    with pytest.raises(WorkCatalogNotFoundError):
        await service.get_project_work_item_detail(
            project_id=project_id,
            project_work_item_id=created.id,
            organization_id=test_tenants["org_b"],
        )


async def test_catalog_read_models_expose_global_detail_without_tenant_override_data(
    db_session,
):
    await _ensure_global_catalog_seed(db_session)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    categories = await service.list_categories()
    work_types = await service.list_work_types_global()
    detail = await service.get_work_type_detail("roof-repair")
    parameter_detail = await service.get_parameter_schema_detail(
        work_type_code="roof-repair",
        parameter_code="work-area-sqm",
    )

    assert any(category.code == "roofing" for category in categories)
    assert any(work_type.code == "roof-repair" for work_type in work_types)
    assert detail.code == "roof-repair"
    assert detail.supportsVision is True
    assert detail.supportsPricing is True
    assert parameter_detail.parameter.code == "work-area-sqm"
    assert parameter_detail.supportsVisionPopulation is True
    assert parameter_detail.supportsPricingInput is True


async def test_project_effective_configuration_includes_vision_and_pricing_workflow_surfaces(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    project_id = await _create_project(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    configuration = await service.get_project_work_item_effective_configuration(
        project_id=project_id,
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
    )

    assert configuration.workTypeCode == "roof-repair"
    assert configuration.effectiveWorkType.tenantSetting is not None
    assert configuration.effectiveWorkType.tenantPricingProfileId == test_tenants["pricebook_a"]
    assert "work-area-sqm" in configuration.requiredParameterCodes
    assert "work-area-sqm" in configuration.vision.extractableParameterCodes
    assert configuration.pricing.supported is True
    assert "work-area-sqm" in configuration.pricing.parameterInputCodes
