from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RevokedToken


class TokenRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def is_revoked(self, jti: str) -> bool:
        result = await self.session.execute(
            select(RevokedToken).where(
                RevokedToken.jti == jti,
                RevokedToken.expires_at > datetime.now(UTC),
            )
        )
        return result.scalar_one_or_none() is not None

    async def revoke(self, jti: str, expires_at: datetime) -> None:
        existing = await self.session.get(RevokedToken, jti)
        if existing:
            return
        self.session.add(RevokedToken(jti=jti, expires_at=expires_at))
        await self.session.commit()

    async def delete_expired(self) -> int:
        result = await self.session.execute(
            delete(RevokedToken).where(RevokedToken.expires_at <= datetime.now(UTC))
        )
        await self.session.commit()
        return result.rowcount
