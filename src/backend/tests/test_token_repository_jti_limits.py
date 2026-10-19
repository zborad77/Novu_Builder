from datetime import UTC, datetime, timedelta
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.token_limits import JTI_MAX_LENGTH
from app.models import RevokedToken
from app.repositories.token_repository import (
    TOKEN_STATE_ACTIVE,
    TOKEN_STATE_REVOKED,
    TokenRepository,
)


class FakeAuthRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def setex(self, key: str, ttl_seconds: int, value) -> bool:
        self.values[key] = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        return True


def test_normalize_jti_accepts_db_boundary_and_uuid_like_values():
    boundary_jti = "a" * JTI_MAX_LENGTH
    uuid_like_jti = uuid4().hex

    assert TokenRepository.normalize_jti(boundary_jti) == boundary_jti
    assert TokenRepository.normalize_jti(uuid_like_jti) == uuid_like_jti


def test_normalize_jti_rejects_value_above_db_boundary():
    assert TokenRepository.normalize_jti("a" * (JTI_MAX_LENGTH + 1)) is None


def test_revoked_token_model_keeps_expires_at_index_in_metadata():
    index_names = {index.name for index in RevokedToken.__table__.indexes}
    assert "ix_revoked_tokens_expires_at" in index_names


@pytest.mark.asyncio
async def test_revoke_rejects_overlong_jti_before_db_write():
    session = AsyncMock()
    repo = TokenRepository(session)

    result = await repo.revoke("a" * (JTI_MAX_LENGTH + 1), datetime.now(UTC) + timedelta(minutes=5))

    assert result is False
    session.get.assert_not_awaited()
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoke_accepts_jti_at_db_boundary():
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.commit = AsyncMock()
    repo = TokenRepository(session, redis=FakeAuthRedis())
    boundary_jti = "a" * JTI_MAX_LENGTH

    result = await repo.revoke(boundary_jti, datetime.now(UTC) + timedelta(minutes=5))

    assert result is True
    session.get.assert_awaited_once()
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_is_revoked_uses_positive_cache_hit_without_db_query():
    session = AsyncMock()
    redis = FakeAuthRedis()
    jti = uuid4().hex
    redis.values[f"cache:revoked-token:{jti}"] = TOKEN_STATE_REVOKED
    repo = TokenRepository(session, redis=redis)

    result = await repo.is_revoked(jti)

    assert result is True
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_lookup_does_not_cache_negative_state_and_revoke_is_immediately_visible():
    session_reader = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session_reader.execute = AsyncMock(return_value=execute_result)

    session_writer = AsyncMock()
    session_writer.get = AsyncMock(return_value=None)
    session_writer.add = MagicMock()
    session_writer.commit = AsyncMock()

    shared_redis = FakeAuthRedis()
    jti = uuid4().hex
    expires_at = datetime.now(UTC) + timedelta(minutes=5)

    reader_repo = TokenRepository(session_reader, redis=shared_redis)
    writer_repo = TokenRepository(session_writer, redis=shared_redis)

    active_state = await reader_repo.get_token_state(jti, expires_at=expires_at)
    assert f"cache:revoked-token:{jti}" not in shared_redis.values
    revoked = await writer_repo.revoke(jti, expires_at)
    revoked_state = await reader_repo.get_token_state(jti, expires_at=expires_at)

    assert active_state == TOKEN_STATE_ACTIVE
    assert revoked is True
    assert revoked_state == TOKEN_STATE_REVOKED
    assert session_reader.execute.await_count == 1


@pytest.mark.asyncio
async def test_revoke_writes_positive_cache_after_commit():
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.commit = AsyncMock()
    redis = FakeAuthRedis()
    repo = TokenRepository(session, redis=redis)

    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    jti = uuid4().hex
    result = await repo.revoke(jti, expires_at)

    assert result is True
    payload = json.loads(redis.values[f"cache:revoked-token:{jti}"])
    assert payload["meta"]["version"] == 1
    assert payload["meta"]["tag"] == "revoked-token-v1"
    assert payload["meta"]["ttlSeconds"] > 0
    assert payload["state"] == TOKEN_STATE_REVOKED
    assert payload["revoked"] is True


@pytest.mark.asyncio
async def test_legacy_negative_cache_entry_is_not_treated_as_active():
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=execute_result)
    redis = FakeAuthRedis()
    jti = uuid4().hex
    redis.values[f"cache:revoked-token:{jti}"] = '{"revoked": false}'
    repo = TokenRepository(session, redis=redis)

    result = await repo.get_token_state(
        jti,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    assert result == TOKEN_STATE_ACTIVE
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_token_state_falls_back_to_db_when_redis_is_unavailable():
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=execute_result)
    repo = TokenRepository(session, redis=None)

    result = await repo.get_token_state(
        uuid4().hex,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    assert result == TOKEN_STATE_ACTIVE
    session.execute.assert_awaited_once()
