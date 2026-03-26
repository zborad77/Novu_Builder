"""R-14: delete_photo must remove physical storage files."""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call


def _make_photo(storage_key="projects/p/orig.jpg",
                preview_key="projects/p/preview/orig.jpg",
                ai_key="projects/p/ai/orig.jpg"):
    ph = MagicMock()
    ph.id = "pho_1"
    ph.project_id = "prj_1"
    ph.storage_key = storage_key
    ph.preview_storage_key = preview_key
    ph.ai_input_storage_key = ai_key
    return ph


class TestDeletePhotoStorageCleanup:

    @pytest.mark.asyncio
    async def test_delete_removes_all_three_storage_keys(self):
        """delete_photo calls delete_storage_file for original, preview, and AI input."""
        from app.services.photo_service import PhotoService

        photo = _make_photo()
        repo = AsyncMock()
        repo.get_photo = AsyncMock(return_value=photo)
        repo.remove_photo = AsyncMock()

        service = PhotoService(repo)

        with patch("app.services.photo_service.delete_storage_file", new_callable=AsyncMock) as mock_del:
            result = await service.delete_photo("prj_1", "pho_1")

        assert result is True
        assert mock_del.await_count == 3
        called_keys = {c.kwargs["relative_storage_key"] for c in mock_del.await_args_list}
        assert called_keys == {
            "projects/p/orig.jpg",
            "projects/p/preview/orig.jpg",
            "projects/p/ai/orig.jpg",
        }
        repo.remove_photo.assert_called_once_with(photo)

    @pytest.mark.asyncio
    async def test_delete_skips_missing_storage_keys(self):
        """delete_photo skips None storage keys (e.g. photo without preview)."""
        from app.services.photo_service import PhotoService

        photo = _make_photo(preview_key=None, ai_key=None)
        repo = AsyncMock()
        repo.get_photo = AsyncMock(return_value=photo)
        repo.remove_photo = AsyncMock()

        service = PhotoService(repo)

        with patch("app.services.photo_service.delete_storage_file", new_callable=AsyncMock) as mock_del:
            result = await service.delete_photo("prj_1", "pho_1")

        assert result is True
        assert mock_del.await_count == 1  # only original
        repo.remove_photo.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_storage_file_safe_when_file_missing(self, tmp_path):
        """delete_storage_file does not raise when the target file is absent."""
        from app.storage.local_photo_storage import _sync_delete_storage_file, STORAGE_ROOT
        import app.storage.local_photo_storage as storage_mod

        original_root = storage_mod.STORAGE_ROOT
        storage_mod.STORAGE_ROOT = tmp_path
        try:
            # Call with a key that does not exist — must not raise
            _sync_delete_storage_file(relative_storage_key="projects/ghost/nonexistent.jpg")
        finally:
            storage_mod.STORAGE_ROOT = original_root

    @pytest.mark.asyncio
    async def test_delete_photo_returns_false_for_missing_photo(self):
        """delete_photo returns False when DB record is not found."""
        from app.services.photo_service import PhotoService

        repo = AsyncMock()
        repo.get_photo = AsyncMock(return_value=None)

        service = PhotoService(repo)

        with patch("app.services.photo_service.delete_storage_file", new_callable=AsyncMock) as mock_del:
            result = await service.delete_photo("prj_1", "nonexistent")

        assert result is False
        mock_del.assert_not_called()
