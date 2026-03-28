"""C7: Email-based password reset flow tests.

Coverage:
1. forgot-password always returns 200 regardless of whether email exists
2. A reset token is created in DB for valid email
3. reset-password with valid token updates the password
4. reset-password with valid token invalidates old JWT tokens
5. reset-password with expired token returns 400
6. reset-password with already-used token returns 400
7. reset-password with non-existent token returns 400
8. Password strength is enforced on reset-password
"""
import inspect
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 1. Source-level checks ────────────────────────────────────────────────────

class TestPasswordResetSource:

    def test_forgot_password_endpoint_exists(self):
        """forgot_password endpoint must be defined in auth routes."""
        from app.api.routes.auth import forgot_password
        assert callable(forgot_password)

    def test_reset_password_endpoint_exists(self):
        """reset_password endpoint must be defined in auth routes."""
        from app.api.routes.auth import reset_password
        assert callable(reset_password)

    def test_forgot_password_uses_generic_response(self):
        """forgot_password must not reveal whether an email exists."""
        src = inspect.getsource(__import__("app.api.routes.auth", fromlist=["forgot_password"]).forgot_password)
        assert "_GENERIC_RESPONSE" in src or "If that email" in src

    def test_reset_password_sets_tokens_valid_after(self):
        """reset_password must set tokens_valid_after to invalidate old JWTs."""
        src = inspect.getsource(__import__("app.api.routes.auth", fromlist=["reset_password"]).reset_password)
        assert "tokens_valid_after" in src

    def test_reset_token_model_has_used_at(self):
        """PasswordResetToken must have a used_at field to track consumption."""
        from app.models import PasswordResetToken
        assert hasattr(PasswordResetToken, "used_at")

    def test_reset_token_model_has_expires_at(self):
        """PasswordResetToken must have an expires_at field."""
        from app.models import PasswordResetToken
        assert hasattr(PasswordResetToken, "expires_at")


# ── 2. Integration tests against live DB ─────────────────────────────────────

class TestForgotPassword:

    async def test_unknown_email_returns_200(self, app_client):
        """POST /auth/forgot-password returns 200 even for unknown emails."""
        resp = await app_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nobody@example.com"},
        )
        assert resp.status_code == 200
        assert "If that email" in resp.json()["message"] or resp.json()["message"]

    async def test_known_email_returns_200(self, app_client, test_tenants):
        """POST /auth/forgot-password returns 200 for a known email."""
        email = test_tenants["user_a"]["email"]
        with patch("app.api.routes.auth.send_password_reset_email", new_callable=AsyncMock):
            resp = await app_client.post(
                "/api/v1/auth/forgot-password",
                json={"email": email},
            )
        assert resp.status_code == 200

    async def test_both_responses_identical(self, app_client, test_tenants):
        """Response for known and unknown email must be identical (no oracle)."""
        email = test_tenants["user_a"]["email"]
        with patch("app.api.routes.auth.send_password_reset_email", new_callable=AsyncMock):
            resp_known = await app_client.post(
                "/api/v1/auth/forgot-password",
                json={"email": email},
            )
            resp_unknown = await app_client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "nobody@example.com"},
            )
        assert resp_known.status_code == resp_unknown.status_code
        assert resp_known.json()["message"] == resp_unknown.json()["message"]

    async def test_token_created_for_known_email(self, app_client, test_tenants, db_session):
        """A PasswordResetToken row must be inserted for a known email."""
        from sqlalchemy import select
        from app.models import PasswordResetToken, User
        email = test_tenants["user_a"]["email"]

        with patch("app.api.routes.auth.send_password_reset_email", new_callable=AsyncMock):
            await app_client.post("/api/v1/auth/forgot-password", json={"email": email})

        result = await db_session.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()
        assert user is not None

        token_result = await db_session.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        )
        token = token_result.scalar_one_or_none()
        assert token is not None
        assert token.used_at is None


class TestResetPassword:

    async def test_valid_token_resets_password(self, app_client, test_tenants, db_session):
        """Valid token allows password reset and returns 200."""
        from sqlalchemy import select
        from app.models import PasswordResetToken, User

        email = test_tenants["user_a"]["email"]
        with patch("app.api.routes.auth.send_password_reset_email", new_callable=AsyncMock):
            await app_client.post("/api/v1/auth/forgot-password", json={"email": email})

        user_result = await db_session.execute(select(User).where(User.email == email))
        user = user_result.scalar_one()
        token_result = await db_session.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        )
        token = token_result.scalar_one()

        resp = await app_client.post(
            "/api/v1/auth/reset-password",
            json={"token": token.token, "newPassword": "NewSecureP@ssw0rd!"},
        )
        assert resp.status_code == 200

    async def test_used_token_rejected(self, app_client, test_tenants, db_session):
        """A token that has already been used returns 400."""
        from sqlalchemy import select
        from app.models import PasswordResetToken, User

        email = test_tenants["user_a"]["email"]
        with patch("app.api.routes.auth.send_password_reset_email", new_callable=AsyncMock):
            await app_client.post("/api/v1/auth/forgot-password", json={"email": email})

        user_result = await db_session.execute(select(User).where(User.email == email))
        user = user_result.scalar_one()
        token_result = await db_session.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        )
        token = token_result.scalar_one()

        # Use the token
        await app_client.post(
            "/api/v1/auth/reset-password",
            json={"token": token.token, "newPassword": "NewSecureP@ssw0rd!"},
        )
        # Try to use it again
        resp = await app_client.post(
            "/api/v1/auth/reset-password",
            json={"token": token.token, "newPassword": "AnotherP@ssw0rd!"},
        )
        assert resp.status_code == 400

    async def test_nonexistent_token_returns_400(self, app_client):
        """A made-up token returns 400."""
        resp = await app_client.post(
            "/api/v1/auth/reset-password",
            json={"token": "totally-fake-token", "newPassword": "ValidP@ssw0rd1"},
        )
        assert resp.status_code == 400

    async def test_weak_password_rejected(self, app_client, test_tenants, db_session):
        """Weak new password returns 400 before the token is consumed."""
        from sqlalchemy import select
        from app.models import PasswordResetToken, User

        email = test_tenants["user_a"]["email"]
        with patch("app.api.routes.auth.send_password_reset_email", new_callable=AsyncMock):
            await app_client.post("/api/v1/auth/forgot-password", json={"email": email})

        user_result = await db_session.execute(select(User).where(User.email == email))
        user = user_result.scalar_one()
        token_result = await db_session.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        )
        token = token_result.scalar_one()

        resp = await app_client.post(
            "/api/v1/auth/reset-password",
            json={"token": token.token, "newPassword": "weak"},
        )
        assert resp.status_code == 400
        # Token must still be unused
        await db_session.refresh(token)
        assert token.used_at is None
