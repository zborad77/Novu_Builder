"""R-32: Redis cache helpers and pricebook/supplier caching — unit tests.

Tests cover:
  - cache miss: get_cached returns None when key absent
  - cache hit: get_cached returns stored value without Redis being called twice
  - set_cached stores JSON-serialisable value with correct TTL
  - delete_cached removes one or more keys
  - fail-open: all helpers are no-ops when redis=None
  - tenant isolation: keys for org_a and org_b are distinct
  - pricebook list route uses cache key scoped to org_id
  - supplier list route uses cache key scoped to org_id + includeInactive flag
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.cache import _k, delete_cached, get_cached, set_cached


# ── cache.py unit tests ───────────────────────────────────────────────────────

class TestGetCached:
    @pytest.mark.asyncio
    async def test_returns_none_on_cache_miss(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        result = await get_cached(redis, "some:key")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_parsed_json_on_hit(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps({"x": 1}).encode())
        result = await get_cached(redis, "some:key")
        assert result == {"x": 1}

    @pytest.mark.asyncio
    async def test_returns_none_when_redis_is_none(self):
        result = await get_cached(None, "some:key")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_redis_error(self):
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=Exception("connection refused"))
        result = await get_cached(redis, "some:key")
        assert result is None  # fail open


class TestSetCached:
    @pytest.mark.asyncio
    async def test_calls_setex_with_prefixed_key(self):
        redis = AsyncMock()
        await set_cached(redis, "pricebooks:list:org-1", [{"id": "pb1"}], ttl=300)
        redis.setex.assert_awaited_once()
        key_arg, ttl_arg, val_arg = redis.setex.call_args[0]
        assert key_arg == _k("pricebooks:list:org-1")
        assert ttl_arg == 300
        assert json.loads(val_arg) == [{"id": "pb1"}]

    @pytest.mark.asyncio
    async def test_no_op_when_redis_is_none(self):
        # Should not raise
        await set_cached(None, "key", {"data": 1}, ttl=60)

    @pytest.mark.asyncio
    async def test_no_op_on_redis_error(self):
        redis = AsyncMock()
        redis.setex = AsyncMock(side_effect=Exception("timeout"))
        # Should not raise — fails silently
        await set_cached(redis, "key", {}, ttl=60)


class TestDeleteCached:
    @pytest.mark.asyncio
    async def test_deletes_prefixed_keys(self):
        redis = AsyncMock()
        await delete_cached(redis, "a:key", "b:key")
        redis.delete.assert_awaited_once_with(_k("a:key"), _k("b:key"))

    @pytest.mark.asyncio
    async def test_no_op_when_redis_is_none(self):
        await delete_cached(None, "a:key")  # must not raise

    @pytest.mark.asyncio
    async def test_no_op_when_no_keys_given(self):
        redis = AsyncMock()
        await delete_cached(redis)
        redis.delete.assert_not_called()


# ── tenant isolation ──────────────────────────────────────────────────────────

class TestTenantIsolation:
    def test_pricebook_list_keys_differ_by_org(self):
        from app.api.routes.pricebooks import _list_key
        key_a = _list_key("org-a")
        key_b = _list_key("org-b")
        assert key_a != key_b
        assert "org-a" in key_a
        assert "org-b" in key_b

    def test_supplier_list_keys_differ_by_org(self):
        from app.api.routes.suppliers import _list_key
        key_a = _list_key("org-a", False)
        key_b = _list_key("org-b", False)
        assert key_a != key_b

    def test_supplier_list_keys_differ_by_include_inactive_flag(self):
        from app.api.routes.suppliers import _list_key
        key_active = _list_key("org-1", False)
        key_all = _list_key("org-1", True)
        assert key_active != key_all

    @pytest.mark.asyncio
    async def test_pricebook_cache_miss_falls_through_to_db(self):
        """When Redis has no entry, the route must call the service (DB path)."""
        from app.api.routes.pricebooks import list_pricebooks
        from app.schemas.pricebook import PricebookListResponse

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # cache miss

        mock_service = AsyncMock()
        mock_service.list_pricebooks = AsyncMock(return_value=[])

        mock_user = MagicMock()
        mock_user.organizationId = "org-test"
        mock_user.isSuperAdmin = False

        with patch("app.api.routes.pricebooks.get_cached", return_value=None):
            with patch("app.api.routes.pricebooks.set_cached", new_callable=AsyncMock) as mock_set:
                result = await list_pricebooks(
                    current_user=mock_user,
                    service=mock_service,
                    redis=mock_redis,
                )
        mock_service.list_pricebooks.assert_awaited_once_with("org-test")
        # set_cached should be called to populate the cache
        mock_set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pricebook_cache_hit_skips_db(self):
        """When Redis returns data, the service (DB) must NOT be called."""
        from app.api.routes.pricebooks import list_pricebooks

        mock_service = AsyncMock()
        mock_service.list_pricebooks = AsyncMock()

        mock_user = MagicMock()
        mock_user.organizationId = "org-test"

        cached_data = [{"id": "pb1", "name": "Test", "organizationId": "org-test",
                        "hourlyRate": 350.0, "dailyRate": 2800.0, "laborHoursPerSqm": 0.3,
                        "vatPct": 21.0, "currency": "CZK", "isDefault": True,
                        "createdAt": "2025-01-01T00:00:00", "updatedAt": "2025-01-01T00:00:00"}]

        with patch("app.api.routes.pricebooks.get_cached", return_value=cached_data):
            result = await list_pricebooks(
                current_user=mock_user,
                service=mock_service,
                redis=AsyncMock(),
            )
        # DB must NOT have been called
        mock_service.list_pricebooks.assert_not_called()

    @pytest.mark.asyncio
    async def test_superadmin_bypasses_cache(self):
        """Superadmin (org_id=None) must never read or write the cache."""
        from app.api.routes.pricebooks import list_pricebooks

        mock_service = AsyncMock()
        mock_service.list_pricebooks = AsyncMock(return_value=[])

        mock_user = MagicMock()
        mock_user.organizationId = None  # superadmin has no org
        mock_user.isSuperAdmin = True

        with patch("app.api.routes.pricebooks.get_cached", new_callable=AsyncMock) as mock_get:
            with patch("app.api.routes.pricebooks.set_cached", new_callable=AsyncMock) as mock_set:
                await list_pricebooks(
                    current_user=mock_user,
                    service=mock_service,
                    redis=AsyncMock(),
                )
        mock_get.assert_not_called()
        mock_set.assert_not_called()

    @pytest.mark.asyncio
    async def test_supplier_create_invalidates_both_variants(self):
        """PATCH supplier must invalidate both active-only and all-suppliers keys."""
        from app.api.routes.suppliers import _list_key, patch_supplier
        from app.schemas.supplier import SupplierPatch

        mock_service = AsyncMock()
        mock_service.update_supplier = AsyncMock(return_value=MagicMock(model_dump=lambda: {}))

        mock_user = MagicMock()
        mock_user.organizationId = "org-x"

        payload = SupplierPatch(
            name="Supplier X",
            websiteUrl=None,
            integrationType="manual",
            contactName=None,
            contactEmail=None,
        )

        deleted_keys = []

        async def capture_delete(redis, *keys):
            deleted_keys.extend(keys)

        with patch("app.api.routes.suppliers.delete_cached", side_effect=capture_delete):
            await patch_supplier(
                supplier_id="sup-1",
                payload=payload,
                current_user=mock_user,
                service=mock_service,
                redis=AsyncMock(),
            )

        assert _list_key("org-x", False) in deleted_keys
        assert _list_key("org-x", True) in deleted_keys
