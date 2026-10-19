"""C7: Self-service password reset — retired flow tests.

Self-service reset (forgot/reset via email) is not supported in the current architecture
(no web client). Both endpoints return 410 Gone. Admin reset remains unaffected.
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

    def test_forgot_password_retired(self):
        """forgot_password must be marked as retired."""
        src = inspect.getsource(__import__("app.api.routes.auth", fromlist=["forgot_password"]).forgot_password)
        assert "retired" in src.lower()

    def test_reset_password_retired(self):
        """reset_password must be marked as retired."""
        src = inspect.getsource(__import__("app.api.routes.auth", fromlist=["reset_password"]).reset_password)
        assert "retired" in src.lower()

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

    async def test_forgot_password_returns_410(self, app_client):
        """POST /auth/forgot-password returns 410 — feature is disabled."""
        resp = await app_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nobody@example.com"},
        )
        assert resp.status_code == 410
        assert "not supported" in resp.json()["detail"].lower()

    async def test_forgot_password_returns_410_for_known_email(self, app_client, test_tenants):
        """POST /auth/forgot-password returns 410 even for a known email."""
        email = test_tenants["user_a"]["email"]
        resp = await app_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": email},
        )
        assert resp.status_code == 410

    async def test_both_responses_identical(self, app_client, test_tenants):
        """Both known and unknown email get the same 410 response."""
        email = test_tenants["user_a"]["email"]
        resp_known = await app_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": email},
        )
        resp_unknown = await app_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nobody@example.com"},
        )
        assert resp_known.status_code == resp_unknown.status_code
        assert resp_known.json()["detail"] == resp_unknown.json()["detail"]

    async def test_no_token_created_when_disabled(self, app_client, test_tenants, db_session):
        """No PasswordResetToken row must be created when the endpoint is disabled."""
        from sqlalchemy import select
        from app.models import PasswordResetToken, User
        email = test_tenants["user_a"]["email"]

        await app_client.post("/api/v1/auth/forgot-password", json={"email": email})

        result = await db_session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        assert user is not None

        token_result = await db_session.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        )
        assert token_result.scalar_one_or_none() is None


class TestResetPassword:
    """reset-password endpoint is disabled — all requests return 410."""

    async def test_reset_password_returns_410(self, app_client):
        """Any reset-password request returns 410 — feature is disabled."""
        resp = await app_client.post(
            "/api/v1/auth/reset-password",
            json={"token": "any-token", "newPassword": "ValidP@ssw0rd1"},
        )
        assert resp.status_code == 410
        assert "not supported" in resp.json()["detail"].lower()
