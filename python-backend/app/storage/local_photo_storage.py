import asyncio
import re
import shutil
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath, PureWindowsPath
from time import time_ns
from uuid import uuid4

import structlog
from fastapi import UploadFile

logger = structlog.get_logger(__name__)


def _resolve_storage_root() -> Path:
    import os
    env_val = os.getenv("STORAGE_ROOT", "").strip()
    if env_val:
        return Path(env_val)
    return Path(__file__).resolve().parents[3] / "storage"


STORAGE_ROOT = _resolve_storage_root()

# Local/dev storage maps storage keys to the authenticated /mock-storage route.
def generate_presigned_url(storage_key: str, expires: int = 3600) -> str:
    """Return a deterministic local DEV/TEST URL for the given storage key."""
    if expires < 1 or expires > 3600:
        raise ValueError("Signed storage URL expiry must be between 1 and 3600 seconds.")
    return f"/mock-storage/{storage_key}"


def get_public_url(storage_key: str) -> str:
    """Backward-compatible alias for signed storage URLs."""
    return generate_presigned_url(storage_key)


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


ALLOWED_UPLOAD_IMAGE_EXTENSIONS: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
ALLOWED_UPLOAD_IMAGE_MIME_TYPES = frozenset(ALLOWED_UPLOAD_IMAGE_EXTENSIONS.values())
DECLARED_UPLOAD_IMAGE_MIME_TYPES: dict[str, str] = {
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
    "image/png": "image/png",
    "image/webp": "image/webp",
}
GENERIC_UPLOAD_MIME_TYPES = frozenset({"application/octet-stream"})
_ALLOWED_IMAGE_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
_IMAGE_FORMAT_TO_MIME: dict[str, str] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
_WINDOWS_RESERVED_FILENAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)
_MAX_UPLOAD_FILENAME_LENGTH = 255
_ALLOWED_STORAGE_PREFIXES = frozenset({"projects", "exports"})
MIME_TO_UPLOAD_EXTENSION: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class UploadValidationError(ValueError):
    """Client-visible upload validation error with a sanitized message."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ValidatedImageUpload:
    original_filename: str
    storage_filename: str
    actual_mime_type: str
    content: bytes
    file_size: int
    filename_was_missing: bool
    content_type_was_missing: bool


def _storage_root_resolved() -> Path:
    return STORAGE_ROOT.resolve()


def _validate_storage_namespace_segment(value: str, *, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"Invalid {field_name}: value is required.")
    if any(ord(ch) < 32 for ch in normalized):
        raise ValueError(f"Invalid {field_name}: control characters are not allowed.")
    if PurePosixPath(normalized).name != normalized or PureWindowsPath(normalized).name != normalized:
        raise ValueError(f"Invalid {field_name}: path separators are not allowed.")
    if normalized in {".", ".."}:
        raise ValueError(f"Invalid {field_name}: traversal segments are not allowed.")
    return normalized


def _normalize_relative_storage_key(relative_storage_key: str) -> str:
    normalized = (relative_storage_key or "").strip().replace("\\", "/")
    if not normalized:
        raise ValueError("Invalid storage key: value is required.")
    if normalized.startswith("/"):
        raise ValueError("Invalid storage key: absolute paths are not allowed.")
    windows_path = PureWindowsPath(normalized)
    if windows_path.drive:
        raise ValueError("Invalid storage key: absolute paths are not allowed.")

    parts = PurePosixPath(normalized).parts
    if not parts:
        raise ValueError("Invalid storage key: value is required.")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Invalid storage key: traversal segments are not allowed.")
    if parts[0] not in _ALLOWED_STORAGE_PREFIXES:
        raise ValueError(
            "Invalid storage key: only 'projects/' and 'exports/' storage paths are allowed."
        )
    return PurePosixPath(*parts).as_posix()


def _resolve_storage_path(relative_storage_key: str) -> tuple[str, Path]:
    normalized_key = _normalize_relative_storage_key(relative_storage_key)
    absolute_path = (_storage_root_resolved() / normalized_key).resolve()
    try:
        absolute_path.relative_to(_storage_root_resolved())
    except ValueError as exc:
        raise ValueError("Invalid storage key: resolved path escapes STORAGE_ROOT.") from exc
    return normalized_key, absolute_path


def _normalize_declared_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    normalized = content_type.split(";", 1)[0].strip().lower()
    if not normalized or normalized in GENERIC_UPLOAD_MIME_TYPES:
        return None
    canonical = DECLARED_UPLOAD_IMAGE_MIME_TYPES.get(normalized)
    if canonical is None:
        raise UploadValidationError(
            f"Unsupported Content-Type '{normalized}': "
            "only image/jpeg, image/png, and image/webp uploads are accepted.",
            status_code=415,
        )
    return canonical


def _validate_client_filename(filename: str | None) -> tuple[str | None, str]:
    raw_filename = (filename or "").strip()
    if not raw_filename:
        return None, ""

    if any(ord(ch) < 32 for ch in raw_filename):
        raise UploadValidationError("Invalid filename: control characters are not allowed.")
    if len(raw_filename) > _MAX_UPLOAD_FILENAME_LENGTH:
        raise UploadValidationError(
            f"Invalid filename: filenames longer than {_MAX_UPLOAD_FILENAME_LENGTH} characters are not allowed."
        )

    posix_parts = PurePosixPath(raw_filename).parts
    windows_parts = PureWindowsPath(raw_filename).parts
    if ".." in posix_parts or ".." in windows_parts:
        raise UploadValidationError("Invalid filename: path traversal sequences are not allowed.")
    if PurePosixPath(raw_filename).name != raw_filename or PureWindowsPath(raw_filename).name != raw_filename:
        raise UploadValidationError("Invalid filename: path separators are not allowed.")
    if raw_filename.startswith("."):
        raise UploadValidationError("Invalid filename: a non-empty base name is required.")

    extension = Path(raw_filename).suffix.lower()
    base_name = raw_filename[:-len(extension)] if extension else raw_filename
    if not base_name or not base_name.strip("."):
        raise UploadValidationError("Invalid filename: a non-empty base name is required.")
    if base_name.rstrip(" .").upper() in _WINDOWS_RESERVED_FILENAMES:
        raise UploadValidationError("Invalid filename: reserved device names are not allowed.")

    if extension and extension not in ALLOWED_UPLOAD_IMAGE_EXTENSIONS:
        raise UploadValidationError(
            f"Unsupported file extension '{extension}': "
            "only JPEG, PNG, and WEBP files are accepted.",
            status_code=415,
        )

    return raw_filename, extension


def _build_storage_filename(*, original_filename: str | None, actual_mime_type: str) -> str:
    extension = MIME_TO_UPLOAD_EXTENSION[actual_mime_type]
    if not original_filename:
        candidate = f"upload-{uuid4().hex[:8]}{extension}"
    else:
        candidate = original_filename if Path(original_filename).suffix else f"{original_filename}{extension}"

    safe_filename = sanitize_filename(candidate)
    if not Path(safe_filename).suffix:
        safe_filename = f"{safe_filename}{extension}"
    return safe_filename


async def _read_upload_bytes_limited(file: UploadFile, *, max_bytes: int, max_upload_size_mb: int) -> bytes:
    declared_size = getattr(file, "size", None)
    if isinstance(declared_size, int) and declared_size > max_bytes:
        raise UploadValidationError(
            f"File too large: Content-Length {declared_size} bytes exceeds the "
            f"{max_upload_size_mb} MB upload limit.",
            status_code=413,
        )

    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise UploadValidationError(
            f"File too large: more than {max_bytes} bytes exceeds the "
            f"{max_upload_size_mb} MB upload limit.",
            status_code=413,
        )
    if not content:
        raise UploadValidationError("Invalid file content: upload payload is empty.")
    return content


def validate_image_format(content: bytes) -> str:
    """Reject files not recognised as JPEG, PNG, or WEBP by inspecting actual bytes
    (magic-byte detection via Pillow), regardless of the client-supplied Content-Type.

    Returns the canonical MIME type when valid.
    Raises ValueError for non-image data or disallowed formats.
    """
    from PIL import Image, UnidentifiedImageError
    try:
        buffer = BytesIO(content)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(buffer)
            fmt = img.format
            img.load()
    except UnidentifiedImageError:
        raise UploadValidationError(
            "Unsupported file type: only JPEG, PNG, and WEBP images are accepted.",
            status_code=415,
        )
    except Image.DecompressionBombWarning:
        raise UploadValidationError("Invalid file content: image payload is unsafe or exceeds decoder limits.")
    except Image.DecompressionBombError:
        raise UploadValidationError("Invalid file content: image payload is unsafe or exceeds decoder limits.")
    except OSError:
        raise UploadValidationError("Invalid file content: image payload is truncated or corrupted.")
    except Exception:
        raise UploadValidationError(
            "Unsupported file type: only JPEG, PNG, and WEBP images are accepted.",
            status_code=415,
        )
    if fmt not in _ALLOWED_IMAGE_FORMATS:
        raise UploadValidationError(
            f"Unsupported file type '{fmt}': only JPEG, PNG, and WEBP are accepted.",
            status_code=415,
        )
    try:
        buffer.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            Image.open(buffer).verify()
    except Image.DecompressionBombWarning:
        raise UploadValidationError("Invalid file content: image payload is unsafe or exceeds decoder limits.")
    except Image.DecompressionBombError:
        raise UploadValidationError("Invalid file content: image payload is unsafe or exceeds decoder limits.")
    except Exception:
        raise UploadValidationError("Invalid file content: image payload is truncated or corrupted.")
    return _IMAGE_FORMAT_TO_MIME[fmt]


async def validate_photo_upload(
    file: UploadFile,
    *,
    max_bytes: int,
    max_upload_size_mb: int,
) -> ValidatedImageUpload:
    original_filename, declared_extension = _validate_client_filename(file.filename)
    declared_mime_type = _normalize_declared_content_type(file.content_type)
    content = await _read_upload_bytes_limited(
        file,
        max_bytes=max_bytes,
        max_upload_size_mb=max_upload_size_mb,
    )
    actual_mime_type = validate_image_format(content)
    if declared_mime_type and declared_mime_type != actual_mime_type:
        raise UploadValidationError(
            f"Content-Type mismatch: declared {declared_mime_type!r} but actual image data is "
            f"{actual_mime_type!r}.",
            status_code=415,
        )
    if declared_extension and ALLOWED_UPLOAD_IMAGE_EXTENSIONS[declared_extension] != actual_mime_type:
        raise UploadValidationError(
            f"File extension mismatch: filename extension {declared_extension!r} does not match actual "
            f"image data {actual_mime_type!r}.",
            status_code=415,
        )

    storage_filename = _build_storage_filename(
        original_filename=original_filename,
        actual_mime_type=actual_mime_type,
    )
    return ValidatedImageUpload(
        original_filename=original_filename or storage_filename,
        storage_filename=storage_filename,
        actual_mime_type=actual_mime_type,
        content=content,
        file_size=len(content),
        filename_was_missing=original_filename is None,
        content_type_was_missing=file.content_type is None,
    )


# ── Sync helpers (wrapped by async public API) ────────────────────────────────

def _sync_save_original_photo(
    *, project_id: str, original_filename: str | None, content: bytes
) -> tuple[str, Path]:
    normalized_project_id = _validate_storage_namespace_segment(project_id, field_name="project_id")
    safe_filename = sanitize_filename(original_filename)
    stored_filename = f"{time_ns()}-{uuid4().hex[:8]}-{safe_filename}"
    relative_storage_key, absolute_path = _resolve_storage_path(
        f"projects/{normalized_project_id}/{stored_filename}"
    )
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
    return relative_storage_key, absolute_path


def _sync_write_storage_file(*, relative_storage_key: str, content: bytes) -> Path:
    normalized_storage_key, absolute_path = _resolve_storage_path(relative_storage_key)
    try:
        ensure_directory(absolute_path.parent)
        absolute_path.write_bytes(content)
    except OSError as exc:
        logger.error(
            "storage.write_failed",
            storage_key=normalized_storage_key,
            error=str(exc),
            exc_info=True,
        )
        raise
    return absolute_path


def _sync_copy_storage_file(*, source_storage_key: str, target_storage_key: str) -> Path:
    normalized_source_key, source_path = _resolve_storage_path(source_storage_key)
    normalized_target_key, target_path = _resolve_storage_path(target_storage_key)
    try:
        ensure_directory(target_path.parent)
        shutil.copy2(source_path, target_path)
    except OSError as exc:
        logger.error(
            "storage.copy_failed",
            source_key=normalized_source_key,
            target_key=normalized_target_key,
            error=str(exc),
            exc_info=True,
        )
        raise
    return target_path


def _sync_delete_storage_file(*, relative_storage_key: str) -> None:
    """Delete a file from storage. Safe when file does not exist."""
    normalized_storage_key, absolute_path = _resolve_storage_path(relative_storage_key)
    try:
        absolute_path.unlink(missing_ok=True)
    except OSError as exc:
        # missing_ok=True already handles FileNotFoundError — any remaining
        # OSError (e.g. EACCES, EBUSY) means the file was NOT deleted.
        logger.warning(
            "storage.delete_failed",
            storage_key=normalized_storage_key,
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


def _sync_read_storage_file(*, relative_storage_key: str) -> bytes | None:
    _, absolute_path = _resolve_storage_path(relative_storage_key)
    if not absolute_path.is_file():
        return None
    try:
        return absolute_path.read_bytes()
    except OSError as exc:
        logger.error(
            "storage.read_failed",
            storage_key=relative_storage_key,
            error=str(exc),
            exc_info=True,
        )
        raise


async def read_storage_file(*, relative_storage_key: str) -> bytes | None:
    return await asyncio.to_thread(
        _sync_read_storage_file,
        relative_storage_key=relative_storage_key,
    )


def _sync_storage_key_exists(*, relative_storage_key: str) -> bool:
    _, absolute_path = _resolve_storage_path(relative_storage_key)
    return absolute_path.is_file()


async def storage_key_exists(*, relative_storage_key: str) -> bool:
    return await asyncio.to_thread(
        _sync_storage_key_exists,
        relative_storage_key=relative_storage_key,
    )


def _sync_list_storage_keys(*, prefix: str | None = None) -> list[str]:
    normalized_prefix = None
    root = _storage_root_resolved()
    if prefix is not None:
        normalized_prefix = _normalize_relative_storage_key(prefix)
        target_root = (root / normalized_prefix).resolve()
        if not target_root.exists():
            return []
        try:
            target_root.relative_to(root)
        except ValueError as exc:
            raise ValueError("Invalid storage key: resolved path escapes STORAGE_ROOT.") from exc
    else:
        target_root = root

    keys: list[str] = []
    if not target_root.exists():
        return keys

    for path in target_root.rglob("*"):
        if not path.is_file():
            continue
        relative_key = path.relative_to(root).as_posix()
        keys.append(relative_key)
    keys.sort()
    return keys


async def list_storage_keys(*, prefix: str | None = None) -> list[str]:
    return await asyncio.to_thread(
        _sync_list_storage_keys,
        prefix=prefix,
    )


async def delete_storage_file(*, relative_storage_key: str) -> None:
    """R-14: async-safe delete; silent if file is already absent."""
    await asyncio.to_thread(
        _sync_delete_storage_file,
        relative_storage_key=relative_storage_key,
    )
