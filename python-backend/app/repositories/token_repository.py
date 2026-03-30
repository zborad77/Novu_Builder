import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.token_limits import JTI_MAX_LENGTH
from app.models import PasswordResetToken, RevokedToken

_MAX_PASSWORD_RESET_TOKEN_LENGTH = 512


@dataclass(frozen=True)
class ClaimedPasswordResetToken:
    token_hash: str
    user_id: str
    expires_at: datetime
    used_at: datetime


class TokenRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def normalize_jti(jti: str | None) -> str | None:
        if not isinstance(jti, str):
            return None
        if not jti:
            return None
        if len(jti) > JTI_MAX_LENGTH:
            return None
        if jti != jti.strip():
            return None
        if any(ch.isspace() or ord(ch) < 32 for ch in jti):
            return None
        return jti

    @staticmethod
    def normalize_password_reset_token(raw_token: str | None) -> str | None:
        if not isinstance(raw_token, str):
            return None
        if not raw_token:
            return None
        if len(raw_token) > _MAX_PASSWORD_RESET_TOKEN_LENGTH:
            return None
        if raw_token != raw_token.strip():
            return None
        if any(ch.isspace() or ord(ch) < 32 for ch in raw_token):
            return None
        return raw_token

    @staticmethod
    def hash_password_reset_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    async def is_revoked(self, jti: str) -> bool:
        normalized_jti = self.normalize_jti(jti)
        if normalized_jti is None:
            return False
        result = await self.session.execute(
            select(RevokedToken).where(
                RevokedToken.jti == normalized_jti,
                RevokedToken.expires_at > datetime.now(UTC),
            )
        )
        return result.scalar_one_or_none() is not None

    async def revoke(self, jti: str, expires_at: datetime) -> bool:
        normalized_jti = self.normalize_jti(jti)
        if normalized_jti is None:
            return False
        existing = await self.session.get(RevokedToken, normalized_jti)
        if existing:
            return False
        self.session.add(RevokedToken(jti=normalized_jti, expires_at=expires_at))
        await self.session.commit()
        return True

    async def delete_expired(self) -> int:
        result = await self.session.execute(
            delete(RevokedToken).where(RevokedToken.expires_at <= datetime.now(UTC))
        )
        await self.session.commit()
        return result.rowcount or 0

    async def get_valid_password_reset_token(
        self,
        raw_token: str,
        *,
        now: datetime | None = None,
    ) -> PasswordResetToken | None:
        current_time = now or datetime.now(UTC)
        normalized_token = self.normalize_password_reset_token(raw_token)
        if normalized_token is None:
            return None
        token_hash = self.hash_password_reset_token(normalized_token)
        result = await self.session.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token == token_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > current_time,
            )
        )
        return result.scalar_one_or_none()

    async def create_password_reset_token(
        self,
        *,
        user_id: str,
        expires_at: datetime,
        now: datetime | None = None,
        raw_token: str | None = None,
        commit: bool = True,
    ) -> str:
        current_time = now or datetime.now(UTC)
        raw_value = raw_token or secrets.token_urlsafe(32)
        normalized_token = self.normalize_password_reset_token(raw_value)
        if normalized_token is None:
            raise ValueError("Invalid password reset token format.")

        await self.delete_expired_password_reset_tokens(
            now=current_time,
            user_id=user_id,
            commit=False,
        )
        await self.invalidate_active_password_reset_tokens(
            user_id,
            now=current_time,
            commit=False,
        )

        token_hash = self.hash_password_reset_token(normalized_token)
        self.session.add(
            PasswordResetToken(
                token=token_hash,
                user_id=user_id,
                expires_at=expires_at,
            )
        )

        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise

        if commit:
            await self.session.commit()
        return normalized_token

    async def invalidate_active_password_reset_tokens(
        self,
        user_id: str,
        *,
        now: datetime | None = None,
        commit: bool = True,
    ) -> int:
        current_time = now or datetime.now(UTC)
        result = await self.session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=current_time)
        )
        if commit:
            await self.session.commit()
        return result.rowcount or 0

    async def claim_password_reset_token(
        self,
        raw_token: str,
        *,
        now: datetime | None = None,
        commit: bool = True,
    ) -> ClaimedPasswordResetToken | None:
        current_time = now or datetime.now(UTC)
        normalized_token = self.normalize_password_reset_token(raw_token)
        if normalized_token is None:
            return None
        token_hash = self.hash_password_reset_token(normalized_token)
        result = await self.session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.token == token_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > current_time,
            )
            .values(used_at=current_time)
            .returning(
                PasswordResetToken.token,
                PasswordResetToken.user_id,
                PasswordResetToken.expires_at,
                PasswordResetToken.used_at,
            )
        )
        row = result.one_or_none()
        if commit:
            await self.session.commit()
        if row is None:
            return None
        return ClaimedPasswordResetToken(
            token_hash=row.token,
            user_id=row.user_id,
            expires_at=row.expires_at,
            used_at=row.used_at,
        )

    async def delete_expired_password_reset_tokens(
        self,
        *,
        now: datetime | None = None,
        user_id: str | None = None,
        commit: bool = True,
    ) -> int:
        current_time = now or datetime.now(UTC)
        stmt = delete(PasswordResetToken).where(PasswordResetToken.expires_at <= current_time)
        if user_id:
            stmt = stmt.where(PasswordResetToken.user_id == user_id)
        result = await self.session.execute(stmt)
        if commit:
            await self.session.commit()
        return result.rowcount or 0
