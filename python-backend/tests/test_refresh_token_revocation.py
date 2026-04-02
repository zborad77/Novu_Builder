# =============================================================================
# Refresh token revocation — global token invalidation guard
#
# Verifies that AuthService.refresh() rejects refresh tokens invalidated by the
# global token-version guard, while preserving a legacy tokens_valid_after
# fallback for pre-version tokens during rollout.
#
# Tests are structured in two layers:
#   1. Unit tests (mocked) — fast, no DB, cover the guard logic directly
#   2. E2E integration test — real DB + ASGI client, exercises the full flow
# =============================================================================
import os
from datetime import UTC, datetime, timedelta

import jwt
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import AsyncMock, MagicMock

from app.models import User
from app.repositories.token_repository import TOKEN_STATE_ACTIVE, TOKEN_STATE_REVOKED
from app.services.auth_service import AuthService, hash_password


# ── Unit-level helpers ────────────────────────────────────────────────────────

_JWT_SECRET = "test-e2e-jwt-secret-x99-32bytes-min"
_JWT_ALGO = "HS256"
_REFRESH_TTL_DAYS = 30


def _encode_refresh_token(user_id: str, issued_offset_seconds: int = 0, *, version: int | None = 0) -> str:
    """Encode a minimal refresh token whose iat is NOW + offset."""
    now = datetime.now(UTC)
    iat = now + timedelta(seconds=issued_offset_seconds)
    exp = iat + timedelta(days=_REFRESH_TTL_DAYS)
    payload = {"sub": user_id, "jti": "test-jti-1", "type": "refresh", "exp": exp}
    if version is not None:
        payload["ver"] = version
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGO)


def _make_settings(refresh_days: int = _REFRESH_TTL_DAYS) -> MagicMock:
    s = MagicMock()
    s.jwt_secret = _JWT_SECRET
    s.jwt_algorithm = _JWT_ALGO
    s.jwt_refresh_token_expire_days = refresh_days
    s.jwt_access_token_expire_minutes = 15
    return s


def _make_user(*, tokens_valid_after=None, token_version: int = 0) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = "usr_test_1"
    u.is_active = True
    u.tokens_valid_after = tokens_valid_after
    u.token_version = token_version
    u.email = "test@test.local"
    u.full_name = "Test User"
    u.role = "manager"
    u.organization_id = "org_test"
    u.is_superadmin = False
    return u


def _make_auth_service(user: MagicMock) -> AuthService:
    mock_session = MagicMock()
    mock_session.get = AsyncMock(return_value=user)
    mock_session.commit = AsyncMock()

    mock_tokens = MagicMock()
    mock_tokens.get_token_state = AsyncMock(return_value=TOKEN_STATE_ACTIVE)
    mock_tokens.revoke = AsyncMock()
    mock_tokens.revoke_with_commit = AsyncMock()
    mock_tokens.cache_revoked_token = AsyncMock()
    mock_tokens.create_user_session = AsyncMock()
    mock_tokens.rotate_user_session = AsyncMock()

    service = AuthService.__new__(AuthService)
    service.session = mock_session
    service._settings = _make_settings()
    service._tokens = mock_tokens
    return service


# ── 1. Unit tests — guard logic ───────────────────────────────────────────────

class TestRefreshTokensValidAfterGuard:

    @pytest.mark.asyncio
    async def test_refresh_accepted_when_no_tva_set(self):
        """tokens_valid_after is None → guard is skipped, refresh proceeds."""
        user = _make_user(tokens_valid_after=None)
        service = _make_auth_service(user)
        token = _encode_refresh_token(user.id)

        result = await service.refresh(token)

        assert result is not None, "Refresh must succeed when tokens_valid_after is not set"

    @pytest.mark.asyncio
    async def test_refresh_accepted_when_token_issued_after_tva(self):
        """Legacy token without version still uses tokens_valid_after fallback."""
        tva = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=60)
        user = _make_user(tokens_valid_after=tva)
        service = _make_auth_service(user)
        token = _encode_refresh_token(user.id, issued_offset_seconds=0, version=None)

        result = await service.refresh(token)

        assert result is not None, "Refresh must succeed when token was issued after tva"

    @pytest.mark.asyncio
    async def test_refresh_rejected_when_token_issued_before_tva(self):
        """Legacy token without version is still rejected by tva during rollout."""
        tva = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=5)
        user = _make_user(tokens_valid_after=tva)
        service = _make_auth_service(user)
        token = _encode_refresh_token(user.id, version=None)

        result = await service.refresh(token)

        assert result is None, "Refresh must be rejected when token was issued before tva"

    @pytest.mark.asyncio
    async def test_refresh_rejected_with_naive_tva(self):
        """Legacy fallback handles naive tva values returned by SQLite."""
        tva_naive = (datetime.now(UTC) + timedelta(seconds=5)).replace(tzinfo=None, microsecond=0)
        user = _make_user(tokens_valid_after=tva_naive)
        service = _make_auth_service(user)
        token = _encode_refresh_token(user.id, version=None)

        result = await service.refresh(token)

        assert result is None, "Guard must handle naive tva (SQLite) and still reject stale token"

    @pytest.mark.asyncio
    async def test_refresh_rejected_returns_none_not_exception(self):
        """Guard must return None, not raise, so the route issues 401 gracefully."""
        tva = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=5)
        user = _make_user(tokens_valid_after=tva)
        service = _make_auth_service(user)
        token = _encode_refresh_token(user.id, version=None)

        result = await service.refresh(token)

        assert result is None  # caller (route) maps None → HTTP 401

    @pytest.mark.asyncio
    async def test_revoked_token_still_rejected_before_tva_check(self):
        """A revoked token must be rejected by the revocation check, independent of tva."""
        user = _make_user(tokens_valid_after=None)
        service = _make_auth_service(user)
        # Override: token IS revoked
        service._tokens.get_token_state = AsyncMock(return_value=TOKEN_STATE_REVOKED)
        token = _encode_refresh_token(user.id)

        result = await service.refresh(token)

        assert result is None, "Revoked token must be rejected regardless of tva"

    @pytest.mark.asyncio
    async def test_refresh_rejected_when_token_version_mismatch(self):
        """Version mismatch deterministically invalidates tokens without relying on time precision."""
        user = _make_user(tokens_valid_after=datetime.now(UTC).replace(microsecond=0), token_version=1)
        service = _make_auth_service(user)
        token = _encode_refresh_token(user.id, version=0)

        result = await service.refresh(token)

        assert result is None, "Refresh must be rejected when token version lags behind the user version"


