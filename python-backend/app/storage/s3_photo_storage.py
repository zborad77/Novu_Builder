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
import os
from pathlib import Path
from time import time_ns
from uuid import uuid4

import structlog

from app.storage.local_photo_storage import sanitize_filename

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

    kwargs: dict = {
        "region_name": os.getenv("S3_REGION", "us-east-1"),
        "config": Config(
            connect_timeout=_configured_s3_timeout("S3_CONNECT_TIMEOUT_SECONDS", 3.0),
            read_timeout=_configured_s3_timeout("S3_READ_TIMEOUT_SECONDS", 10.0),
            retries={"mode": "standard", "max_attempts": 3},
        ),
    }
    access_key = os.getenv("S3_ACCESS_KEY_ID", "")
    secret_key = os.getenv("S3_SECRET_ACCESS_KEY", "")
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key

    endpoint_url = os.getenv("S3_ENDPOINT_URL", "")
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


async def save_original_photo(
    *, project_id: str, original_filename: str | None, content: bytes
) -> tuple[str, Path]:
    return await asyncio.to_thread(
        _sync_save_original_photo,
        project_id=project_id,
        original_filename=original_filename,
        content=content,
    )


async def write_storage_file(*, relative_storage_key: str, content: bytes) -> Path:
    return await asyncio.to_thread(
        _sync_write_storage_file,
        relative_storage_key=relative_storage_key,
        content=content,
    )


async def copy_storage_file(*, source_storage_key: str, target_storage_key: str) -> Path:
    return await asyncio.to_thread(
        _sync_copy_storage_file,
        source_storage_key=source_storage_key,
        target_storage_key=target_storage_key,
    )


async def read_storage_file(*, relative_storage_key: str) -> bytes | None:
    return await asyncio.to_thread(
        _sync_read_storage_file,
        relative_storage_key=relative_storage_key,
    )


async def storage_key_exists(*, relative_storage_key: str) -> bool:
    return await asyncio.to_thread(
        _sync_storage_key_exists,
        relative_storage_key=relative_storage_key,
    )


async def list_storage_keys(*, prefix: str | None = None) -> list[str]:
    return await asyncio.to_thread(
        _sync_list_storage_keys,
        prefix=prefix,
    )


async def delete_storage_file(*, relative_storage_key: str) -> None:
    await asyncio.to_thread(
        _sync_delete_storage_file,
        relative_storage_key=relative_storage_key,
    )
