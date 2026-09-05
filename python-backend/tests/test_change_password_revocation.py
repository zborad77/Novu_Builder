# =============================================================================
# Change-password token revocation tests
#
# Verify that POST /auth/change-password invalidates all previously issued
# access tokens for that user.
#
# Uses a dedicated function-scoped user so that session-scoped token_a/token_b
# fixtures used by other tests are never affected.
# =============================================================================
import pytest
import pytest_asyncio

from app.models import User
from app.services.auth_service import hash_password

_PW_USER_ID = "usr_pw_change_test"
_PW_USER_EMAIL = "pw_change_test@test.local"
_PW_ORIGINAL = "OriginalPass99!"
_PW_NEW = "NewSecurePass99!"


@pytest_asyncio.fixture()
async def pw_user(app_client, test_tenants, db_session_factory):
    """Create a dedicated user for password change tests; delete after each test."""
    async with db_session_factory() as session:
        existing = await session.get(User, _PW_USER_ID)
        if existing:
            await session.delete(existing)
            await session.commit()
        session.add(User(
            id=_PW_USER_ID,
            organization_id="org_e2e_a",
            email=_PW_USER_EMAIL,
            password_hash=hash_password(_PW_ORIGINAL),
            full_name="PW Change Test User",
            role="manager",
            is_active=True,
            is_superadmin=False,
        ))
        await session.commit()

    yield {"email": _PW_USER_EMAIL, "password": _PW_ORIGINAL}

    async with db_session_factory() as session:
        user = await session.get(User, _PW_USER_ID)
        if user:
            await session.delete(user)
            await session.commit()


@pytest_asyncio.fixture()
async def pw_session(app_client, pw_user):
    """Fresh access token for the dedicated password-change test user."""
    resp = await app_client.post("/api/v1/auth/login", json=pw_user)
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["accessToken"]


class TestChangePasswordRevocation:
    async def test_old_access_token_rejected_after_password_change(
        self, app_client, pw_user, pw_session
    ):
        old_token = pw_session

        # Token must be valid before the change
        resp = await app_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert resp.status_code == 200, "Token should be valid before password change"

        # Change password
        resp = await app_client.post(
            "/api/v1/auth/change-password",
            json={"currentPassword": pw_user["password"], "newPassword": _PW_NEW},
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert resp.status_code == 200, f"Change password failed: {resp.text}"

        # Old token must now be rejected
        resp = await app_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert resp.status_code == 401, (
            f"Old token must be rejected after password change, got {resp.status_code}"
        )

    async def test_login_with_new_password_works_after_change(
        self, app_client, pw_user, pw_session
    ):
        old_token = pw_session

        resp = await app_client.post(
            "/api/v1/auth/change-password",
            json={"currentPassword": pw_user["password"], "newPassword": _PW_NEW},
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert resp.status_code == 200

        # Login with new password must succeed
        resp = await app_client.post("/api/v1/auth/login", json={
            "email": pw_user["email"], "password": _PW_NEW,
        })
        assert resp.status_code == 200, f"Login with new password failed: {resp.text}"

        # New token must work
        new_token = resp.json()["accessToken"]
        resp = await app_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert resp.status_code == 200

    async def test_failed_password_change_does_not_invalidate_token(
        self, app_client, pw_user, pw_session
    ):
        old_token = pw_session

        # Wrong current password → change must fail
        resp = await app_client.post(
            "/api/v1/auth/change-password",
            json={"currentPassword": "WrongPassword99!", "newPassword": _PW_NEW},
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

        # Token must still be valid
        resp = await app_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert resp.status_code == 200, (
            f"Token must remain valid after failed change, got {resp.status_code}"
        )
