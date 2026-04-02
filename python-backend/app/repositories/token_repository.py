import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Literal

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.metrics import observe_cache_operation
from app.core.token_limits import JTI_MAX_LENGTH
from app.models import PasswordResetToken, RevokedToken, UserSession

_MAX_PASSWORD_RESET_TOKEN_LENGTH = 512
_REVOKED_TOKEN_CACHE_NAMESPACE = "revoked-token"
_REVOKED_TOKEN_CACHE_PREFIX = "cache:"
_REVOKED_TOKEN_CACHE_ENTRY_VERSION = 1
_REVOKED_TOKEN_CACHE_TAG = "revoked-token-v1"
TOKEN_STATE_ACTIVE: Literal["active"] = "active"
TOKEN_STATE_REVOKED: Literal["revoked"] = "revoked"
TOKEN_STATE_EXPIRED: Literal["expired"] = "expired"
TokenState = Literal["active", "revoked", "expired"]


@dataclass(frozen=True)
class ClaimedPasswordResetToken:
    token_hash: str
    user_id: str
    expires_at: datetime
    used_at: datetime


@dataclass(frozen=True)
class SessionTokenRevocation:
    jti: str
    expires_at: datetime


class TokenStateBackendUnavailableError(RuntimeError):
    """Raised when a shared token-state optimization cannot be used."""

    def __init__(
        self,
        *,
        operation: str,
        jti: str | None,
        cause: Exception | None = None,
    ) -> None:
        self.operation = operation
        self.jti = jti
        self.cause = cause
        super().__init__(
            f"Shared token-state backend is unavailable during {operation}"
            f"{f' for {jti!r}' if jti else ''}."
        )


