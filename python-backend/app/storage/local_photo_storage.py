import re
from pathlib import Path
import shutil
from time import time_ns
from uuid import uuid4


def _resolve_storage_root() -> Path:
    import os
    env_val = os.getenv("STORAGE_ROOT", "").strip()
    if env_val:
        return Path(env_val)
    return Path(__file__).resolve().parents[3] / "storage"


STORAGE_ROOT = _resolve_storage_root()


def ensure_directory(target_directory: Path) -> None:
    target_directory.mkdir(parents=True, exist_ok=True)


def sanitize_filename(filename: str | None) -> str:
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", (filename or "upload.bin").strip())
    safe_name = re.sub(r"-+", "-", safe_name).strip("-")
    return safe_name or "upload.bin"


def save_original_photo(*, project_id: str, original_filename: str | None, content: bytes) -> tuple[str, Path]:
    safe_filename = sanitize_filename(original_filename)
    relative_directory = Path("projects") / project_id
    target_directory = STORAGE_ROOT / relative_directory
    stored_filename = f"{time_ns()}-{uuid4().hex[:8]}-{safe_filename}"
    relative_storage_key = (relative_directory / stored_filename).as_posix()
    absolute_path = STORAGE_ROOT / relative_storage_key

    ensure_directory(target_directory)
    absolute_path.write_bytes(content)

    return relative_storage_key, absolute_path


def write_storage_file(*, relative_storage_key: str, content: bytes) -> Path:
    absolute_path = STORAGE_ROOT / relative_storage_key
    ensure_directory(absolute_path.parent)
    absolute_path.write_bytes(content)
    return absolute_path


def copy_storage_file(*, source_storage_key: str, target_storage_key: str) -> Path:
    source_path = STORAGE_ROOT / source_storage_key
    target_path = STORAGE_ROOT / target_storage_key
    ensure_directory(target_path.parent)
    shutil.copy2(source_path, target_path)
    return target_path
