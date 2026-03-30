"""Storage backend dispatcher (C1).

Selects the active storage backend based on the STORAGE_BACKEND environment
variable (default: "local"). Import storage functions from this module instead
of importing from local_photo_storage or s3_photo_storage directly.

Supported backends:
    local — files written to STORAGE_ROOT on disk (default, dev-friendly)
    s3    — files written to an S3-compatible object store (production)

Path-based constants (STORAGE_ROOT, UPLOADS_ROOT, EXPORTS_ROOT) and local-only
utilities (ensure_directory) are NOT re-exported here because they have no
meaning for object-store backends. Code that depends on local file paths should
continue to import from local_photo_storage directly.
"""
import os as _os

_backend = _os.getenv("STORAGE_BACKEND", "local").lower()

if _backend == "s3":
    from app.storage.s3_photo_storage import (  # noqa: F401
        copy_storage_file,
        delete_storage_file,
        generate_presigned_url,
        get_public_url,
        list_storage_keys,
        read_storage_file,
        save_original_photo,
        storage_key_exists,
        write_storage_file,
    )
elif _backend == "local":
    from app.storage.local_photo_storage import (  # type: ignore[assignment]  # noqa: F401
        copy_storage_file,
        delete_storage_file,
        generate_presigned_url,
        get_public_url,
        list_storage_keys,
        read_storage_file,
        save_original_photo,
        storage_key_exists,
        write_storage_file,
    )
else:
    raise RuntimeError(
        f"Unsupported STORAGE_BACKEND={_backend!r}. "
        "Use 'local' or 's3' instead of relying on an implicit fallback."
    )

# Backend-independent helpers — always sourced from local_photo_storage
# (pure computation, no I/O)
from app.storage.local_photo_storage import (  # noqa: F401
    UploadValidationError,
    ensure_directory,
    get_image_dimensions,
    resize_image_bytes,
    sanitize_filename,
    validate_photo_upload,
    validate_image_format,
)