# ── 2. E2E integration test ───────────────────────────────────────────────────

_engine_e2e = create_async_engine(os.environ["DATABASE_URL"])
_E2ESession = async_sessionmaker(_engine_e2e, class_=AsyncSession, expire_on_commit=False)

_RT_USER_ID = "usr_rt_revoke_test"
_RT_USER_EMAIL = "rt_revoke@test.local"
_RT_PASSWORD = "RefreshRevoke99!"


@pytest_asyncio.fixture()
async def rt_user(app_client, test_tenants):
    """Function-scoped user for refresh-revocation tests; cleaned up after each test."""
    async with _E2ESession() as session:
        existing = await session.get(User, _RT_USER_ID)
        if existing:
            await session.delete(existing)
            await session.commit()
        session.add(User(
            id=_RT_USER_ID,
            organization_id="org_e2e_a",
            email=_RT_USER_EMAIL,
            password_hash=hash_password(_RT_PASSWORD),
            full_name="RT Revoke Test User",
            role="manager",
            is_active=True,
            is_superadmin=False,
        ))
        await session.commit()

    yield {"email": _RT_USER_EMAIL, "password": _RT_PASSWORD}

    async with _E2ESession() as session:
        user = await session.get(User, _RT_USER_ID)
        if user:
            await session.delete(user)
            await session.commit()


class TestRefreshRevocationE2E:

    async def test_refresh_token_rejected_after_password_change(
        self, app_client, rt_user
    ):
        """Full flow:
        1. Login → get refresh token
        2. Verify refresh works (sanity check)
        3. Change password → bumps global token invalidation state
        4. Attempt refresh with the OLD token → must fail with 401
        """
        # Step 1: Login
        resp = await app_client.post("/api/v1/auth/login", json=rt_user)
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        data = resp.json()
        old_refresh_token = data["refreshToken"]
        old_access_token = data["accessToken"]

        # Step 2: Verify refresh works before password change
        resp = await app_client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": old_refresh_token},
        )
        assert resp.status_code == 200, f"Pre-change refresh must work: {resp.text}"
        # Retrieve fresh refresh token from this call so rotation doesn't consume old_refresh_token
        # (we need to use the original old_refresh_token after password change)

        # Step 3: Login again to get a fresh refresh token (the first was consumed by step 2)
        resp = await app_client.post("/api/v1/auth/login", json=rt_user)
        assert resp.status_code == 200
        data2 = resp.json()
        stale_refresh_token = data2["refreshToken"]
        fresh_access_token = data2["accessToken"]

        # Change password — this bumps tokens_valid_after to NOW
        new_password = "NewRefreshRevoke99!"
        resp = await app_client.post(
            "/api/v1/auth/change-password",
            json={"currentPassword": rt_user["password"], "newPassword": new_password},
            headers={"Authorization": f"Bearer {fresh_access_token}"},
        )
        assert resp.status_code == 200, f"Password change failed: {resp.text}"

        # Step 4: Attempt to use the stale refresh token → must fail
        resp = await app_client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": stale_refresh_token},
        )
        assert resp.status_code == 401, (
            f"Stale refresh token must be rejected after password change, "
            f"got {resp.status_code}: {resp.text}"
        )

    async def test_fresh_refresh_token_works_after_password_change(
        self, app_client, rt_user
    ):
        """After password change, a token obtained with the new password must work."""
        resp = await app_client.post("/api/v1/auth/login", json=rt_user)
        assert resp.status_code == 200
        access_token = resp.json()["accessToken"]

        new_password = "NewRefreshRevoke99!"
        resp = await app_client.post(
            "/api/v1/auth/change-password",
            json={"currentPassword": rt_user["password"], "newPassword": new_password},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp.status_code == 200

        # Login with new password → fresh refresh token
        resp = await app_client.post("/api/v1/auth/login", json={
            "email": rt_user["email"], "password": new_password,
        })
        assert resp.status_code == 200, f"Login with new password failed: {resp.text}"
        fresh_refresh = resp.json()["refreshToken"]

        # Fresh refresh token must work
        resp = await app_client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": fresh_refresh},
        )
        assert resp.status_code == 200, (
            f"Fresh refresh token must be accepted after password change: {resp.text}"
        )