class TokenRepository:
    def __init__(self, session: AsyncSession, redis=None):
        self.session = session
        self.redis = redis

    @staticmethod
    def _revoked_cache_key(jti: str) -> str:
        return f"{_REVOKED_TOKEN_CACHE_PREFIX}{_REVOKED_TOKEN_CACHE_NAMESPACE}:{jti}"

    def _raise_backend_unavailable(
        self,
        *,
        operation: str,
        jti: str | None,
        error: Exception | None = None,
    ) -> None:
        raise TokenStateBackendUnavailableError(
            operation=operation,
            jti=jti,
            cause=error,
        ) from error

    @staticmethod
    def _decode_cached_revoked_state(raw: object) -> bool | None:
        if raw is None:
            return None

        decoded = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw)
        if decoded == TOKEN_STATE_REVOKED:
            return True

        try:
            payload = json.loads(decoded)
        except json.JSONDecodeError:
            return None

        if not isinstance(payload, dict):
            return None
        if payload.get("revoked") is True:
            return True
        meta = payload.get("meta")
        if not isinstance(meta, dict):
            return None
        if int(meta.get("version", 0) or 0) != _REVOKED_TOKEN_CACHE_ENTRY_VERSION:
            return None
        if meta.get("tag") != _REVOKED_TOKEN_CACHE_TAG:
            return None
        if payload.get("state") == TOKEN_STATE_REVOKED:
            return True
        return None

    @staticmethod
    def _build_revoked_cache_payload(*, ttl_seconds: int) -> str:
        return json.dumps(
            {
                "meta": {
                    "version": _REVOKED_TOKEN_CACHE_ENTRY_VERSION,
                    "tag": _REVOKED_TOKEN_CACHE_TAG,
                    "ttlSeconds": max(1, int(ttl_seconds)),
                },
                "state": TOKEN_STATE_REVOKED,
                "revoked": True,
            }
        )

    async def _write_revoked_cache_entry(self, *, jti: str, ttl_seconds: int) -> None:
        ttl = max(1, int(ttl_seconds))
        if self.redis is None:
            return
        try:
            await self.redis.setex(
                self._revoked_cache_key(jti),
                ttl,
                self._build_revoked_cache_payload(ttl_seconds=ttl),
            )
        except Exception as exc:
            observe_cache_operation(
                namespace=_REVOKED_TOKEN_CACHE_NAMESPACE,
                operation="set",
                outcome="error",
                duration_seconds=0.0,
            )
            return

    async def _cache_revoked_hit(self, *, jti: str, expires_at: datetime) -> None:
        normalized_expiry = expires_at if expires_at.tzinfo is not None else expires_at.replace(tzinfo=UTC)
        ttl_seconds = int((normalized_expiry.astimezone(UTC) - datetime.now(UTC)).total_seconds())
        if ttl_seconds <= 0:
            return
        await self._write_revoked_cache_entry(jti=jti, ttl_seconds=ttl_seconds)

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
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

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
        started_at = perf_counter()
        raw_cached = None
        if self.redis is None:
            observe_cache_operation(
                namespace=_REVOKED_TOKEN_CACHE_NAMESPACE,
                operation="lookup",
                outcome="unavailable",
                duration_seconds=perf_counter() - started_at,
            )
        else:
            try:
                raw_cached = await self.redis.get(self._revoked_cache_key(normalized_jti))
            except Exception:
                observe_cache_operation(
                    namespace=_REVOKED_TOKEN_CACHE_NAMESPACE,
                    operation="lookup",
                    outcome="error",
                    duration_seconds=perf_counter() - started_at,
                )
                raw_cached = None

        cached = self._decode_cached_revoked_state(raw_cached)
        if cached is True:
            observe_cache_operation(
                namespace=_REVOKED_TOKEN_CACHE_NAMESPACE,
                operation="lookup",
                outcome="hit",
                duration_seconds=perf_counter() - started_at,
            )
            return True

        result = await self.session.execute(
            select(RevokedToken).where(
                RevokedToken.jti == normalized_jti,
                RevokedToken.expires_at > datetime.now(UTC),
            )
        )
        record = result.scalar_one_or_none()
        observe_cache_operation(
            namespace=_REVOKED_TOKEN_CACHE_NAMESPACE,
            operation="lookup",
            outcome="db_fallback",
            duration_seconds=perf_counter() - started_at,
        )
        if record is None:
            return False

        await self._cache_revoked_hit(jti=normalized_jti, expires_at=record.expires_at)
        return True

    async def get_token_state(
        self,
        jti: str,
        *,
        expires_at: datetime,
        now: datetime | None = None,
    ) -> TokenState:
        normalized_expiry = self._normalize_datetime(expires_at)
        current_time = self._normalize_datetime(now or datetime.now(UTC))
        if normalized_expiry <= current_time:
            return TOKEN_STATE_EXPIRED
        if await self.is_revoked(jti):
            return TOKEN_STATE_REVOKED
        return TOKEN_STATE_ACTIVE

    async def revoke(self, jti: str, expires_at: datetime) -> bool:
        return await self.revoke_with_commit(jti, expires_at, commit=True)

    async def revoke_with_commit(
        self,
        jti: str,
        expires_at: datetime,
        *,
        commit: bool,
    ) -> bool:
        normalized_jti = self.normalize_jti(jti)
        if normalized_jti is None:
            return False
        existing = await self.session.get(RevokedToken, normalized_jti)
        if existing:
            return False
        self.session.add(RevokedToken(jti=normalized_jti, expires_at=expires_at))
        if commit:
            await self.session.commit()
            await self._cache_revoked_hit(jti=normalized_jti, expires_at=expires_at)
        return True

    async def cache_revoked_token(self, jti: str, expires_at: datetime) -> bool:
        normalized_jti = self.normalize_jti(jti)
        if normalized_jti is None:
            return False
        await self._cache_revoked_hit(jti=normalized_jti, expires_at=expires_at)
        return self.redis is not None

    async def get_user_session(self, session_id: str) -> UserSession | None:
        return await self.session.get(UserSession, session_id)

    async def get_active_user_session(
        self,
        session_id: str,
        *,
        now: datetime | None = None,
    ) -> UserSession | None:
        current_time = now or datetime.now(UTC)
        result = await self.session.execute(
            select(UserSession).where(
                UserSession.id == session_id,
                UserSession.revoked_at.is_(None),
                UserSession.refresh_expires_at > current_time,
            )
        )
        return result.scalar_one_or_none()

    async def list_user_sessions(self, user_id: str) -> list[UserSession]:
        result = await self.session.execute(
            select(UserSession)
            .where(UserSession.user_id == user_id)
            .order_by(UserSession.created_at.desc(), UserSession.id.desc())
        )
        return list(result.scalars().all())

    async def create_user_session(
        self,
        *,
        session_id: str,
        user_id: str,
        access_jti: str,
        refresh_jti: str,
        access_expires_at: datetime,
        refresh_expires_at: datetime,
        commit: bool = True,
    ) -> UserSession:
        record = UserSession(
            id=session_id,
            user_id=user_id,
            access_jti=access_jti,
            refresh_jti=refresh_jti,
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
            revoked_at=None,
        )
        self.session.add(record)
        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(record)
        return record

    async def rotate_user_session(
        self,
        session: UserSession,
        *,
        access_jti: str,
        refresh_jti: str,
        access_expires_at: datetime,
        refresh_expires_at: datetime,
        commit: bool = True,
    ) -> UserSession:
        session.access_jti = access_jti
        session.refresh_jti = refresh_jti
        session.access_expires_at = access_expires_at
        session.refresh_expires_at = refresh_expires_at
        session.revoked_at = None
        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(session)
        return session

    async def revoke_user_session(
        self,
        session: UserSession,
        *,
        now: datetime | None = None,
        commit: bool = True,
    ) -> UserSession:
        session.revoked_at = now or datetime.now(UTC)
        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(session)
        return session

    async def revoke_all_user_sessions(
        self,
        user_id: str,
        *,
        now: datetime | None = None,
        commit: bool = True,
    ) -> list[SessionTokenRevocation]:
        current_time = self._normalize_datetime(now or datetime.now(UTC))
        result = await self.session.execute(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
            )
        )
        sessions = list(result.scalars().all())
        if not sessions:
            return []

        revocations: list[SessionTokenRevocation] = []
        for session in sessions:
            session.revoked_at = current_time

            access_expires_at = self._normalize_datetime(session.access_expires_at)
            if access_expires_at > current_time:
                revocations.append(
                    SessionTokenRevocation(
                        jti=session.access_jti,
                        expires_at=access_expires_at,
                    )
                )

            refresh_expires_at = self._normalize_datetime(session.refresh_expires_at)
            if refresh_expires_at > current_time:
                revocations.append(
                    SessionTokenRevocation(
                        jti=session.refresh_jti,
                        expires_at=refresh_expires_at,
                    )
                )

        if revocations:
            revocation_map = {record.jti: record for record in revocations}
            existing_result = await self.session.execute(
                select(RevokedToken.jti).where(RevokedToken.jti.in_(tuple(revocation_map)))
            )
            existing_jtis = set(existing_result.scalars().all())
            for record in revocations:
                if record.jti in existing_jtis:
                    continue
                self.session.add(
                    RevokedToken(
                        jti=record.jti,
                        expires_at=record.expires_at,
                    )
                )

        await self.session.flush()
        if commit:
            await self.session.commit()
            for record in revocations:
                await self._cache_revoked_hit(jti=record.jti, expires_at=record.expires_at)
        return revocations

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
