from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    AnalysisProfile,
    CatalogPricingProfile,
    Project,
    ProjectWorkItemValue,
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
    ProjectWorkItemValueInput,
    TenantWorkTypeSettingUpsert,
    TenantWorkTypeSettingWithParametersUpsert,
)
from app.services.work_catalog_service import WorkCatalogService
from app.work_catalog.domain import CatalogValidationError
from app.work_catalog.seeds import GLOBAL_WORK_CATALOG_SEED


async def _ensure_global_catalog_seed(db_session) -> None:
    model_by_key = {
        "categories": WorkCategory,
        "analysis_profiles": AnalysisProfile,
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


async def _ensure_tenant_setting(db_session, test_tenants) -> None:
    await _ensure_global_catalog_seed(db_session)
    row_id = "twts_test_org_a_roof_repair"
    if await db_session.get(TenantWorkTypeSetting, row_id) is None:
        db_session.add(
            TenantWorkTypeSetting(
                id=row_id,
                organization_id=test_tenants["org_a"],
                work_type_id="wt_roof_repair",
                status="enabled",
                custom_display_name="Tenant A Crack Repair",
                catalog_pricing_profile_id="cpp_surface_repair_standard_v1",
                tenant_pricing_profile_id=test_tenants["pricebook_a"],
                config_version=1,
            )
        )
        await db_session.commit()
    parameter_override_id = "twpo_test_org_a_roof_repair_severity"
    if await db_session.get(TenantWorkTypeParameterOverride, parameter_override_id) is None:
        db_session.add(
            TenantWorkTypeParameterOverride(
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
        )
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
    hidden = await service.list_project_work_items(project_id=project_id, organization_id=test_tenants["org_b"])

    assert [item.id for item in visible] == [created.id]
    assert hidden == []


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
            catalogPricingProfileCode="surface-repair-standard-v1",
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
    assert "idx_tenant_parameter_overrides_org_work_type" in override_index_names
    assert "idx_tenant_parameter_overrides_setting_lookup" in override_index_names
    value_index_names = {index.name for index in ProjectWorkItemValue.__table__.indexes}
    assert "idx_project_work_item_values_parameter_lookup" in value_index_names
