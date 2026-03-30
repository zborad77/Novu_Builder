from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.token_limits import JTI_MAX_LENGTH
from app.repositories.token_repository import TokenRepository


def test_normalize_jti_accepts_db_boundary_and_uuid_like_values():
    boundary_jti = "a" * JTI_MAX_LENGTH
    uuid_like_jti = uuid4().hex

    assert TokenRepository.normalize_jti(boundary_jti) == boundary_jti
    assert TokenRepository.normalize_jti(uuid_like_jti) == uuid_like_jti


def test_normalize_jti_rejects_value_above_db_boundary():
    assert TokenRepository.normalize_jti("a" * (JTI_MAX_LENGTH + 1)) is None


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
