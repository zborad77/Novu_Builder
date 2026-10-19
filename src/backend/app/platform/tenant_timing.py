from __future__ import annotations

import asyncio
from time import perf_counter

CACHE_ACCESS_TIMING_FLOOR_SECONDS = 0.004
TENANT_SENSITIVE_TIMING_FLOOR_SECONDS = 0.012


async def enforce_timing_floor(
    started_at: float,
    *,
    minimum_seconds: float,
) -> None:
    remaining = float(minimum_seconds) - (perf_counter() - started_at)
    if remaining > 0:
        await asyncio.sleep(remaining)
