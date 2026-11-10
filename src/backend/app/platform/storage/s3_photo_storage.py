"""S3-compatible storage backend (C1).

Implements the same async public API as local_photo_storage.py so it can be
swapped in transparently via the storage backend dispatcher (backend.py).

Required environment variables when STORAGE_BACKEND=s3:
    S3_BUCKET                         - target bucket name
    S3_REGION                         - AWS region (default: us-east-1)
    S3_ACCESS_KEY_ID                  - access key (or use IAM role / instance profile)
    S3_SECRET_ACCESS_KEY              - secret key (or use IAM role / instance profile)
    S3_ENDPOINT_URL                   - custom endpoint for S3-compatible services
                                        (e.g. MinIO, Cloudflare R2); leave empty for AWS
    STORAGE_SIGNED_URL_TTL_SECONDS    - signed GET URL TTL, max 3600 seconds
"""

import asyncio
from datetime import UTC
import os
from pathlib import Path
from time import time_ns, monotonic as _time_mono
from typing import AsyncIterator
from uuid import uuid4

import structlog

from app.platform.metrics import observe_storage_operation
from app.platform.storage.local_photo_storage import (
    DEFAULT_STREAM_CHUNK_SIZE,
    sanitize_filename,
    validate_storage_key,
)

logger = structlog.get_logger(__name__)


def _configured_s3_timeout(env_name: str, default: float) -> float:
    raw = os.getenv(env_name, str(default)).strip() or str(default)
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{env_name} must be a number.") from exc
    if timeout <= 0:
        raise RuntimeError(f"{env_name} must be > 0.")
    return timeout


def _build_s3_client_kwargs() -> dict:
    from botocore.config import Config  # type: ignore[import]

    endpoint_url = os.getenv("S3_ENDPOINT_URL", "")
    config_kwargs: dict = {
        "connect_timeout": _configured_s3_timeout("S3_CONNECT_TIMEOUT_SECONDS", 3.0),
        "read_timeout": _configured_s3_timeout("S3_READ_TIMEOUT_SECONDS", 10.0),
        "retries": {"mode": "standard", "max_attempts": 3},
    }
    if endpoint_url:
        # Self-hosted S3-compatible store (Garage on 127.0.0.1, see
        # docs/security/OBJECT_STORAGE_OPTIONS.md §5.1): path-style addressing
        # (no virtual-host DNS for the bucket) and checksums only where the
        # operation requires them (the boto3 default CRC32 is not universal).
        config_kwargs["s3"] = {"addressing_style": "path"}
        config_kwargs["request_checksum_calculation"] = "when_required"
        config_kwargs["response_checksum_validation"] = "when_required"

    kwargs: dict = {
        "region_name": os.getenv("S3_REGION", "us-east-1"),
        "config": Config(**config_kwargs),
    }
    access_key = os.getenv("S3_ACCESS_KEY_ID", "")
    secret_key = os.getenv("S3_SECRET_ACCESS_KEY", "")
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key

    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return kwargs


def _get_s3_client():
    """Return a boto3 S3 client configured from environment variables."""
    import boto3  # type: ignore[import]

    return boto3.client("s3", **_build_s3_client_kwargs())


def _s3_bucket() -> str:
    bucket = os.getenv("S3_BUCKET", "")
    if not bucket:
        raise RuntimeError("S3_BUCKET environment variable is not set.")
    return bucket


def _configured_signed_url_ttl() -> int:
    raw = os.getenv("STORAGE_SIGNED_URL_TTL_SECONDS", "3600").strip() or "3600"
    try:
        ttl = int(raw)
    except ValueError as exc:
        raise RuntimeError("STORAGE_SIGNED_URL_TTL_SECONDS must be an integer.") from exc
    if ttl < 1 or ttl > 3600:
        raise RuntimeError(
            "STORAGE_SIGNED_URL_TTL_SECONDS must be between 1 and 3600 seconds."
        )
    return ttl


def generate_presigned_url(storage_key: str, expires: int = 3600) -> str:
    """Return a signed GET URL for the given S3 object key."""
    effective_expires = _configured_signed_url_ttl() if expires == 3600 else expires
    if effective_expires < 1 or effective_expires > 3600:
        raise ValueError("Signed storage URL expiry must be between 1 and 3600 seconds.")

    client = _get_s3_client()
    return client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": _s3_bucket(), "Key": storage_key},
        ExpiresIn=effective_expires,
    )


def get_public_url(storage_key: str) -> str:
    """Backward-compatible alias for signed storage URLs."""
    return generate_presigned_url(storage_key)


def _sync_save_original_photo(
    *, project_id: str, original_filename: str | None, content: bytes
) -> tuple[str, Path]:
    safe_filename = sanitize_filename(original_filename)
    stored_filename = f"{time_ns()}-{uuid4().hex[:8]}-{safe_filename}"
    storage_key = f"projects/{project_id}/{stored_filename}"

    client = _get_s3_client()
    client.put_object(Bucket=_s3_bucket(), Key=storage_key, Body=content)
    return storage_key, Path(storage_key)


