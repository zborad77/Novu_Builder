from datetime import UTC, datetime, timedelta
from uuid import uuid4

import bcrypt
import jwt
import structlog
from dataclasses import dataclass
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import enforce_password_strength
from app.models import User
from app.repositories.token_repository import TokenRepository
from app.schemas.auth import AuthUserRead

logger = structlog.get_logger(__name__)
_MAX_ENCODED_TOKEN_LENGTH = 8192
_MAX_TOKEN_SUBJECT_LENGTH = 128


@dataclass(frozen=True)
class RefreshResult:
    tokens: tuple[str, str, AuthUserRead] | None
    failure_reason: str | None = None


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def _user_to_read(user: User) -> AuthUserRead:
    return AuthUserRead(
        id=user.id,
        email=user.email,
        fullName=user.full_name,
        role=user.role,
        isActive=user.is_active,
        organizationId=user.organization_id,
        isSuperAdmin=user.is_superadmin,
    )


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._settings = get_settings()
        self._tokens = TokenRepository(session)

    def _create_access_token(self, user_id: str) -> tuple[str, str, datetime]:
        """Returns (encoded_token, jti, expires_at)."""
        jti = uuid4().hex
        exp = datetime.now(UTC) + timedelta(minutes=self._settings.jwt_access_token_expire_minutes)
        token = jwt.encode(
            {"sub": user_id, "jti": jti, "type": "access", "exp": exp},
            self._settings.jwt_secret,
            algorithm=self._settings.jwt_algorithm,
        )
        return token, jti, exp

    def _create_refresh_token(self, user_id: str) -> tuple[str, str, datetime]:
        """Returns (encoded_token, jti, expires_at)."""
        jti = uuid4().hex
        exp = datetime.now(UTC) + timedelta(days=self._settings.jwt_refresh_token_expire_days)
        token = jwt.encode(
            {"sub": user_id, "jti": jti, "type": "refresh", "exp": exp},
            self._settings.jwt_secret,
            algorithm=self._settings.jwt_algorithm,
        )
        return token, jti, exp

    @staticmethod
    def _normalize_encoded_token(token: str | None) -> str | None:
        if not isinstance(token, str):
            return None
        if not token:
            return None
        if len(token) > _MAX_ENCODED_TOKEN_LENGTH:
            return None
        if token != token.strip():
            return None
        if any(ch.isspace() or ord(ch) < 32 for ch in token):
            return None
        return token

    @staticmethod
    def _normalize_token_subject(subject: str | None) -> str | None:
        if not isinstance(subject, str):
            return None
        if not subject:
            return None
        if len(subject) > _MAX_TOKEN_SUBJECT_LENGTH:
            return None
        if subject != subject.strip():
            return None
        if any(ch.isspace() or ord(ch) < 32 for ch in subject):
            return None
        return subject

    @staticmethod
    def _normalize_exp_timestamp(exp: object) -> int | None:
        if isinstance(exp, bool):
            return None
        if isinstance(exp, (int, float)) and exp > 0:
            return int(exp)
        return None

    def decode_token(self, token: str, *, expected_type: str | None = None) -> dict | None:
        normalized_token = self._normalize_encoded_token(token)
        if normalized_token is None:
            return None
        try:
            payload = jwt.decode(normalized_token, self._settings.jwt_secret, algorithms=[self._settings.jwt_algorithm])
        except jwt.PyJWTError:
            return None
        if not isinstance(payload, dict):
            return None

        token_type = payload.get("type")
        if not isinstance(token_type, str):
            return None
        if expected_type is not None and token_type != expected_type:
            return None

        subject = self._normalize_token_subject(payload.get("sub"))
        exp = self._normalize_exp_timestamp(payload.get("exp"))
        jti = TokenRepository.normalize_jti(payload.get("jti"))
        if subject is None or exp is None or jti is None:
            return None

        sanitized_payload = dict(payload)
        sanitized_payload["sub"] = subject
        sanitized_payload["exp"] = exp
        sanitized_payload["jti"] = jti

        impersonated_by = sanitized_payload.get("impersonated_by")
        if impersonated_by is not None:
            normalized_impersonator = self._normalize_token_subject(impersonated_by)
            if normalized_impersonator is None:
                return None
            sanitized_payload["impersonated_by"] = normalized_impersonator
        return sanitized_payload

    async def login(self, *, email: str, password: str) -> tuple[str, str, AuthUserRead] | None:
        result = await self.session.execute(
            select(User).where(User.email == email.strip().lower(), User.is_active.is_(True))
        )
        user = result.scalar_one_or_none()
        if not user:
            return None
        if not _verify_password(password, user.password_hash):
            return None
        access_token, _, _ = self._create_access_token(user.id)
        refresh_token, _, _ = self._create_refresh_token(user.id)
        return access_token, refresh_token, _user_to_read(user)

    async def get_user_by_token(self, token: str) -> AuthUserRead | None:
        payload = self.decode_token(token, expected_type="access")
        if not payload:
            return None
        jti = payload.get("jti")
        if jti and await self._tokens.is_revoked(jti):
            return None
        user = await self.session.get(User, payload["sub"])
        if not user or not user.is_active:
            return None
        if user.tokens_valid_after:
            ttl = timedelta(minutes=self._settings.jwt_access_token_expire_minutes)
            issued_at = datetime.fromtimestamp(payload["exp"], tz=UTC) - ttl
            tva = user.tokens_valid_after
            if tva.tzinfo is None:
                tva = tva.replace(tzinfo=UTC)
            if issued_at < tva:
                return None
        result = _user_to_read(user)
        impersonated_by = payload.get("impersonated_by")
        if impersonated_by:
            result = result.model_copy(update={"impersonatedBy": impersonated_by})
        return result

    async def refresh_with_status(self, refresh_token: str) -> RefreshResult:
        payload = self.decode_token(refresh_token, expected_type="refresh")
        if not payload:
            return RefreshResult(tokens=None, failure_reason="invalid_or_expired_token")
        jti = payload.get("jti")
        if jti and await self._tokens.is_revoked(jti):
            return RefreshResult(tokens=None, failure_reason="revoked_or_reused_token")
        user = await self.session.get(User, payload["sub"])
        if not user or not user.is_active:
            return RefreshResult(tokens=None, failure_reason="invalid_or_expired_token")
        # tokens_valid_after guard: reject refresh tokens issued before the last
        # password change / admin reset (mirrors the same check in get_user_by_token)
        if user.tokens_valid_after:
            ttl = timedelta(days=self._settings.jwt_refresh_token_expire_days)
            issued_at = datetime.fromtimestamp(payload["exp"], tz=UTC) - ttl
            tva = user.tokens_valid_after
            if tva.tzinfo is None:
                tva = tva.replace(tzinfo=UTC)
            if issued_at < tva:
                return RefreshResult(tokens=None, failure_reason="token_invalidated")
        # Rotate: revoke old refresh token, issue new pair
        if jti:
            exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
            await self._tokens.revoke(jti, exp)
        access_token, _, _ = self._create_access_token(user.id)
        new_refresh, _, _ = self._create_refresh_token(user.id)
        return RefreshResult(tokens=(access_token, new_refresh, _user_to_read(user)))

    async def refresh(self, refresh_token: str) -> tuple[str, str, AuthUserRead] | None:
        result = await self.refresh_with_status(refresh_token)
        return result.tokens

    async def revoke_token(self, token: str) -> bool:
        """Revoke any token (access or refresh) by its jti."""
        payload = self.decode_token(token)
        if not payload:
            return False
        jti = payload.get("jti")
        if not jti:
            return False
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        if exp <= datetime.now(UTC):
            return False
        if await self._tokens.is_revoked(jti):
            return False
        return await self._tokens.revoke(jti, exp)

    async def issue_password_reset_token(self, *, user_id: str) -> tuple[str, datetime]:
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self._settings.password_reset_expire_minutes)

        for _ in range(2):
            try:
                raw_token = await self._tokens.create_password_reset_token(
                    user_id=user_id,
                    expires_at=expires_at,
                    now=now,
                )
                return raw_token, expires_at
            except IntegrityError:
                await self.session.rollback()

        raise RuntimeError("Unable to issue a unique password reset token after retry.")

    async def validate_password_reset_token(self, raw_token: str) -> User | None:
        token_record = await self._tokens.get_valid_password_reset_token(raw_token)
        if token_record is None:
            return None

        user = await self.session.get(User, token_record.user_id)
        if not user or not user.is_active:
            return None
        return user

    async def reset_password_with_token(self, *, raw_token: str, new_password: str) -> bool:
        enforce_password_strength(new_password)
        reset_timestamp = datetime.now(UTC).replace(microsecond=0)

        async with self.session.begin():
            claimed = await self._tokens.claim_password_reset_token(
                raw_token,
                now=reset_timestamp,
                commit=False,
            )
            if claimed is None:
                return False

            user = await self.session.get(User, claimed.user_id)
            if not user or not user.is_active:
                logger.warning(
                    "auth.password_reset_invalid_user",
                    user_id=claimed.user_id,
                    user_active=bool(user and user.is_active),
                )
                return False

            user.password_hash = hash_password(new_password)
            user.tokens_valid_after = reset_timestamp
            await self._tokens.invalidate_active_password_reset_tokens(
                user.id,
                now=reset_timestamp,
                commit=False,
            )

        return True
