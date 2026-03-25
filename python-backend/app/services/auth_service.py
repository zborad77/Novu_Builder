from datetime import UTC, datetime, timedelta
from uuid import uuid4

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import User
from app.repositories.token_repository import TokenRepository
from app.schemas.auth import AuthUserRead


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


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

    def decode_token(self, token: str) -> dict | None:
        try:
            return jwt.decode(token, self._settings.jwt_secret, algorithms=[self._settings.jwt_algorithm])
        except jwt.PyJWTError:
            return None

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
        payload = self.decode_token(token)
        if not payload or payload.get("type") != "access":
            return None
        jti = payload.get("jti")
        if jti and await self._tokens.is_revoked(jti):
            return None
        user = await self.session.get(User, payload["sub"])
        if not user or not user.is_active:
            return None
        result = _user_to_read(user)
        impersonated_by = payload.get("impersonated_by")
        if impersonated_by:
            result = result.model_copy(update={"impersonatedBy": impersonated_by})
        return result

    async def refresh(self, refresh_token: str) -> tuple[str, str, AuthUserRead] | None:
        payload = self.decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return None
        jti = payload.get("jti")
        if jti and await self._tokens.is_revoked(jti):
            return None
        user = await self.session.get(User, payload["sub"])
        if not user or not user.is_active:
            return None
        # Rotate: revoke old refresh token, issue new pair
        if jti:
            exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
            await self._tokens.revoke(jti, exp)
        access_token, _, _ = self._create_access_token(user.id)
        new_refresh, _, _ = self._create_refresh_token(user.id)
        return access_token, new_refresh, _user_to_read(user)

    async def revoke_token(self, token: str) -> None:
        """Revoke any token (access or refresh) by its jti."""
        payload = self.decode_token(token)
        if not payload:
            return
        jti = payload.get("jti")
        if not jti:
            return
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        await self._tokens.revoke(jti, exp)
