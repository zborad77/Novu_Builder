from __future__ import annotations

import os
import re
import socket
from datetime import UTC, datetime

WORKER_HEARTBEAT_LEGACY_KEY = "worker:heartbeat"
WORKER_HEARTBEAT_KEY_PREFIX = f"{WORKER_HEARTBEAT_LEGACY_KEY}:"
WORKER_HEARTBEAT_KEY_PATTERN = f"{WORKER_HEARTBEAT_KEY_PREFIX}*"
WORKER_HEARTBEAT_INTERVAL = 30
WORKER_HEARTBEAT_TTL = 120
WORKER_HEARTBEAT_FRESHNESS_SECONDS = 90

_INSTANCE_ID_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_instance_fragment(value: str | None, *, fallback: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return fallback

    sanitized = _INSTANCE_ID_PATTERN.sub("-", normalized).strip("-")
    return sanitized or fallback


def build_worker_instance_id(*, hostname: str | None = None, pid: int | None = None) -> str:
    resolved_hostname = hostname or os.getenv("HOSTNAME") or socket.gethostname()
    safe_hostname = _sanitize_instance_fragment(resolved_hostname, fallback="worker")
    resolved_pid = os.getpid() if pid is None else pid
    return f"{safe_hostname}-{resolved_pid}"


def worker_heartbeat_key(instance_id: str) -> str:
    safe_instance_id = _sanitize_instance_fragment(instance_id, fallback="worker")
    return f"{WORKER_HEARTBEAT_KEY_PREFIX}{safe_instance_id}"


async def write_worker_heartbeat(redis, instance_id: str, *, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(UTC)).isoformat()
    key = worker_heartbeat_key(instance_id)
    await redis.set(key, timestamp, ex=WORKER_HEARTBEAT_TTL)
    return key


async def clear_worker_heartbeat(redis, instance_id: str) -> None:
    try:
        await redis.delete(worker_heartbeat_key(instance_id))
    except Exception:
        pass
