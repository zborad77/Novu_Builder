"""R-16: Storage functions must be async (asyncio.to_thread wrappers)."""
import inspect
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import app.storage.local_photo_storage as storage_mod


class TestStorageFunctionsAreAsync:

    def test_save_original_photo_is_coroutine(self):
        assert inspect.iscoroutinefunction(storage_mod.save_original_photo)

    def test_write_storage_file_is_coroutine(self):
        assert inspect.iscoroutinefunction(storage_mod.write_storage_file)

    def test_copy_storage_file_is_coroutine(self):
        assert inspect.iscoroutinefunction(storage_mod.copy_storage_file)

    def test_delete_storage_file_is_coroutine(self):
        assert inspect.iscoroutinefunction(storage_mod.delete_storage_file)


class TestStorageFunctionalBehaviour:

    @pytest.mark.asyncio
    async def test_write_and_read_roundtrip(self, tmp_path):
        """write_storage_file writes bytes; the file is readable afterwards."""
        orig_root = storage_mod.STORAGE_ROOT
        storage_mod.STORAGE_ROOT = tmp_path
        try:
            key = "projects/test_proj/photo.bin"
            content = b"hello storage"
            await storage_mod.write_storage_file(relative_storage_key=key, content=content)
            assert (tmp_path / key).read_bytes() == content
        finally:
            storage_mod.STORAGE_ROOT = orig_root

    @pytest.mark.asyncio
    async def test_delete_storage_file_removes_file(self, tmp_path):
        """delete_storage_file removes an existing file."""
        orig_root = storage_mod.STORAGE_ROOT
        storage_mod.STORAGE_ROOT = tmp_path
        try:
            key = "projects/test_proj/to_delete.bin"
            target = tmp_path / key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"data")

            await storage_mod.delete_storage_file(relative_storage_key=key)

            assert not target.exists()
        finally:
            storage_mod.STORAGE_ROOT = orig_root

    @pytest.mark.asyncio
    async def test_delete_storage_file_silent_on_missing(self, tmp_path):
        """delete_storage_file does not raise when file is already absent."""
        orig_root = storage_mod.STORAGE_ROOT
        storage_mod.STORAGE_ROOT = tmp_path
        try:
            # Must complete without exception
            await storage_mod.delete_storage_file(
                relative_storage_key="projects/ghost/never_existed.jpg"
            )
        finally:
            storage_mod.STORAGE_ROOT = orig_root

    @pytest.mark.asyncio
    async def test_copy_storage_file_duplicates_content(self, tmp_path):
        """copy_storage_file produces an exact copy at the target key."""
        orig_root = storage_mod.STORAGE_ROOT
        storage_mod.STORAGE_ROOT = tmp_path
        try:
            src_key = "projects/p/original.bin"
            dst_key = "projects/p/copy.bin"
            src = tmp_path / src_key
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_bytes(b"original content")

            await storage_mod.copy_storage_file(
                source_storage_key=src_key,
                target_storage_key=dst_key,
            )

            assert (tmp_path / dst_key).read_bytes() == b"original content"
        finally:
            storage_mod.STORAGE_ROOT = orig_root