def _sync_write_storage_file(*, relative_storage_key: str, content: bytes) -> Path:
    client = _get_s3_client()
    client.put_object(Bucket=_s3_bucket(), Key=relative_storage_key, Body=content)
    return Path(relative_storage_key)


def _sync_copy_storage_file(*, source_storage_key: str, target_storage_key: str) -> Path:
    bucket = _s3_bucket()
    client = _get_s3_client()
    client.copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": source_storage_key},
        Key=target_storage_key,
    )
    return Path(target_storage_key)


def _sync_read_storage_file(*, relative_storage_key: str) -> bytes | None:
    try:
        client = _get_s3_client()
        response = client.get_object(Bucket=_s3_bucket(), Key=relative_storage_key)
        return response["Body"].read()
    except Exception as exc:
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404"}:
            return None
        logger.error(
            "storage.read_failed",
            storage_key=relative_storage_key,
            error=str(exc),
            exc_info=True,
        )
        raise


def _sync_storage_key_exists(*, relative_storage_key: str) -> bool:
    try:
        client = _get_s3_client()
        client.head_object(Bucket=_s3_bucket(), Key=relative_storage_key)
        return True
    except Exception as exc:
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404", "NotFound"}:
            return False
        logger.error(
            "storage.exists_failed",
            storage_key=relative_storage_key,
            error=str(exc),
            exc_info=True,
        )
        raise


def _sync_list_storage_keys(*, prefix: str | None = None) -> list[str]:
    client = _get_s3_client()
    paginator = client.get_paginator("list_objects_v2")
    keys: list[str] = []

    pagination_kwargs = {"Bucket": _s3_bucket()}
    if prefix:
        pagination_kwargs["Prefix"] = prefix

    for page in paginator.paginate(**pagination_kwargs):
        for item in page.get("Contents", []):
            key = item.get("Key")
            if isinstance(key, str) and key:
                keys.append(key)
    keys.sort()
    return keys


def _sync_list_storage_objects(*, prefix: str | None = None) -> list[dict[str, object]]:
    client = _get_s3_client()
    paginator = client.get_paginator("list_objects_v2")
    objects: list[dict[str, object]] = []

    pagination_kwargs = {"Bucket": _s3_bucket()}
    if prefix:
        pagination_kwargs["Prefix"] = prefix

    for page in paginator.paginate(**pagination_kwargs):
        for item in page.get("Contents", []):
            key = item.get("Key")
            if not isinstance(key, str) or not key:
                continue
            last_modified = item.get("LastModified")
            if last_modified is not None and getattr(last_modified, "tzinfo", None) is None:
                last_modified = last_modified.replace(tzinfo=UTC)
            objects.append(
                {
                    "key": key,
                    "last_modified_at": last_modified,
                }
            )
    objects.sort(key=lambda item: str(item["key"]))
    return objects


def _sync_delete_storage_file(*, relative_storage_key: str) -> None:
    try:
        client = _get_s3_client()
        client.delete_object(Bucket=_s3_bucket(), Key=relative_storage_key)
    except Exception as exc:
        logger.warning(
            "storage.delete_failed",
            storage_key=relative_storage_key,
            error=str(exc),
            exc_info=True,
        )


def _sync_verify_storage_health() -> None:
    client = _get_s3_client()
    bucket = _s3_bucket()
    client.head_bucket(Bucket=bucket)
    logger.info(
        "storage.verified",
        backend="s3",
        bucket=bucket,
        endpoint_url_configured=bool(os.getenv("S3_ENDPOINT_URL", "").strip()),
        signed_url_ttl_seconds=_configured_signed_url_ttl(),
    )


async def save_original_photo(
    *, project_id: str, original_filename: str | None, content: bytes
) -> tuple[str, Path]:
    _t0 = _time_mono()
    _outcome = "success"
    try:
        return await asyncio.to_thread(
            _sync_save_original_photo,
            project_id=project_id,
            original_filename=original_filename,
            content=content,
        )
    except Exception:
        _outcome = "error"
        raise
    finally:
        observe_storage_operation(operation="upload", backend="s3", outcome=_outcome, duration_seconds=_time_mono() - _t0)


async def write_storage_file(*, relative_storage_key: str, content: bytes) -> Path:
    _t0 = _time_mono()
    _outcome = "success"
    try:
        return await asyncio.to_thread(
            _sync_write_storage_file,
            relative_storage_key=relative_storage_key,
            content=content,
        )
    except Exception:
        _outcome = "error"
        raise
    finally:
        observe_storage_operation(operation="write", backend="s3", outcome=_outcome, duration_seconds=_time_mono() - _t0)


async def copy_storage_file(*, source_storage_key: str, target_storage_key: str) -> Path:
    _t0 = _time_mono()
    _outcome = "success"
    try:
        return await asyncio.to_thread(
            _sync_copy_storage_file,
            source_storage_key=source_storage_key,
            target_storage_key=target_storage_key,
        )
    except Exception:
        _outcome = "error"
        raise
    finally:
        observe_storage_operation(operation="copy", backend="s3", outcome=_outcome, duration_seconds=_time_mono() - _t0)


