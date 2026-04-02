from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.token_limits import JTI_MAX_LENGTH
from app.models import RevokedToken
from app.repositories.token_repository import TokenRepository


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
    repo = TokenRepository(session)
    boundary_jti = "a" * JTI_MAX_LENGTH

    result = await repo.revoke(boundary_jti, datetime.now(UTC) + timedelta(minutes=5))

    assert result is True
    session.get.assert_awaited_once()
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_is_revoked_uses_cache_hit_without_db_query(monkeypatch):
    session = AsyncMock()
    repo = TokenRepository(session, redis=object())

    monkeypatch.setattr(
        "app.repositories.token_repository.get_cached",
        AsyncMock(return_value={"revoked": True}),
    )

    result = await repo.is_revoked(uuid4().hex)

    assert result is True
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_is_revoked_populates_negative_cache_after_db_miss(monkeypatch):
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=execute_result)
    set_cached = AsyncMock()
    repo = TokenRepository(session, redis=object())

    monkeypatch.setattr(
        "app.repositories.token_repository.get_cached",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr("app.repositories.token_repository.set_cached", set_cached)

    jti = uuid4().hex
    result = await repo.is_revoked(jti)

    assert result is False
    session.execute.assert_awaited_once()
    set_cached.assert_awaited_once()
    assert set_cached.await_args.args[1] == f"revoked-token:{jti}"


@pytest.mark.asyncio
async def test_revoke_writes_positive_cache_after_commit(monkeypatch):
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.commit = AsyncMock()
    set_cached = AsyncMock()
    repo = TokenRepository(session, redis=object())

    monkeypatch.setattr("app.repositories.token_repository.set_cached", set_cached)

    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    result = await repo.revoke(uuid4().hex, expires_at)

    assert result is True
    set_cached.assert_awaited_once()
