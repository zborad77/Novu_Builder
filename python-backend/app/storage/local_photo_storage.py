import asyncio
import re
import shutil
from io import BytesIO
from pathlib import Path
from time import time_ns
from uuid import uuid4

import structlog

logger = structlog.get_logger(__name__)


def _resolve_storage_root() -> Path:
    import os
    env_val = os.getenv("STORAGE_ROOT", "").strip()
    if env_val:
        return Path(env_val)
    return Path(__file__).resolve().parents[3] / "storage"


STORAGE_ROOT = _resolve_storage_root()

# R-22 / R-44: single place for public URL generation.
# Local/dev storage maps storage keys to the /mock-storage/ dev route.
# Replace this function (or swap the module) for production CDN/S3 URLs
# without touching any service-layer code.
def get_public_url(storage_key: str) -> str:
    """Return the public URL for a given relative storage key."""
    return f"/mock-storage/{storage_key}"


# Canonical subdirectories — all persistent data lives here
UPLOADS_ROOT = STORAGE_ROOT / "projects"   # photo uploads: projects/{project_id}/{filename}
EXPORTS_ROOT = STORAGE_ROOT / "exports"    # generated exports: exports/{case_id}/{export_id}-{filename}


def ensure_directory(target_directory: Path) -> None:
    target_directory.mkdir(parents=True, exist_ok=True)


def sanitize_filename(filename: str | None) -> str:
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", (filename or "upload.bin").strip())
    safe_name = re.sub(r"-+", "-", safe_name).strip("-")
    return safe_name or "upload.bin"


# ── R-15: resize helper ───────────────────────────────────────────────────────

def resize_image_bytes(content: bytes, max_edge: int) -> bytes:
    """Resize image so the longer edge is at most max_edge px.

    Returns JPEG bytes on success. Falls back to original bytes if Pillow
    cannot parse the content (e.g. non-image binary files).
    """
    try:
        from PIL import Image
        img = Image.open(BytesIO(content))
        img_format = img.format or "JPEG"
        img.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        output = BytesIO()
        save_format = img_format if img_format in ("JPEG", "PNG", "WEBP") else "JPEG"
        if save_format == "JPEG":
            # Convert palette/RGBA modes that JPEG cannot handle
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.save(output, format="JPEG", quality=85, optimize=True)
        else:
            img.save(output, format=save_format)
        return output.getvalue()
    except Exception as exc:
        logger.warning("storage.resize_fallback", max_edge=max_edge, error=str(exc))
        return content


def get_image_dimensions(content: bytes) -> tuple[int | None, int | None]:
    """Return (width, height) from image bytes, or (None, None) on failure."""
    try:
        from PIL import Image
        img = Image.open(BytesIO(content))
        return img.size  # (width, height)
    except Exception:
        return None, None


_ALLOWED_IMAGE_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


def validate_image_format(content: bytes) -> None:
    """Reject files not recognised as JPEG, PNG, or WEBP by inspecting actual bytes
    (magic-byte detection via Pillow), regardless of the client-supplied Content-Type.

    Raises ValueError for non-image data or disallowed formats.
    """
    from PIL import Image, UnidentifiedImageError
    try:
        img = Image.open(BytesIO(content))
        fmt = img.format
    except (UnidentifiedImageError, Exception):
        raise ValueError("Unsupported file type: only JPEG, PNG, and WEBP images are accepted.")
    if fmt not in _ALLOWED_IMAGE_FORMATS:
        raise ValueError(f"Unsupported file type '{fmt}': only JPEG, PNG, and WEBP are accepted.")


# ── Sync helpers (wrapped by async public API) ────────────────────────────────

def _sync_save_original_photo(
    *, project_id: str, original_filename: str | None, content: bytes
) -> tuple[str, Path]:
    safe_filename = sanitize_filename(original_filename)
    relative_directory = Path("projects") / project_id
    target_directory = UPLOADS_ROOT / project_id
    stored_filename = f"{time_ns()}-{uuid4().hex[:8]}-{safe_filename}"
    relative_storage_key = (relative_directory / stored_filename).as_posix()
    absolute_path = STORAGE_ROOT / relative_storage_key
    try:
        ensure_directory(target_directory)
        absolute_path.write_bytes(content)
    except OSError as exc:
        logger.error(
            "storage.write_failed",
            storage_key=relative_storage_key,
            error=str(exc),
            exc_info=True,
        )
        raise
    return relative_storage_key, absolute_path


def _sync_write_storage_file(*, relative_storage_key: str, content: bytes) -> Path:
    absolute_path = STORAGE_ROOT / relative_storage_key
    try:
        ensure_directory(absolute_path.parent)
        absolute_path.write_bytes(content)
    except OSError as exc:
        logger.error(
            "storage.write_failed",
            storage_key=relative_storage_key,
            error=str(exc),
            exc_info=True,
        )
        raise
    return absolute_path


def _sync_copy_storage_file(*, source_storage_key: str, target_storage_key: str) -> Path:
    source_path = STORAGE_ROOT / source_storage_key
    target_path = STORAGE_ROOT / target_storage_key
    try:
        ensure_directory(target_path.parent)
        shutil.copy2(source_path, target_path)
    except OSError as exc:
        logger.error(
            "storage.copy_failed",
            source_key=source_storage_key,
            target_key=target_storage_key,
            error=str(exc),
            exc_info=True,
        )
        raise
    return target_path


def _sync_delete_storage_file(*, relative_storage_key: str) -> None:
    """Delete a file from storage. Safe when file does not exist."""
    absolute_path = STORAGE_ROOT / relative_storage_key
    try:
        absolute_path.unlink(missing_ok=True)
    except OSError as exc:
        # missing_ok=True already handles FileNotFoundError — any remaining
        # OSError (e.g. EACCES, EBUSY) means the file was NOT deleted.
        logger.warning(
            "storage.delete_failed",
            storage_key=relative_storage_key,
            error=str(exc),
            exc_info=True,
        )


# ── R-16: async public API (offloads blocking I/O off the event loop) ─────────

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
    """R-14: async-safe delete; silent if file is already absent."""
    await asyncio.to_thread(
        _sync_delete_storage_file,
        relative_storage_key=relative_storage_key,
    )
