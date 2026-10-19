from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import PasswordResetToken, User
from app.repositories.token_repository import TokenRepository
from app.services.auth_service import AuthService


@pytest.mark.asyncio
async def test_issue_password_reset_token_persists_hash_and_supports_lookup(db_session, reset_test_user):
    service = AuthService(db_session)
    raw_token, expires_at = await service.issue_password_reset_token(user_id=reset_test_user["user_id"])

    result = await db_session.execute(
        select(PasswordResetToken).where(PasswordResetToken.user_id == reset_test_user["user_id"])
    )
    token_row = result.scalar_one()

    assert raw_token
    assert token_row.token != raw_token
    assert token_row.token == TokenRepository.hash_password_reset_token(raw_token)
    assert token_row.used_at is None
    stored_expires_at = token_row.expires_at
    if stored_expires_at.tzinfo is None:
        stored_expires_at = stored_expires_at.replace(tzinfo=UTC)
    assert stored_expires_at == expires_at

    lookup = await TokenRepository(db_session).get_valid_password_reset_token(raw_token)
    assert lookup is not None
    assert lookup.user_id == reset_test_user["user_id"]


@pytest.mark.asyncio
async def test_expired_password_reset_token_is_rejected(db_session, reset_test_user):
    repo = TokenRepository(db_session)
    now = datetime.now(UTC)
    raw_token = await repo.create_password_reset_token(
        user_id=reset_test_user["user_id"],
        expires_at=now - timedelta(minutes=1),
        raw_token="expired-reset-token",
    )

    lookup = await repo.get_valid_password_reset_token(raw_token, now=now)
    assert lookup is None


@pytest.mark.asyncio
async def test_claimed_password_reset_token_cannot_be_reused(db_session, reset_test_user):
    repo = TokenRepository(db_session)
    now = datetime.now(UTC)
    raw_token = await repo.create_password_reset_token(
        user_id=reset_test_user["user_id"],
        expires_at=now + timedelta(minutes=30),
        raw_token="single-use-reset-token",
    )

    claimed = await repo.claim_password_reset_token(raw_token, now=now)
    reused = await repo.claim_password_reset_token(raw_token, now=now + timedelta(seconds=1))

    assert claimed is not None
    assert claimed.user_id == reset_test_user["user_id"]
    assert reused is None

    lookup = await repo.get_valid_password_reset_token(raw_token, now=now + timedelta(seconds=2))
    assert lookup is None


@pytest.mark.asyncio
async def test_issuing_second_token_invalidates_previous_unused_token(db_session, reset_test_user):
    service = AuthService(db_session)

    first_raw_token, _ = await service.issue_password_reset_token(user_id=reset_test_user["user_id"])
    second_raw_token, _ = await service.issue_password_reset_token(user_id=reset_test_user["user_id"])

    repo = TokenRepository(db_session)
    assert await repo.get_valid_password_reset_token(first_raw_token) is None

    second_lookup = await repo.get_valid_password_reset_token(second_raw_token)
    assert second_lookup is not None

    count_result = await db_session.execute(
        select(func.count())
        .select_from(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == reset_test_user["user_id"],
            PasswordResetToken.used_at.is_(None),
        )
    )
    assert count_result.scalar_one() == 1


@pytest.mark.asyncio
async def test_reset_password_with_token_updates_password_and_blocks_reuse(db_session, reset_test_user):
    service = AuthService(db_session)
    raw_token, _ = await service.issue_password_reset_token(user_id=reset_test_user["user_id"])

    assert await service.reset_password_with_token(raw_token=raw_token, new_password="NewResetP@ss1!") is True
    assert await service.reset_password_with_token(raw_token=raw_token, new_password="AnotherResetP@ss2!") is False

    user = await db_session.get(User, reset_test_user["user_id"])
    assert user is not None
    assert user.tokens_valid_after is not None

    old_login = await service.login(email=reset_test_user["email"], password="OldResetP@ss1!")
    new_login = await service.login(email=reset_test_user["email"], password="NewResetP@ss1!")
    assert old_login is None
    assert new_login is not None


