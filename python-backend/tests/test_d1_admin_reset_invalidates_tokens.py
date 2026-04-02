"""D1 Regression: Admin password reset invalidates pre-existing JWT tokens.

Covers the full integration path that test_admin_hardening.py only verified
at the source/mock level:

  1. Superadmin calls POST /admin/users/{id}/reset-password
  2. The target user's tokens_valid_after is bumped to NOW
  3. A token issued BEFORE that moment returns 401 on GET /auth/me
  4. The target user CAN log in with the new password and get a fresh token

This test uses real HTTP (AsyncClient + ASGI), real DB (SQLite test session),
and real JWT decode/verify — no mocks.
"""
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
import pytest_asyncio

# ── Fixtures ────────────────────────────────────────────────────────────────

_TestSession = None  # resolved lazily inside fixtures


def _get_session_factory():
    global _TestSession
    if _TestSession is None:
        from tests.conftest import _TestSession as _TS  # noqa: PLC0415
        _TestSession = _TS
    return _TestSession


@pytest_asyncio.fixture
async def superadmin_for_reset(app_client):
    """Function-scoped throwaway superadmin for admin-reset tests."""
    from app.models import User
    from app.services.auth_service import hash_password

    uid = f"usr_sa_{uuid.uuid4().hex[:8]}"
    email = f"superadmin_{uid}@test.local"
    TS = _get_session_factory()
    async with TS() as session:
        session.add(User(
            id=uid,
            organization_id="org_e2e_a",
            email=email,
            password_hash=hash_password("AdminPass@1!"),
            full_name="Test Superadmin",
            role="superadmin",
            is_active=True,
            is_superadmin=True,
        ))
        await session.commit()

    resp = await app_client.post("/api/v1/auth/login", json={"email": email, "password": "AdminPass@1!"})
    assert resp.status_code == 200, f"Superadmin login failed: {resp.text}"
    token = resp.json()["accessToken"]

    yield {"user_id": uid, "token": token}

    TS = _get_session_factory()
    async with TS() as session:
        user = await session.get(User, uid)
        if user:
            await session.delete(user)
            await session.commit()


@pytest_asyncio.fixture
async def target_user_with_old_token(app_client):
    """Function-scoped user whose token we will try to invalidate."""
    from app.models import User
    from app.services.auth_service import hash_password

    uid = f"usr_tgt_{uuid.uuid4().hex[:8]}"
    email = f"target_{uid}@test.local"
    original_password = "OriginalPass@1!"
    TS = _get_session_factory()
    async with TS() as session:
        session.add(User(
            id=uid,
            organization_id="org_e2e_a",
            email=email,
            password_hash=hash_password(original_password),
            full_name="Target User",
            role="manager",
            is_active=True,
            is_superadmin=False,
        ))
        await session.commit()

    resp = await app_client.post("/api/v1/auth/login", json={"email": email, "password": original_password})
    assert resp.status_code == 200, f"Target user login failed: {resp.text}"
    old_token = resp.json()["accessToken"]

    yield {"user_id": uid, "email": email, "old_token": old_token, "original_password": original_password}

    TS = _get_session_factory()
    async with TS() as session:
        user = await session.get(User, uid)
        if user:
            await session.delete(user)
            await session.commit()


# ── Tests ───────────────────────────────────────────────────────────────────

class TestAdminResetInvalidatesOldTokens:

    @pytest.mark.asyncio
    async def test_old_token_valid_before_reset(self, app_client, target_user_with_old_token):
        """Sanity: before admin reset, the old token works fine."""
        resp = await app_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {target_user_with_old_token['old_token']}"},
        )
        assert resp.status_code == 200, f"Old token should be valid before reset: {resp.text}"

    @pytest.mark.asyncio
    async def test_admin_reset_rejects_old_token(
        self, app_client, superadmin_for_reset, target_user_with_old_token
    ):
        """After admin reset, the pre-existing access token returns 401."""
        new_password = "NewAdminSet@Pass1!"
        target_id = target_user_with_old_token["user_id"]
        old_token = target_user_with_old_token["old_token"]

        # Admin resets the password
        resp = await app_client.post(
            f"/api/v1/admin/users/{target_id}/reset-password",
            json={"password": new_password},
            headers={"Authorization": f"Bearer {superadmin_for_reset['token']}"},
        )
        assert resp.status_code == 204, f"Admin reset failed: {resp.text}"

        # Old token must now be rejected
        resp = await app_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert resp.status_code == 401, (
            f"Old token must be invalid after admin password reset, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_admin_reset_rejects_old_token_issued_in_same_second(
        self, app_client, superadmin_for_reset, target_user_with_old_token
    ):
        """Same-second issuance no longer bypasses invalidation because version is authoritative."""

        frozen_now = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)

        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is None:
                    return frozen_now.replace(tzinfo=None)
                return frozen_now.astimezone(tz)

        target_id = target_user_with_old_token["user_id"]
        email = target_user_with_old_token["email"]

        with (
            patch("app.services.auth_service.datetime", FrozenDateTime),
            patch("app.api.routes.admin.datetime", FrozenDateTime),
        ):
            login_resp = await app_client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": target_user_with_old_token["original_password"]},
            )
            assert login_resp.status_code == 200, f"Login failed under frozen time: {login_resp.text}"
            old_token = login_resp.json()["accessToken"]

            reset_resp = await app_client.post(
                f"/api/v1/admin/users/{target_id}/reset-password",
                json={"password": "SameSecondReset@Pass1!"},
                headers={"Authorization": f"Bearer {superadmin_for_reset['token']}"},
            )
            assert reset_resp.status_code == 204, f"Admin reset failed: {reset_resp.text}"

        resp = await app_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert resp.status_code == 401, (
            f"Same-second token must be invalid after admin reset, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_new_password_works_after_admin_reset(
        self, app_client, superadmin_for_reset, target_user_with_old_token
    ):
        """After admin reset, the target user can log in with the NEW password."""
        new_password = "NewAdminSet@Pass1v2!"
        target_id = target_user_with_old_token["user_id"]
        email = target_user_with_old_token["email"]

        # Admin sets new password
        resp = await app_client.post(
            f"/api/v1/admin/users/{target_id}/reset-password",
            json={"password": new_password},
            headers={"Authorization": f"Bearer {superadmin_for_reset['token']}"},
        )
        assert resp.status_code == 204, f"Admin reset failed: {resp.text}"

        # New password works
        resp = await app_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": new_password},
        )
        assert resp.status_code == 200, f"Login with new password failed: {resp.text}"
        new_token = resp.json()["accessToken"]

        # New token is immediately usable
        resp = await app_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert resp.status_code == 200, f"New token should be valid: {resp.text}"

    @pytest.mark.asyncio
    async def test_old_password_rejected_after_admin_reset(
        self, app_client, superadmin_for_reset, target_user_with_old_token
    ):
        """After admin reset, the OLD password no longer works for login."""
        new_password = "NewAdminSet@Pass1v3!"
        target_id = target_user_with_old_token["user_id"]
        email = target_user_with_old_token["email"]
        old_password = target_user_with_old_token["original_password"]

        resp = await app_client.post(
            f"/api/v1/admin/users/{target_id}/reset-password",
            json={"password": new_password},
            headers={"Authorization": f"Bearer {superadmin_for_reset['token']}"},
        )
        assert resp.status_code == 204, f"Admin reset failed: {resp.text}"

        # Old password must no longer work
        resp = await app_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": old_password},
        )
        assert resp.status_code == 401, (
            f"Old password must be invalid after admin reset, got {resp.status_code}"
        )
