from uuid import uuid4

from tests.test_work_catalog_core_subsystem import _ensure_tenant_setting


async def _create_case(app_client, token: str, *, title: str) -> str:
    response = await app_client.post(
        "/api/v1/cases",
        json={"title": title},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_work_catalog_read_endpoints_expose_global_and_tenant_effective_surfaces(
    app_client,
    db_session,
    test_tenants,
    token_a,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    headers = {"Authorization": f"Bearer {token_a}"}

    categories_response = await app_client.get("/api/v1/work-catalog/catalog/categories", headers=headers)
    assert categories_response.status_code == 200, categories_response.text
    categories_body = categories_response.json()
    roofing_category = next(item for item in categories_body["items"] if item["code"] == "roofing")
    assert roofing_category["activeWorkTypeCount"] >= 1

    work_types_response = await app_client.get("/api/v1/work-catalog/catalog/work-types", headers=headers)
    assert work_types_response.status_code == 200, work_types_response.text
    work_types_body = work_types_response.json()
    roof_repair_summary = next(item for item in work_types_body["items"] if item["code"] == "roof-repair")
    assert roof_repair_summary["supportsVision"] is True
    assert roof_repair_summary["supportsPricing"] is True

    work_type_detail_response = await app_client.get(
        "/api/v1/work-catalog/catalog/work-types/roof-repair",
        headers=headers,
    )
    assert work_type_detail_response.status_code == 200, work_type_detail_response.text
    work_type_detail = work_type_detail_response.json()
    assert work_type_detail["analysisProfile"]["code"].startswith("roof-repair-")
    assert work_type_detail["catalogPricingProfile"]["code"].startswith("roof-repair-")

    parameter_detail_response = await app_client.get(
        "/api/v1/work-catalog/catalog/work-types/roof-repair/parameters/work-area-sqm",
        headers=headers,
    )
    assert parameter_detail_response.status_code == 200, parameter_detail_response.text
    parameter_detail = parameter_detail_response.json()
    assert parameter_detail["parameter"]["code"] == "work-area-sqm"
    assert parameter_detail["supportsVisionPopulation"] is True
    assert parameter_detail["supportsPricingInput"] is True

    effective_detail_response = await app_client.get(
        "/api/v1/work-catalog/work-types/roof-repair/effective",
        headers=headers,
    )
    assert effective_detail_response.status_code == 200, effective_detail_response.text
    effective_detail = effective_detail_response.json()
    assert effective_detail["tenantSetting"] is not None
    assert effective_detail["tenantPricingProfileId"] == test_tenants["pricebook_a"]


async def test_project_work_item_api_flow_returns_effective_configuration_and_operator_workflow(
    app_client,
    db_session,
    test_tenants,
    token_a,
    token_b,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    case_id = await _create_case(
        app_client,
        token_a,
        title=f"Work Catalog API Flow {uuid4().hex[:8]}",
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    effective_config_response = await app_client.get(
        f"/api/v1/cases/{case_id}/work-types/roof-repair/effective-configuration",
        headers=headers_a,
    )
    assert effective_config_response.status_code == 200, effective_config_response.text
    effective_config = effective_config_response.json()
    assert effective_config["effectiveWorkType"]["tenantSetting"] is not None
    assert effective_config["effectiveWorkType"]["tenantPricingProfileId"] == test_tenants["pricebook_a"]
    assert "work-area-sqm" in effective_config["requiredParameterCodes"]
    assert "work-area-sqm" in effective_config["vision"]["extractableParameterCodes"]
    assert effective_config["pricing"]["supported"] is True

    create_work_item_response = await app_client.post(
        f"/api/v1/cases/{case_id}/work-items",
        json={
            "workTypeCode": "roof-repair",
            "sourceType": "vision",
            "values": [
                {"parameterCode": "work-area-sqm", "numberValue": 12.4, "sourceType": "vision", "sourceConfidence": 0.88},
                {"parameterCode": "roof-covering-type", "optionValue": "bitumen-membrane"},
                {"parameterCode": "damage-type", "optionValue": "membrane-split", "sourceType": "vision", "sourceConfidence": 0.82},
                {"parameterCode": "access-method", "optionValue": "roof-ladder"},
            ],
        },
        headers=headers_a,
    )
    assert create_work_item_response.status_code == 200, create_work_item_response.text
    work_item = create_work_item_response.json()
    assert work_item["confirmationStatus"] == "mixed"
    work_item_id = work_item["id"]

    work_item_detail_response = await app_client.get(
        f"/api/v1/cases/{case_id}/work-items/{work_item_id}",
        headers=headers_a,
    )
    assert work_item_detail_response.status_code == 200, work_item_detail_response.text
    work_item_detail = work_item_detail_response.json()
    assert work_item_detail["workItem"]["id"] == work_item_id
    assert set(work_item_detail["workflow"]["pendingConfirmationParameterCodes"]) == {
        "damage-type",
        "work-area-sqm",
    }
    assert work_item_detail["workflow"]["supportsVision"] is True
    assert work_item_detail["workflow"]["supportsPricing"] is True

    confirm_response = await app_client.post(
        f"/api/v1/cases/{case_id}/work-items/{work_item_id}/values/confirm",
        json=[
            {
                "parameterCode": "work-area-sqm",
                "action": "correct",
                "numberValue": 11.8,
                "operatorNote": "Operator corrected foreshortened vision estimate.",
            },
            {
                "parameterCode": "damage-type",
                "action": "confirm",
            },
        ],
        headers=headers_a,
    )
    assert confirm_response.status_code == 200, confirm_response.text
    confirmed_work_item = confirm_response.json()
    assert confirmed_work_item["confirmationStatus"] == "confirmed"

    confirmed_detail_response = await app_client.get(
        f"/api/v1/cases/{case_id}/work-items/{work_item_id}",
        headers=headers_a,
    )
    assert confirmed_detail_response.status_code == 200, confirmed_detail_response.text
    confirmed_detail = confirmed_detail_response.json()
    assert confirmed_detail["workflow"]["canConfirmValues"] is False
    assert confirmed_detail["workflow"]["pendingConfirmationParameterCodes"] == []

    cross_tenant_detail_response = await app_client.get(
        f"/api/v1/cases/{case_id}/work-items/{work_item_id}",
        headers=headers_b,
    )
    assert cross_tenant_detail_response.status_code == 404

    cross_tenant_config_response = await app_client.get(
        f"/api/v1/cases/{case_id}/work-types/roof-repair/effective-configuration",
        headers=headers_b,
    )
    assert cross_tenant_config_response.status_code == 404
