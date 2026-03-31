from __future__ import annotations

from uuid import uuid4

import pytest

from app.models import TenantWorkTypeParameterOverride
from app.repositories.work_catalog_repository import WorkCatalogRepository
from app.schemas.work_catalog import TenantWorkTypeSettingWithParametersUpsert
from app.services.tenant_work_type_resolution_service import TenantWorkTypeResolutionService
from app.services.work_catalog_service import WorkCatalogService
from app.work_catalog.domain import CatalogValidationError
from tests.test_work_catalog_core_subsystem import _ensure_global_catalog_seed, _ensure_tenant_setting


async def test_effective_work_type_contract_snapshot_is_deterministic(
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
                    "overrideStatus": "optional",
                    "customDisplayName": "Zavaznost opravy",
                    "sortOrderOverride": 25,
                }
            ],
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
                        {"code": "standard", "label": "Standard", "sortOrder": 10},
                        {"code": "rush", "label": "Rush", "sortOrder": 20},
                    ],
                }
            ],
        ),
        updated_by_user_id="usr_e2e_a1",
    )

    snapshot = {
        "effective_display_name": effective.effectiveDisplayName,
        "section_order": [section.code for section in effective.parameterSections],
        "override_codes": [override.parameterCode for override in effective.parameterOverrides],
        "extra_codes": [parameter.code for parameter in effective.extraParameters],
        "extra_statuses": {parameter.code: parameter.status for parameter in effective.extraParameters},
        "parameter_order": [parameter.code for parameter in effective.parameters[:8]],
    }

    assert snapshot == {
        "effective_display_name": "Tenant A Crack Repair",
        "section_order": [
            "dimensions",
            "materials",
            "condition_or_damage",
            "access_and_complexity",
            "quantity_scope",
            "optional_notes",
        ],
        "override_codes": ["severity-band"],
        "extra_codes": ["tenant.internal-priority"],
        "extra_statuses": {"tenant.internal-priority": "active"},
        "parameter_order": [
            "roof-pitch-deg",
            "roof-covering-type",
            "severity-band",
            "damage-type",
            "access-method",
            "work-area-sqm",
            "repair-zones-count",
            "tenant.internal-priority",
        ],
    }


async def test_resolution_service_exposes_stable_read_views_for_effective_configuration(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))
    await service.upsert_tenant_setting(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
        payload=TenantWorkTypeSettingWithParametersUpsert(
            status="enabled",
            customDisplayName="Tenant A Crack Repair",
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

    resolution_service = TenantWorkTypeResolutionService(WorkCatalogRepository(db_session))
    resolved = await resolution_service.resolve_for_work_type(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
    )

    assert resolved.effective_display_name == "Tenant A Crack Repair"
    assert [parameter.code for parameter in resolved.extra_parameter_definitions] == [
        "tenant.internal-priority"
    ]
    assert list(resolved.parameter_by_code()) == [parameter.code for parameter in resolved.parameters]


async def test_upsert_tenant_setting_rejects_duplicate_parameter_override_payloads(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    with pytest.raises(CatalogValidationError, match="Duplicate parameter override payload"):
        await service.upsert_tenant_setting(
            organization_id=test_tenants["org_a"],
            work_type_code="roof-repair",
            payload=TenantWorkTypeSettingWithParametersUpsert(
                status="enabled",
                parameterOverrides=[
                    {"parameterCode": "severity-band", "overrideStatus": "optional"},
                    {"parameterCode": "severity-band", "overrideStatus": "hidden"},
                ],
            ),
            updated_by_user_id="usr_e2e_a1",
        )


async def test_upsert_tenant_setting_rejects_duplicate_extra_parameter_payload_codes_and_slugs(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    service = WorkCatalogService(WorkCatalogRepository(db_session))

    with pytest.raises(CatalogValidationError, match="Duplicate tenant extra parameter code"):
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
                        "dataType": "text",
                        "section": "optional_notes",
                    },
                    {
                        "code": "tenant.internal-priority",
                        "slug": "tenant.internal-priority-2",
                        "label": "Internal Priority Copy",
                        "dataType": "text",
                        "section": "optional_notes",
                    },
                ],
            ),
            updated_by_user_id="usr_e2e_a1",
        )

    with pytest.raises(CatalogValidationError, match="Duplicate tenant extra parameter slug"):
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
                        "dataType": "text",
                        "section": "optional_notes",
                    },
                    {
                        "code": "tenant.priority-second",
                        "slug": "tenant.internal-priority",
                        "label": "Internal Priority Copy",
                        "dataType": "text",
                        "section": "optional_notes",
                    },
                ],
            ),
            updated_by_user_id="usr_e2e_a1",
        )


async def test_resolution_fails_closed_when_override_scope_is_inconsistent(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    await _ensure_global_catalog_seed(db_session)
    override = await db_session.get(
        TenantWorkTypeParameterOverride,
        "twpo_test_org_a_roof_repair_severity",
    )
    assert override is not None

    repository = WorkCatalogRepository(db_session)
    other_work_type = next(
        work_type
        for work_type in await repository.list_work_types()
        if work_type.code != "roof-repair"
    )
    service = WorkCatalogService(repository)
    await service.upsert_tenant_setting(
        organization_id=test_tenants["org_a"],
        work_type_code=other_work_type.code,
        payload=TenantWorkTypeSettingWithParametersUpsert(status="enabled"),
        updated_by_user_id="usr_e2e_a1",
    )
    other_setting = (
        await repository.list_tenant_settings_for_org(
            test_tenants["org_a"],
            work_type_ids=[other_work_type.id],
        )
    )[other_work_type.id]
    override.tenant_work_type_setting_id = other_setting.id
    override.updated_by_user_id = f"usr_scope_{uuid4().hex[:8]}"
    await db_session.commit()

    resolution_service = TenantWorkTypeResolutionService(repository)
    with pytest.raises(CatalogValidationError, match="not attached to the active tenant setting"):
        await resolution_service.resolve_for_work_type(
            organization_id=test_tenants["org_a"],
            work_type_code="roof-repair",
        )
