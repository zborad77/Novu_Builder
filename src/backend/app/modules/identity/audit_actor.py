"""Implementace portu audit.ActorLookup: e-mail a organizace uživatele pro audit záznam."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import User


async def lookup_audit_actor(session: AsyncSession, user_id: str) -> tuple[str, str | None] | None:
    user = await session.get(User, user_id)
    if user is None:
        return None
    return user.email, user.organization_id