@pytest.mark.asyncio
async def test_invalid_password_reset_token_returns_none_and_false(db_session, reset_test_user):
    service = AuthService(db_session)
    repo = TokenRepository(db_session)
    raw_token, _ = await service.issue_password_reset_token(user_id=reset_test_user["user_id"])

    assert await repo.get_valid_password_reset_token(" invalid-reset-token ") is None
    assert await repo.claim_password_reset_token("\ninvalid-reset-token") is None
    assert await service.reset_password_with_token(raw_token=" invalid-reset-token ", new_password="ValidResetP@ss1!") is False

    # The real token must remain usable after invalid-token attempts.
    assert await service.reset_password_with_token(raw_token=raw_token, new_password="ValidResetP@ss2!") is True


@pytest.mark.asyncio
async def test_create_password_reset_token_rejects_invalid_raw_token_format(db_session, reset_test_user):
    repo = TokenRepository(db_session)

    with pytest.raises(ValueError, match="Invalid password reset token format"):
        await repo.create_password_reset_token(
            user_id=reset_test_user["user_id"],
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
            raw_token=" invalid-reset-token ",
        )


@pytest.mark.asyncio
async def test_weak_password_is_rejected_before_token_is_consumed(db_session, reset_test_user):
    service = AuthService(db_session)
    repo = TokenRepository(db_session)
    raw_token, _ = await service.issue_password_reset_token(user_id=reset_test_user["user_id"])

    with pytest.raises(ValueError, match="Heslo"):
        await service.reset_password_with_token(raw_token=raw_token, new_password="weak")

    assert await repo.get_valid_password_reset_token(raw_token) is not None


@pytest.mark.asyncio
async def test_reset_password_token_for_inactive_user_is_consumed_and_logged_safely(db_session, reset_test_user):
    service = AuthService(db_session)
    repo = TokenRepository(db_session)
    raw_token, _ = await service.issue_password_reset_token(user_id=reset_test_user["user_id"])

    user = await db_session.get(User, reset_test_user["user_id"])
    assert user is not None
    user.is_active = False
    await db_session.commit()

    from unittest.mock import patch

    with patch("app.services.auth_service.logger.warning") as mock_warning:
        assert await service.reset_password_with_token(raw_token=raw_token, new_password="ValidResetP@ss3!") is False

    assert await repo.get_valid_password_reset_token(raw_token) is None
    mock_warning.assert_called_once()
    rendered = repr(mock_warning.call_args)
    assert raw_token not in rendered


@pytest.mark.asyncio
async def test_delete_expired_password_reset_tokens_keeps_non_expired_rows(db_session, reset_test_user):
    repo = TokenRepository(db_session)
    now = datetime.now(UTC)
    fresh_raw_token = await repo.create_password_reset_token(
        user_id=reset_test_user["user_id"],
        expires_at=now + timedelta(minutes=30),
        raw_token="cleanup-fresh-token",
    )
    expired_raw_token = "cleanup-expired-token"
    db_session.add(
        PasswordResetToken(
            token=TokenRepository.hash_password_reset_token(expired_raw_token),
            user_id=reset_test_user["user_id"],
            expires_at=now - timedelta(minutes=1),
            used_at=now - timedelta(minutes=2),
        )
    )
    await db_session.commit()

    deleted = await repo.delete_expired_password_reset_tokens(now=now)

    assert deleted >= 1
    assert await repo.get_valid_password_reset_token(expired_raw_token, now=now) is None
    assert await repo.get_valid_password_reset_token(fresh_raw_token, now=now) is not None


def test_password_reset_model_metadata_declares_hardening_indexes():
    index_names = {index.name for index in PasswordResetToken.__table__.indexes}
    assert "ix_password_reset_tokens_expires_at" in index_names
    assert "uq_password_reset_tokens_user_id_unused" in index_names


def test_password_reset_hardening_migration_contains_expected_indexes():
    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20260329_0022_harden_password_reset_tokens.py"
    content = migration_path.read_text(encoding="utf-8")

    assert "ix_password_reset_tokens_expires_at" in content
    assert "uq_password_reset_tokens_user_id_unused" in content
    assert "hashlib.sha256" in content
