"""R-08: Per-account brute-force protection for the login endpoint."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import app.core.account_limiter as limiter_mod


# ── Unit tests: account_limiter module ───────────────────────────────────────

class TestAccountLimiterUnit:

    def test_key_normalises_email(self):
        """_key lowercases and strips the email."""
        assert limiter_mod._key("User@EXAMPLE.COM") == limiter_mod._key("user@example.com")
        assert "user@example.com" in limiter_mod._key("  User@EXAMPLE.COM  ")

    def test_different_accounts_have_different_keys(self):
        """Two different emails produce different Redis keys."""
        assert limiter_mod._key("alice@example.com") != limiter_mod._key("bob@example.com")

    @pytest.mark.asyncio
    async def test_throttled_when_count_at_limit(self):
        """is_account_throttled returns True when count equals the threshold."""
        mock_client = AsyncMock()
        mock_client.get.return_value = str(limiter_mod._MAX_FAILED_ATTEMPTS).encode()
        mock_client.aclose = AsyncMock()

        with patch.object(limiter_mod, "_get_client", return_value=mock_client):
            result = await limiter_mod.is_account_throttled("victim@example.com", "redis://localhost")

        assert result is True

    @pytest.mark.asyncio
    async def test_throttled_when_count_above_limit(self):
        """is_account_throttled returns True when count exceeds the threshold."""
        mock_client = AsyncMock()
        mock_client.get.return_value = b"999"
        mock_client.aclose = AsyncMock()

        with patch.object(limiter_mod, "_get_client", return_value=mock_client):
            result = await limiter_mod.is_account_throttled("victim@example.com", "redis://localhost")

        assert result is True

    @pytest.mark.asyncio
    async def test_not_throttled_below_limit(self):
        """is_account_throttled returns False when count is below the threshold."""
        mock_client = AsyncMock()
        mock_client.get.return_value = str(limiter_mod._MAX_FAILED_ATTEMPTS - 1).encode()
        mock_client.aclose = AsyncMock()

        with patch.object(limiter_mod, "_get_client", return_value=mock_client):
            result = await limiter_mod.is_account_throttled("user@example.com", "redis://localhost")

        assert result is False

    @pytest.mark.asyncio
    async def test_not_throttled_when_redis_unavailable(self):
        """Fails open (no throttle) when Redis is not reachable."""
        with patch.object(limiter_mod, "_get_client", return_value=None):
            result = await limiter_mod.is_account_throttled("user@example.com", "redis://localhost")

        assert result is False

    @pytest.mark.asyncio
    async def test_record_failure_uses_pipeline_incr_and_expire(self):
        """record_login_failure increments the counter and resets the TTL."""
        # Redis pipeline methods (incr, expire) are synchronous — use MagicMock.
        # Only execute() is async.
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[1, True])

        mock_client = AsyncMock()
        mock_client.pipeline = MagicMock(return_value=mock_pipe)
        mock_client.aclose = AsyncMock()

        with patch.object(limiter_mod, "_get_client", return_value=mock_client):
            await limiter_mod.record_login_failure("user@example.com", "redis://localhost")

        expected_key = limiter_mod._key("user@example.com")
        mock_pipe.incr.assert_called_once_with(expected_key)
        mock_pipe.expire.assert_called_once_with(expected_key, limiter_mod._WINDOW_SECONDS)

    @pytest.mark.asyncio
    async def test_reset_failures_deletes_key(self):
        """reset_login_failures removes the counter key from Redis."""
        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()

        with patch.object(limiter_mod, "_get_client", return_value=mock_client):
            await limiter_mod.reset_login_failures("user@example.com", "redis://localhost")

        mock_client.delete.assert_called_once_with(limiter_mod._key("user@example.com"))

    @pytest.mark.asyncio
    async def test_record_failure_noop_when_redis_unavailable(self):
        """record_login_failure silently no-ops when Redis is down."""
        with patch.object(limiter_mod, "_get_client", return_value=None):
            # Must not raise
            await limiter_mod.record_login_failure("user@example.com", "redis://localhost")

    @pytest.mark.asyncio
    async def test_reset_failures_noop_when_redis_unavailable(self):
        """reset_login_failures silently no-ops when Redis is down."""
        with patch.object(limiter_mod, "_get_client", return_value=None):
            # Must not raise
            await limiter_mod.reset_login_failures("user@example.com", "redis://localhost")


# ── B6: shared Redis client path ─────────────────────────────────────────────

class TestAccountLimiterSharedClient:
    """B6: When a shared Redis client is passed, _get_client is bypassed and
    the shared client is NOT closed (the caller owns it)."""

    @pytest.mark.asyncio
    async def test_shared_client_bypasses_get_client(self):
        """is_account_throttled uses redis_client directly without calling _get_client."""
        shared = AsyncMock()
        shared.get.return_value = b"3"
        shared.aclose = AsyncMock()

        with patch.object(limiter_mod, "_get_client") as mock_get:
            await limiter_mod.is_account_throttled(
                "user@example.com", "redis://localhost", redis_client=shared
            )
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_shared_client_not_closed(self):
        """aclose() must NOT be called on a shared (externally owned) client."""
        shared = AsyncMock()
        shared.get.return_value = b"0"
        shared.aclose = AsyncMock()

        await limiter_mod.is_account_throttled(
            "user@example.com", "redis://localhost", redis_client=shared
        )
        shared.aclose.assert_not_called()

    @pytest.mark.asyncio
    async def test_record_failure_shared_client_not_closed(self):
        """record_login_failure must not close the shared client."""
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[1, True])

        shared = AsyncMock()
        shared.pipeline = MagicMock(return_value=mock_pipe)
        shared.aclose = AsyncMock()

        await limiter_mod.record_login_failure(
            "user@example.com", "redis://localhost", redis_client=shared
        )
        shared.aclose.assert_not_called()

    @pytest.mark.asyncio
    async def test_reset_shared_client_not_closed(self):
        """reset_login_failures must not close the shared client."""
        shared = AsyncMock()
        shared.aclose = AsyncMock()

        await limiter_mod.reset_login_failures(
            "user@example.com", "redis://localhost", redis_client=shared
        )
        shared.aclose.assert_not_called()


# ── Integration tests: login endpoint + throttle ─────────────────────────────

class TestLoginEndpointThrottling:

    async def test_throttled_account_gets_429(self, app_client, test_tenants):
        """When per-account throttle is active, login returns 429."""
        with patch("app.api.routes.auth.is_account_throttled", return_value=True):
            resp = await app_client.post(
                "/api/v1/auth/login",
                json={"email": "victim@example.com", "password": "anypassword"},
            )

        assert resp.status_code == 429

    async def test_throttle_message_does_not_reveal_account_existence(self, app_client):
        """The 429 message must not reveal whether the account exists."""
        with patch("app.api.routes.auth.is_account_throttled", return_value=True):
            resp = await app_client.post(
                "/api/v1/auth/login",
                json={"email": "no-such-user@example.com", "password": "x"},
            )

        assert resp.status_code == 429
        detail = resp.json()["detail"].lower()
        assert "account" not in detail or "exist" not in detail

    async def test_failed_login_records_failure(self, app_client):
        """Failed login calls record_login_failure for the email."""
        with (
            patch("app.api.routes.auth.is_account_throttled", return_value=False),
            patch("app.api.routes.auth.record_login_failure", new_callable=AsyncMock) as mock_record,
        ):
            resp = await app_client.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": "wrong"},
            )

        assert resp.status_code == 401
        mock_record.assert_awaited_once()

    async def test_successful_login_resets_counter(self, app_client, test_tenants):
        """Successful login calls reset_login_failures and NOT record_login_failure."""
        with (
            patch("app.api.routes.auth.is_account_throttled", return_value=False),
            patch("app.api.routes.auth.record_login_failure", new_callable=AsyncMock) as mock_record,
            patch("app.api.routes.auth.reset_login_failures", new_callable=AsyncMock) as mock_reset,
        ):
            resp = await app_client.post(
                "/api/v1/auth/login",
                json=test_tenants["user_a"],
            )

        assert resp.status_code == 200
        mock_reset.assert_awaited_once()
        mock_record.assert_not_awaited()

    async def test_invalid_credentials_returns_401_same_message_regardless_of_account(
        self, app_client
    ):
        """Invalid credentials return the same message whether the account exists or not."""
        with patch("app.api.routes.auth.is_account_throttled", return_value=False):
            resp_existing = await app_client.post(
                "/api/v1/auth/login",
                json={"email": "manager_a@test.local", "password": "wrong_password!"},
            )
            resp_nonexistent = await app_client.post(
                "/api/v1/auth/login",
                json={"email": "no-such-user@example.com", "password": "wrong_password!"},
            )

        assert resp_existing.status_code == 401
        assert resp_nonexistent.status_code == 401
        assert resp_existing.json()["detail"] == resp_nonexistent.json()["detail"]
