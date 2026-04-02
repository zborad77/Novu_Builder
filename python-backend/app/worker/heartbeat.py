from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import socket
import tempfile
from datetime import UTC, datetime

WORKER_HEARTBEAT_LEGACY_KEY = "worker:heartbeat"
WORKER_HEARTBEAT_KEY_PREFIX = f"{WORKER_HEARTBEAT_LEGACY_KEY}:"
WORKER_HEARTBEAT_KEY_PATTERN = f"{WORKER_HEARTBEAT_KEY_PREFIX}*"
WORKER_HEARTBEAT_INTERVAL = 30
WORKER_HEARTBEAT_TTL = 120
WORKER_HEARTBEAT_FRESHNESS_SECONDS = 90
WORKER_LOCAL_HEALTH_PATH_ENV = "WORKER_HEALTH_PATH"
WORKER_LOCAL_HEALTH_FILENAME = "novu-worker-heartbeat.json"

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


def worker_local_health_path() -> Path:
    configured = os.getenv(WORKER_LOCAL_HEALTH_PATH_ENV)
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / WORKER_LOCAL_HEALTH_FILENAME


def _write_local_worker_heartbeat_sync(instance_id: str, *, now: datetime | None = None) -> Path:
    target = worker_local_health_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(f"{target.suffix}.tmp")
    payload = {
        "instance_id": instance_id,
        "timestamp": (now or datetime.now(UTC)).isoformat(),
    }
    tmp_path.write_text(json.dumps(payload), encoding="utf-8")
    tmp_path.replace(target)
    return target


async def write_local_worker_heartbeat(instance_id: str, *, now: datetime | None = None) -> Path:
    return await asyncio.to_thread(
        _write_local_worker_heartbeat_sync,
        instance_id,
        now=now,
    )


def _clear_local_worker_heartbeat_sync() -> None:
    try:
        worker_local_health_path().unlink(missing_ok=True)
    except Exception:
        pass


async def clear_local_worker_heartbeat() -> None:
    await asyncio.to_thread(_clear_local_worker_heartbeat_sync)


def local_worker_heartbeat_is_fresh(*, now: datetime | None = None) -> bool:
    path = worker_local_health_path()
    if not path.exists():
        return False

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False

    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, str):
        return False

    try:
        seen_at = datetime.fromisoformat(timestamp)
    except ValueError:
        return False

    if seen_at.tzinfo is None:
        seen_at = seen_at.replace(tzinfo=UTC)
    else:
        seen_at = seen_at.astimezone(UTC)

    current = now or datetime.now(UTC)
    return (current - seen_at).total_seconds() <= WORKER_HEARTBEAT_FRESHNESS_SECONDS
