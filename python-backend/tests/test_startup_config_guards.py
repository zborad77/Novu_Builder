from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.main import initialize_job_queue, verify_storage_backend


def _settings(**overrides):
    base = {
        "app_env": "production",
        "redis_url": "redis://:strong-password@localhost:6379/0",
        "storage_backend": "s3",
        "s3_bucket": "novu-prod-bucket",
        "s3_endpoint_url": "",
        "s3_cdn_base_url": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_verify_storage_backend_delegates_to_storage_health_probe_for_local_backend():
    settings = _settings(storage_backend="local")
    verify_storage_health = AsyncMock()
    with patch("app.main.verify_storage_health", verify_storage_health):
        await verify_storage_backend(settings)
    verify_storage_health.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_verify_storage_backend_delegates_to_storage_health_probe_for_s3_backend():
    settings = _settings(storage_backend="s3")
    verify_storage_health = AsyncMock()
    with patch("app.main.verify_storage_health", verify_storage_health):
        await verify_storage_backend(settings)
    verify_storage_health.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_initialize_job_queue_fails_fast_outside_development():
    client = AsyncMock()
    client.ping.side_effect = OSError("redis down")
    settings = _settings(app_env="production")

    with patch("app.main._build_redis_client", return_value=client):
        with pytest.raises(RuntimeError, match="Redis job queue is unavailable"):
            await initialize_job_queue(settings)

    client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_initialize_job_queue_is_tolerated_in_development():
    client = AsyncMock()
    client.ping.side_effect = OSError("redis down")
    settings = _settings(app_env="development")

    with patch("app.main._build_redis_client", return_value=client):
        result = await initialize_job_queue(settings)

    assert result is None
    client.aclose.assert_awaited_once()
