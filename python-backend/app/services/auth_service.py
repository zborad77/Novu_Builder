from datetime import UTC, datetime, timedelta
from uuid import uuid4

import bcrypt
import jwt
import structlog
from dataclasses import dataclass
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import commit_security_critical_audit
from app.core.config import get_settings
from app.core.security import enforce_password_strength
from app.models import User, UserSession
from app.repositories.token_repository import (
    SessionTokenRevocation,
    TOKEN_STATE_ACTIVE,
    TOKEN_STATE_EXPIRED,
    TOKEN_STATE_REVOKED,
    TokenRepository,
)
from app.schemas.auth import AuthSessionRead, AuthUserRead

logger = structlog.get_logger(__name__)
_MAX_ENCODED_TOKEN_LENGTH = 8192
_MAX_TOKEN_SUBJECT_LENGTH = 128


@dataclass(frozen=True)
class RefreshResult:
    tokens: tuple[str, str, AuthUserRead] | None
    failure_reason: str | None = None


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


_DUMMY_PASSWORD_HASH = hash_password("NOVU_BUILDER_AUTH_DUMMY_PASSWORD")


def verify_password(plain: str, hashed: str) -> bool:
    return _verify_password(plain, hashed)


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
    def __init__(self, session: AsyncSession, *, redis=None):
        self.session = session
        self._settings = get_settings()
        self._tokens = TokenRepository(session, redis=redis)

    def _create_access_token(
        self,
        user_id: str,
        *,
        session_id: str | None = None,
        token_version: int = 0,
    ) -> tuple[str, str, datetime]:
        """Returns (encoded_token, jti, expires_at)."""
        jti = uuid4().hex
        exp = datetime.now(UTC) + timedelta(minutes=self._settings.jwt_access_token_expire_minutes)
        payload = {"sub": user_id, "jti": jti, "type": "access", "exp": exp, "ver": token_version}
        if session_id is not None:
            payload["sid"] = session_id
        token = jwt.encode(
            payload,
            self._settings.jwt_secret,
            algorithm=self._settings.jwt_algorithm,
        )
        return token, jti, exp

    def _create_refresh_token(
        self,
        user_id: str,
        *,
        session_id: str | None = None,
        token_version: int = 0,
    ) -> tuple[str, str, datetime]:
        """Returns (encoded_token, jti, expires_at)."""
        jti = uuid4().hex
        exp = datetime.now(UTC) + timedelta(days=self._settings.jwt_refresh_token_expire_days)
        payload = {"sub": user_id, "jti": jti, "type": "refresh", "exp": exp, "ver": token_version}
        if session_id is not None:
            payload["sid"] = session_id
        token = jwt.encode(
            payload,
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

    @classmethod
    def _normalize_session_id(cls, session_id: str | None) -> str | None:
        return cls._normalize_token_subject(session_id)

    @staticmethod
    def _normalize_exp_timestamp(exp: object) -> int | None:
        if isinstance(exp, bool):
            return None
        if isinstance(exp, (int, float)) and exp > 0:
            return int(exp)
        return None

    @staticmethod
    def _normalize_token_version(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int) and value >= 0:
            return value
        return None

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @classmethod
    def _user_token_version(cls, user: User | object) -> int:
        normalized = cls._normalize_token_version(getattr(user, "token_version", 0))
        return normalized if normalized is not None else 0

    @classmethod
    def invalidate_user_token_state(cls, user: User | object, *, now: datetime | None = None) -> int:
        invalidated_at = cls._normalize_datetime(now or datetime.now(UTC)).replace(microsecond=0)
        user.tokens_valid_after = invalidated_at
        next_version = cls._user_token_version(user) + 1
        user.token_version = next_version
        return next_version

    @classmethod
    def _current_tokens_valid_after(cls, user: User | object) -> datetime | None:
        value = getattr(user, "tokens_valid_after", None)
        if not isinstance(value, datetime):
            return None
        return cls._normalize_datetime(value)

    @classmethod
    def _token_version_matches_user(cls, payload: dict, user: User | object) -> bool:
        current_version = cls._user_token_version(user)
        token_version = payload.get("ver")
        if token_version is None:
            return current_version == 0
        return token_version == current_version

    @classmethod
    def _legacy_token_is_invalidated(
        cls,
        payload: dict,
        *,
        user: User | object,
        ttl: timedelta,
    ) -> bool:
        tokens_valid_after = cls._current_tokens_valid_after(user)
        if tokens_valid_after is None:
            return False
        issued_at = datetime.fromtimestamp(payload["exp"], tz=UTC) - ttl
        return issued_at < tokens_valid_after

    async def _cache_session_revocations(self, revocations: list[SessionTokenRevocation]) -> None:
        for record in revocations:
            await self._tokens.cache_revoked_token(record.jti, record.expires_at)

    @staticmethod
    def _payload_expiry(payload: dict) -> datetime:
        return datetime.fromtimestamp(payload["exp"], tz=UTC)

    async def _get_token_state(self, payload: dict) -> str:
        jti = payload.get("jti")
        if not isinstance(jti, str):
            return TOKEN_STATE_EXPIRED
        return await self._tokens.get_token_state(
            jti,
            expires_at=self._payload_expiry(payload),
        )

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
        token_version = self._normalize_token_version(payload.get("ver"))
        if payload.get("ver") is not None and token_version is None:
            return None
        if token_version is not None:
            sanitized_payload["ver"] = token_version
        session_id = self._normalize_session_id(payload.get("sid"))
        if payload.get("sid") is not None and session_id is None:
            return None
        if session_id is not None:
            sanitized_payload["sid"] = session_id

        impersonated_by = sanitized_payload.get("impersonated_by")
        if impersonated_by is not None:
            normalized_impersonator = self._normalize_token_subject(impersonated_by)
            if normalized_impersonator is None:
                return None
            sanitized_payload["impersonated_by"] = normalized_impersonator
        return sanitized_payload

    def get_token_session_id(self, token: str) -> str | None:
        payload = self.decode_token(token)
        if not payload:
            return None
        return payload.get("sid")

    @staticmethod
    def _session_to_read(session: UserSession, *, current_session_id: str | None) -> AuthSessionRead:
        return AuthSessionRead(
            id=session.id,
            createdAt=AuthService._normalize_datetime(session.created_at),
            accessExpiresAt=AuthService._normalize_datetime(session.access_expires_at),
            refreshExpiresAt=AuthService._normalize_datetime(session.refresh_expires_at),
            revokedAt=(
                AuthService._normalize_datetime(session.revoked_at)
                if session.revoked_at is not None
                else None
            ),
            isCurrent=session.id == current_session_id,
        )

    async def login(self, *, email: str, password: str) -> tuple[str, str, AuthUserRead] | None:
        normalized_email = email.strip().lower()
        result = await self.session.execute(
            select(User).where(User.email == normalized_email)
        )
        user = result.scalar_one_or_none()
        password_hash = user.password_hash if user and user.password_hash else _DUMMY_PASSWORD_HASH
        password_matches = _verify_password(password, password_hash)
        if not user or not user.is_active or not password_matches:
            return None
        token_version = self._user_token_version(user)
        for _ in range(2):
            session_id = f"sess_{uuid4().hex}"
            access_token, access_jti, access_exp = self._create_access_token(
                user.id,
                session_id=session_id,
                token_version=token_version,
            )
            refresh_token, refresh_jti, refresh_exp = self._create_refresh_token(
                user.id,
                session_id=session_id,
                token_version=token_version,
            )
            try:
                await self._tokens.create_user_session(
                    session_id=session_id,
                    user_id=user.id,
                    access_jti=access_jti,
                    refresh_jti=refresh_jti,
                    access_expires_at=access_exp,
                    refresh_expires_at=refresh_exp,
                )
                return access_token, refresh_token, _user_to_read(user)
            except IntegrityError:
                await self.session.rollback()
                logger.warning(
                    "auth.session_persist_collision",
                    user_id=user.id,
                    email=user.email,
                )
                continue

        raise RuntimeError("Unable to persist login session after retry.")

    async def get_user_by_token(self, token: str) -> AuthUserRead | None:
        payload = self.decode_token(token, expected_type="access")
        if not payload:
            return None
        if await self._get_token_state(payload) != TOKEN_STATE_ACTIVE:
            return None
        session_id = payload.get("sid")
        if session_id:
            session = await self._tokens.get_user_session(session_id)
            if session is None or session.user_id != payload["sub"] or session.revoked_at is not None:
                return None
        user = await self.session.get(User, payload["sub"])
        if not user or not user.is_active:
            return None
        if not self._token_version_matches_user(payload, user):
            return None
        if payload.get("ver") is None and self._legacy_token_is_invalidated(
            payload,
            user=user,
            ttl=timedelta(minutes=self._settings.jwt_access_token_expire_minutes),
        ):
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
        token_state = await self._get_token_state(payload)
        if token_state == TOKEN_STATE_REVOKED:
            return RefreshResult(tokens=None, failure_reason="revoked_or_reused_token")
        if token_state != TOKEN_STATE_ACTIVE:
            return RefreshResult(tokens=None, failure_reason="invalid_or_expired_token")
        jti = payload.get("jti")
        session_id = payload.get("sid")
        session_record = None
        if session_id:
            session_record = await self._tokens.get_active_user_session(session_id)
            if session_record is None or session_record.user_id != payload["sub"]:
                return RefreshResult(tokens=None, failure_reason="token_invalidated")
            if session_record.refresh_jti != jti:
                return RefreshResult(tokens=None, failure_reason="revoked_or_reused_token")
        user = await self.session.get(User, payload["sub"])
        if not user or not user.is_active:
            return RefreshResult(tokens=None, failure_reason="invalid_or_expired_token")
        if not self._token_version_matches_user(payload, user):
            return RefreshResult(tokens=None, failure_reason="token_invalidated")
        if payload.get("ver") is None and self._legacy_token_is_invalidated(
            payload,
            user=user,
            ttl=timedelta(days=self._settings.jwt_refresh_token_expire_days),
        ):
            return RefreshResult(tokens=None, failure_reason="token_invalidated")
        # Rotate: revoke old refresh token, issue new pair
        active_session_id = session_id or f"sess_{uuid4().hex}"
        token_version = self._user_token_version(user)
        access_token, access_jti, access_exp = self._create_access_token(
            user.id,
            session_id=active_session_id,
            token_version=token_version,
        )
        new_refresh, refresh_jti, refresh_exp = self._create_refresh_token(
            user.id,
            session_id=active_session_id,
            token_version=token_version,
        )
        if jti:
            exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
            await self._tokens.revoke_with_commit(jti, exp, commit=False)
        if session_record is None:
            await self._tokens.create_user_session(
                session_id=active_session_id,
                user_id=user.id,
                access_jti=access_jti,
                refresh_jti=refresh_jti,
                access_expires_at=access_exp,
                refresh_expires_at=refresh_exp,
                commit=False,
            )
        else:
            await self._tokens.rotate_user_session(
                session_record,
                access_jti=access_jti,
                refresh_jti=refresh_jti,
                access_expires_at=access_exp,
                refresh_expires_at=refresh_exp,
                commit=False,
            )
        await self.session.commit()
        if jti:
            await self._tokens.cache_revoked_token(jti, exp)
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
        exp = self._payload_expiry(payload)
        if await self._tokens.get_token_state(jti, expires_at=exp) != TOKEN_STATE_ACTIVE:
            return False
        return await self._tokens.revoke(jti, exp)

    async def list_sessions(
        self,
        *,
        user_id: str,
        current_session_id: str | None = None,
    ) -> list[AuthSessionRead]:
        sessions = await self._tokens.list_user_sessions(user_id)
        return [
            self._session_to_read(session, current_session_id=current_session_id)
            for session in sessions
        ]

    async def revoke_session(self, *, user_id: str, session_id: str) -> bool:
        session = await self._tokens.get_user_session(session_id)
        if session is None or session.user_id != user_id:
            return False
        if session.revoked_at is not None:
            return False

        now = datetime.now(UTC)
        access_expires_at = self._normalize_datetime(session.access_expires_at)
        refresh_expires_at = self._normalize_datetime(session.refresh_expires_at)
        if access_expires_at > now:
            await self._tokens.revoke_with_commit(
                session.access_jti,
                access_expires_at,
                commit=False,
            )
        if refresh_expires_at > now:
            await self._tokens.revoke_with_commit(
                session.refresh_jti,
                refresh_expires_at,
                commit=False,
            )
        await self._tokens.revoke_user_session(session, now=now, commit=False)
        await self.session.commit()
        if access_expires_at > now:
            await self._tokens.cache_revoked_token(session.access_jti, access_expires_at)
        if refresh_expires_at > now:
            await self._tokens.cache_revoked_token(session.refresh_jti, refresh_expires_at)
        return True

    async def revoke_session_by_token(self, token: str) -> bool:
        payload = self.decode_token(token)
        if not payload:
            return False
        session_id = payload.get("sid")
        subject = payload.get("sub")
        if not session_id or not subject:
            return False
        return await self.revoke_session(user_id=subject, session_id=session_id)

    async def change_password(
        self,
        *,
        user_id: str,
        organization_id: str,
        new_password: str,
    ) -> bool:
        user = await self.session.get(User, user_id)
        if not user:
            return False
        invalidated_at = datetime.now(UTC).replace(microsecond=0)
        user.password_hash = hash_password(new_password)
        self.invalidate_user_token_state(user, now=invalidated_at)
        revocations = await self._tokens.revoke_all_user_sessions(
            user.id,
            now=invalidated_at,
            commit=False,
        )
        await commit_security_critical_audit(
            self.session,
            current_user_id=user_id,
            action="auth.change_password",
            resource_type="user",
            resource_id=user_id,
            detail={"organization_id": organization_id},
        )
        await self._cache_session_revocations(revocations)
        return True

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
        revocations: list[SessionTokenRevocation] = []

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
            self.invalidate_user_token_state(user, now=reset_timestamp)
            revocations = await self._tokens.revoke_all_user_sessions(
                user.id,
                now=reset_timestamp,
                commit=False,
            )
            await self._tokens.invalidate_active_password_reset_tokens(
                user.id,
                now=reset_timestamp,
                commit=False,
            )

        await self._cache_session_revocations(revocations)
        return True
