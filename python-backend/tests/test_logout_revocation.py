# =============================================================================
# Logout revocation tests
#
# Verify that POST /auth/logout revokes BOTH the refresh token and the
# access token supplied in the Authorization header.
# =============================================================================
import pytest
import pytest_asyncio


@pytest_asyncio.fixture()
async def logout_session(app_client, test_tenants):
    """Fresh login returning both tokens — function-scoped so revocation
    does not pollute other tests that reuse the session-scoped tokens."""
    resp = await app_client.post("/api/v1/auth/login", json=test_tenants["user_a"])
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    return data["accessToken"], data["refreshToken"]


class TestLogoutRevocation:
    async def test_logout_revokes_refresh_token(self, app_client, logout_session):
        access_token, refresh_token = logout_session
        resp = await app_client.post(
            "/api/v1/auth/logout",
            json={"refreshToken": refresh_token},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp.status_code == 200

        # Attempting to use the revoked refresh token must fail
        resp = await app_client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": refresh_token},
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"

    async def test_logout_revokes_access_token(self, app_client, logout_session):
        access_token, refresh_token = logout_session
        resp = await app_client.post(
            "/api/v1/auth/logout",
            json={"refreshToken": refresh_token},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp.status_code == 200

        # Access token must be rejected on a protected endpoint
        resp = await app_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"

    async def test_logout_without_authorization_header_still_revokes_refresh_token(
        self, app_client, logout_session
    ):
        access_token, refresh_token = logout_session
        # Logout without sending the access token — refresh token must still be revoked
        resp = await app_client.post(
            "/api/v1/auth/logout",
            json={"refreshToken": refresh_token},
        )
        assert resp.status_code == 200

        resp = await app_client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": refresh_token},
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
