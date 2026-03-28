"""S3-compatible storage backend (C1).

Implements the same async public API as local_photo_storage.py so it can be
swapped in transparently via the storage backend dispatcher (backend.py).

Required environment variables when STORAGE_BACKEND=s3:
    S3_BUCKET              — target bucket name
    S3_REGION              — AWS region (default: us-east-1)
    S3_ACCESS_KEY_ID       — access key (or use IAM role / instance profile)
    S3_SECRET_ACCESS_KEY   — secret key (or use IAM role / instance profile)
    S3_ENDPOINT_URL        — custom endpoint for S3-compatible services
                             (e.g. MinIO, Cloudflare R2); leave empty for AWS
    S3_CDN_BASE_URL        — optional CDN prefix for public URLs
                             (e.g. https://cdn.example.com); falls back to
                             https://<bucket>.s3.<region>.amazonaws.com
"""
import asyncio
import os
from pathlib import Path
from time import time_ns
from uuid import uuid4

from app.storage.local_photo_storage import sanitize_filename


def _get_s3_client():
    """Return a boto3 S3 client configured from environment variables."""
    import boto3  # type: ignore[import]

    kwargs: dict = {
        "region_name": os.getenv("S3_REGION", "us-east-1"),
    }
    access_key = os.getenv("S3_ACCESS_KEY_ID", "")
    secret_key = os.getenv("S3_SECRET_ACCESS_KEY", "")
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key

    endpoint_url = os.getenv("S3_ENDPOINT_URL", "")
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url

    return boto3.client("s3", **kwargs)


def _s3_bucket() -> str:
    bucket = os.getenv("S3_BUCKET", "")
    if not bucket:
        raise RuntimeError("S3_BUCKET environment variable is not set.")
    return bucket


def get_public_url(storage_key: str) -> str:
    """Return a public URL for the given storage key."""
    cdn_base = os.getenv("S3_CDN_BASE_URL", "").rstrip("/")
    if cdn_base:
        return f"{cdn_base}/{storage_key}"
    bucket = _s3_bucket()
    region = os.getenv("S3_REGION", "us-east-1")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{storage_key}"


# ── Sync helpers ──────────────────────────────────────────────────────────────

def _sync_save_original_photo(
    *, project_id: str, original_filename: str | None, content: bytes
) -> tuple[str, Path]:
    safe_filename = sanitize_filename(original_filename)
    stored_filename = f"{time_ns()}-{uuid4().hex[:8]}-{safe_filename}"
    storage_key = f"projects/{project_id}/{stored_filename}"

    client = _get_s3_client()
    client.put_object(Bucket=_s3_bucket(), Key=storage_key, Body=content)
    return storage_key, Path(storage_key)  # Path is a dummy — callers discard it


def _sync_write_storage_file(*, relative_storage_key: str, content: bytes) -> Path:
    client = _get_s3_client()
    client.put_object(Bucket=_s3_bucket(), Key=relative_storage_key, Body=content)
    return Path(relative_storage_key)  # dummy


def _sync_copy_storage_file(*, source_storage_key: str, target_storage_key: str) -> Path:
    bucket = _s3_bucket()
    client = _get_s3_client()
    client.copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": source_storage_key},
        Key=target_storage_key,
    )
    return Path(target_storage_key)  # dummy


def _sync_delete_storage_file(*, relative_storage_key: str) -> None:
    try:
        client = _get_s3_client()
        client.delete_object(Bucket=_s3_bucket(), Key=relative_storage_key)
    except Exception:
        pass  # Silent on error (mirrors local backend behaviour)


# ── Async public API ──────────────────────────────────────────────────────────

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


async def delete_storage_file(*, relative_storage_key: str) -> None:
    await asyncio.to_thread(
        _sync_delete_storage_file,
        relative_storage_key=relative_storage_key,
    )
