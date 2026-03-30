from unittest.mock import AsyncMock, patch

import pytest

from app.main import create_app


async def test_create_app_lifespan_startup_smoke():
    app = create_app()

    async with app.router.lifespan_context(app):
        assert app.state.startup_checks == {
            "database": "ok",
            "schema": "ok",
            "storage": "ok",
        }


async def test_create_app_lifespan_fails_fast_when_storage_validation_fails_in_production():
    app = create_app()

    with (
        patch("app.main.verify_storage_health", new=AsyncMock(side_effect=RuntimeError("s3 down"))),
        patch("app.main._is_strict_startup_environment", return_value=True),
    ):
        with pytest.raises(RuntimeError, match="storage"):
            async with app.router.lifespan_context(app):
                pass


async def test_openapi_smoke_exposes_key_runtime_paths(app_client):
    response = await app_client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json()["paths"]

    assert "/api/v1/health" in paths
    assert "get" in paths["/api/v1/health"]
    assert "/api/v1/ready" in paths
    assert "get" in paths["/api/v1/ready"]

    assert "/api/v1/cases" in paths
    assert "get" in paths["/api/v1/cases"]
    assert "post" in paths["/api/v1/cases"]

    assert "/api/v1/cases/{case_id}" in paths
    assert "get" in paths["/api/v1/cases/{case_id}"]

    assert "/api/v1/pricebooks" in paths
    assert "get" in paths["/api/v1/pricebooks"]

    assert "/api/v1/material-catalog" in paths
    assert "get" in paths["/api/v1/material-catalog"]

    assert "/api/v1/auth/me" in paths
    assert "get" in paths["/api/v1/auth/me"]


async def test_health_and_alive_smoke(app_client):
    alive = await app_client.get("/api/v1/alive")
    assert alive.status_code == 200
    assert alive.json() == {"status": "alive"}

    health = await app_client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "service": "python-backend"}

    ready = await app_client.get("/api/v1/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "service": "python-backend"}


async def test_auth_me_requires_bearer_token(app_client):
    response = await app_client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_auth_me_smoke_with_valid_token(app_client, token_a):
    response = await app_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["email"] == "manager_a@test.local"
    assert body["organizationId"] == "org_e2e_a"
    assert body["isSuperAdmin"] is False


async def test_cases_list_and_detail_smoke(app_client, token_a, case_a_id):
    headers = {"Authorization": f"Bearer {token_a}"}

    list_response = await app_client.get("/api/v1/cases", headers=headers)
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert isinstance(list_body["items"], list)
    assert any(item["id"] == case_a_id for item in list_body["items"])

    detail_response = await app_client.get(f"/api/v1/cases/{case_a_id}", headers=headers)
    assert detail_response.status_code == 200
    detail_body = detail_response.json()
    assert detail_body["id"] == case_a_id
    assert "workflowStatus" in detail_body
