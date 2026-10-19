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


async def is_worker_instance_alive(
    redis,
    instance_id: str | None,
    *,
    now: datetime | None = None,
    freshness_seconds: int = WORKER_HEARTBEAT_FRESHNESS_SECONDS,
) -> bool | None:
    if redis is None or not instance_id:
        return None
    raw = await redis.get(worker_heartbeat_key(instance_id))
    seen_at = _payload_timestamp({"timestamp": raw.decode("utf-8") if isinstance(raw, bytes) else raw}) if raw is not None else None
    if seen_at is None:
        return False
    current = now or datetime.now(UTC)
    return (current - seen_at).total_seconds() < max(1, int(freshness_seconds))


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
        "pid": os.getpid(),
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


async def scan_alive_workers(redis) -> tuple[int, str | None]:
    """Scan all worker heartbeat keys in Redis.

    Returns ``(alive_count, last_seen_at_iso)``:
    - *alive_count* — number of workers whose heartbeat is fresher than
      ``WORKER_HEARTBEAT_FRESHNESS_SECONDS``.
    - *last_seen_at_iso* — ISO timestamp of the most recently seen worker,
      or ``None`` when no heartbeat exists.

    Returns ``(-1, None)`` when Redis is unavailable or the scan fails.
    """
    if redis is None:
        return -1, None
    try:
        now = datetime.now(UTC)
        timestamps: list[datetime] = []

        scan_iter = getattr(redis, "scan_iter", None)
        if scan_iter is not None:
            keys: list = []
            async for raw_key in scan_iter(match=WORKER_HEARTBEAT_KEY_PATTERN):
                keys.append(raw_key)
            if keys:
                raw_values = await redis.mget(keys)
                for raw_value in raw_values:
                    if raw_value is None:
                        continue
                    ts = _payload_timestamp(
                        {"timestamp": raw_value.decode("utf-8") if isinstance(raw_value, bytes) else raw_value}
                    )
                    if ts is not None:
                        timestamps.append(ts)

        raw_legacy = await redis.get(WORKER_HEARTBEAT_LEGACY_KEY)
        if raw_legacy is not None:
            ts = _payload_timestamp(
                {"timestamp": raw_legacy.decode("utf-8") if isinstance(raw_legacy, bytes) else raw_legacy}
            )
            if ts is not None:
                timestamps.append(ts)

        if not timestamps:
            return 0, None

        last_seen_at = max(timestamps).isoformat()
        alive_count = sum(
            1 for ts in timestamps
            if (now - ts).total_seconds() < WORKER_HEARTBEAT_FRESHNESS_SECONDS
        )
        return alive_count, last_seen_at
    except Exception:
        return -1, None


def _read_local_worker_heartbeat_payload() -> dict | None:
    path = worker_local_health_path()
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _payload_timestamp(payload: dict) -> datetime | None:
    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, str):
        return None

    try:
        seen_at = datetime.fromisoformat(timestamp)
    except ValueError:
        return None

    if seen_at.tzinfo is None:
        seen_at = seen_at.replace(tzinfo=UTC)
    else:
        seen_at = seen_at.astimezone(UTC)
    return seen_at


def _payload_pid(payload: dict) -> int | None:
    pid = payload.get("pid")
    if isinstance(pid, bool):
        return None
    if isinstance(pid, int) and pid > 0:
        return pid
    return None


def worker_pid_is_healthy(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False

    proc_dir = Path("/proc") / str(pid)
    if proc_dir.exists():
        try:
            stat_parts = (proc_dir / "stat").read_text(encoding="utf-8").split()
        except Exception:
            return False
        if len(stat_parts) < 3 or stat_parts[2] == "Z":
            return False

        try:
            cmdline = (proc_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
        except Exception:
            return False
        return "app.worker.runner" in cmdline

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def local_worker_heartbeat_status(
    *,
    now: datetime | None = None,
    require_process: bool = False,
) -> tuple[bool, str]:
    payload = _read_local_worker_heartbeat_payload()
    if payload is None:
        return False, "missing_or_invalid"

    seen_at = _payload_timestamp(payload)
    if seen_at is None:
        return False, "invalid_timestamp"

    current = now or datetime.now(UTC)
    if (current - seen_at).total_seconds() > WORKER_HEARTBEAT_FRESHNESS_SECONDS:
        return False, "stale"

    if require_process:
        pid = _payload_pid(payload)
        if pid is None:
            return False, "pid_missing"
        if not worker_pid_is_healthy(pid):
            return False, "worker_process_unhealthy"

    return True, "fresh"


def local_worker_heartbeat_is_fresh(
    *,
    now: datetime | None = None,
    require_process: bool = False,
) -> bool:
    healthy, _ = local_worker_heartbeat_status(
        now=now,
        require_process=require_process,
    )
    return healthy