async def read_storage_file(*, relative_storage_key: str) -> bytes | None:
    _t0 = _time_mono()
    _outcome = "success"
    try:
        result = await asyncio.to_thread(
            _sync_read_storage_file,
            relative_storage_key=relative_storage_key,
        )
        if result is None:
            _outcome = "not_found"
        return result
    except Exception:
        _outcome = "error"
        raise
    finally:
        observe_storage_operation(operation="read", backend="s3", outcome=_outcome, duration_seconds=_time_mono() - _t0)


async def storage_key_exists(*, relative_storage_key: str) -> bool:
    _t0 = _time_mono()
    _outcome = "success"
    try:
        return await asyncio.to_thread(
            _sync_storage_key_exists,
            relative_storage_key=relative_storage_key,
        )
    except Exception:
        _outcome = "error"
        raise
    finally:
        observe_storage_operation(operation="exists", backend="s3", outcome=_outcome, duration_seconds=_time_mono() - _t0)


async def list_storage_keys(*, prefix: str | None = None) -> list[str]:
    _t0 = _time_mono()
    _outcome = "success"
    try:
        return await asyncio.to_thread(
            _sync_list_storage_keys,
            prefix=prefix,
        )
    except Exception:
        _outcome = "error"
        raise
    finally:
        observe_storage_operation(operation="list", backend="s3", outcome=_outcome, duration_seconds=_time_mono() - _t0)


async def list_storage_objects(*, prefix: str | None = None) -> list[dict[str, object]]:
    _t0 = _time_mono()
    _outcome = "success"
    try:
        return await asyncio.to_thread(
            _sync_list_storage_objects,
            prefix=prefix,
        )
    except Exception:
        _outcome = "error"
        raise
    finally:
        observe_storage_operation(operation="list_objects", backend="s3", outcome=_outcome, duration_seconds=_time_mono() - _t0)


async def delete_storage_file(*, relative_storage_key: str) -> None:
    _t0 = _time_mono()
    _outcome = "success"
    try:
        await asyncio.to_thread(
            _sync_delete_storage_file,
            relative_storage_key=relative_storage_key,
        )
    except Exception:
        _outcome = "error"
        raise
    finally:
        observe_storage_operation(operation="delete", backend="s3", outcome=_outcome, duration_seconds=_time_mono() - _t0)


async def verify_storage_health() -> None:
    await asyncio.to_thread(_sync_verify_storage_health)


# ── NC-007 kap. 6: čtení po blocích pro streamovací endpointy ────────────────


def _is_missing_object_error(exc: Exception) -> bool:
    error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
    return error_code in {"NoSuchKey", "404", "NotFound"}


def _sync_get_storage_object_size(*, relative_storage_key: str) -> int | None:
    validate_storage_key(relative_storage_key)
    try:
        client = _get_s3_client()
        response = client.head_object(Bucket=_s3_bucket(), Key=relative_storage_key)
    except Exception as exc:
        if _is_missing_object_error(exc):
            return None
        logger.error(
            "storage.stat_failed",
            storage_key=relative_storage_key,
            error=str(exc),
            exc_info=True,
        )
        raise
    return int(response["ContentLength"])


async def get_storage_object_size(*, relative_storage_key: str) -> int | None:
    """Velikost objektu v bajtech, ``None`` když objekt neexistuje."""
    _t0 = _time_mono()
    _outcome = "success"
    try:
        size = await asyncio.to_thread(
            _sync_get_storage_object_size,
            relative_storage_key=relative_storage_key,
        )
        if size is None:
            _outcome = "not_found"
        return size
    except Exception:
        _outcome = "error"
        raise
    finally:
        observe_storage_operation(operation="stat", backend="s3", outcome=_outcome, duration_seconds=_time_mono() - _t0)


def _sync_open_object_body(*, relative_storage_key: str, start: int, end: int | None):
    client = _get_s3_client()
    kwargs = {"Bucket": _s3_bucket(), "Key": relative_storage_key}
    if start or end is not None:
        kwargs["Range"] = f"bytes={start}-{'' if end is None else end}"
    return client.get_object(**kwargs)["Body"]


async def iter_storage_file(
    *,
    relative_storage_key: str,
    start: int = 0,
    end: int | None = None,
    chunk_size: int = DEFAULT_STREAM_CHUNK_SIZE,
) -> AsyncIterator[bytes]:
    """Čte objekt po blocích (HTTP Range na S3) od ``start`` do ``end`` včetně.

    Tělo se nikdy nenačítá celé do paměti a klient nikdy nedostane URL úložiště.
    """
    validate_storage_key(relative_storage_key)
    if start < 0 or (end is not None and end < start) or chunk_size < 1:
        raise ValueError("Invalid byte range.")
    body = await asyncio.to_thread(
        _sync_open_object_body,
        relative_storage_key=relative_storage_key,
        start=start,
        end=end,
    )
    try:
        while True:
            chunk = await asyncio.to_thread(body.read, chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        await asyncio.to_thread(body.close)
