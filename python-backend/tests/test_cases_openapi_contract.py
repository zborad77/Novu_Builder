import pytest


async def test_cases_list_does_not_expose_unsupported_updated_filters(app_client):
    response = await app_client.get("/openapi.json")
    assert response.status_code == 200

    params = response.json()["paths"]["/api/v1/cases"]["get"]["parameters"]
    names = {param["name"] for param in params}

    assert "updated_from" not in names
    assert "updated_to" not in names


async def test_forgot_password_does_not_expose_retired_request_body(app_client):
    response = await app_client.get("/openapi.json")
    assert response.status_code == 200

    operation = response.json()["paths"]["/api/v1/auth/forgot-password"]["post"]
    assert "requestBody" not in operation


async def test_reset_password_does_not_expose_retired_request_body(app_client):
    response = await app_client.get("/openapi.json")
    assert response.status_code == 200

    operation = response.json()["paths"]["/api/v1/auth/reset-password"]["post"]
    assert "requestBody" not in operation


@pytest.mark.parametrize(
    ("path", "expected_query_params"),
    [
        ("/api/v1/cases", {"status", "search", "org_id", "limit", "cursor"}),
        ("/api/v1/cases/{case_id}/timeline", set()),
        ("/api/v1/cases/{case_id}/analysis-jobs", set()),
        ("/api/v1/cases/{case_id}/estimates", set()),
        ("/api/v1/cases/{case_id}/images", set()),
        ("/api/v1/material-catalog", {"search", "includeInactive"}),
        ("/api/v1/material-catalog/{material_id}/supplier-prices", set()),
        ("/api/v1/suppliers", {"includeInactive"}),
        ("/api/v1/pricebooks", set()),
        ("/api/v1/pricebooks/{pricebook_id}/items", set()),
        ("/api/v1/admin/companies", {"limit", "offset"}),
        ("/api/v1/admin/users", {"org_id", "limit", "offset"}),
        ("/api/v1/admin/jobs", {"status", "org_id", "limit", "offset"}),
        ("/api/v1/admin/logs", {"lines"}),
        ("/api/v1/admin/audit", {"org_id", "action", "user_id", "limit"}),
    ],
)
async def test_list_endpoints_expose_only_expected_query_params(
    app_client,
    path,
    expected_query_params,
):
    response = await app_client.get("/openapi.json")
    assert response.status_code == 200

    operation = response.json()["paths"][path]["get"]
    query_params = {
        param["name"]
        for param in operation.get("parameters", [])
        if param.get("in") == "query"
    }

    assert query_params == expected_query_params
