"""Porty modulu media – volání do modulů nad media, propojené v app.composition.wiring.

Neregistrovaný port vyhodí RuntimeError: bezpečnostní tok purge fotky (F0.3) nesmí
tiše přeskočit zneplatnění exportů, které fotku mohou obsahovat.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

# (session, project_id, now) -> počet zneplatněných exportů; nesmí commitovat.
ExportInvalidator = Callable[[AsyncSession, str, datetime], Awaitable[int]]

_export_invalidator: ExportInvalidator | None = None


def register_export_invalidator(invalidator: ExportInvalidator) -> None:
    global _export_invalidator
    _export_invalidator = invalidator


async def invalidate_case_exports(session: AsyncSession, project_id: str, *, now: datetime) -> int:
    if _export_invalidator is None:
        raise RuntimeError(
            "media: export invalidator is not registered (call app.composition.wiring.init_modules())"
        )
    return await _export_invalidator(session, project_id, now)
