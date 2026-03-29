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
