"""R-14: photo delete must be soft-delete first, then async-cleaned."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_photo(
    *,
    status: str = "active",
    storage_key: str = "projects/p/orig.jpg",
    preview_key: str | None = "projects/p/preview/orig.jpg",
    ai_key: str | None = "projects/p/ai/orig.jpg",
):
    photo = MagicMock()
    photo.id = "pho_1"
    photo.project_id = "prj_1"
    photo.status = status
    photo.storage_key = storage_key
    photo.preview_storage_key = preview_key
    photo.ai_input_storage_key = ai_key
    photo.is_primary = True
    photo.is_analysis_reference = True
    return photo


class TestPhotoSoftDelete:
    @pytest.mark.asyncio
    async def test_delete_marks_photo_pending_delete_without_touching_storage(self):
        from app.services.photo_service import PhotoService

        photo = _make_photo()
        repo = AsyncMock()
        repo.get_photo = AsyncMock(return_value=photo)
        repo.update_status = AsyncMock(return_value=photo)

        service = PhotoService(repo)

        with patch("app.services.photo_service.delete_storage_file", new_callable=AsyncMock) as mock_delete:
            result = await service.delete_photo("prj_1", "pho_1")

        assert result is True
        assert photo.is_primary is False
        assert photo.is_analysis_reference is False
        repo.update_status.assert_awaited_once_with(photo, "pending_delete")
        mock_delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_returns_false_for_missing_photo(self):
        from app.services.photo_service import PhotoService

        repo = AsyncMock()
        repo.get_photo = AsyncMock(return_value=None)

        service = PhotoService(repo)

        with patch("app.services.photo_service.delete_storage_file", new_callable=AsyncMock) as mock_delete:
            result = await service.delete_photo("prj_1", "missing")

        assert result is False
        mock_delete.assert_not_awaited()


class TestPendingDeleteCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_pending_deletes_marks_deleted_after_storage_cleanup(self):
        from app.services.photo_service import PhotoService

        photo = _make_photo(status="pending_delete")
        repo = AsyncMock()
        repo.list_pending_delete = AsyncMock(return_value=[photo])
        repo.update_status = AsyncMock(return_value=photo)

        service = PhotoService(repo)

        with patch("app.services.photo_service.delete_storage_file", new_callable=AsyncMock) as mock_delete:
            deleted = await service.cleanup_pending_deletes()

        assert deleted == 1
        assert mock_delete.await_count == 3
        called_keys = {call.kwargs["relative_storage_key"] for call in mock_delete.await_args_list}
        assert called_keys == {
            "projects/p/orig.jpg",
            "projects/p/preview/orig.jpg",
            "projects/p/ai/orig.jpg",
        }
        repo.update_status.assert_awaited_once_with(photo, "deleted")

    @pytest.mark.asyncio
    async def test_cleanup_pending_deletes_leaves_photo_pending_when_interrupted(self):
        from app.services.photo_service import PhotoService

        photo = _make_photo(status="pending_delete")
        repo = AsyncMock()
        repo.list_pending_delete = AsyncMock(return_value=[photo])
        repo.update_status = AsyncMock(return_value=photo)

        service = PhotoService(repo)

        async def failing_delete(*, relative_storage_key: str) -> None:
            if relative_storage_key.endswith("preview/orig.jpg"):
                raise OSError("storage unavailable")

        with patch("app.services.photo_service.delete_storage_file", side_effect=failing_delete):
            deleted = await service.cleanup_pending_deletes()

        assert deleted == 0
        repo.update_status.assert_not_awaited()
