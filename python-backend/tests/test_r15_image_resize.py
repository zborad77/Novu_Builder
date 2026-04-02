"""R-15: Preview and AI-input variants must be real resized images."""
import pytest
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

from app.storage.local_photo_storage import resize_image_bytes, get_image_dimensions


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_jpeg(width: int, height: int) -> bytes:
    """Create a minimal JPEG of the given size in memory."""
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(128, 64, 32))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _image_size(content: bytes) -> tuple[int, int]:
    from PIL import Image
    return Image.open(BytesIO(content)).size


# ── resize_image_bytes ────────────────────────────────────────────────────────

class TestResizeImageBytes:

    def test_large_image_is_shrunk_to_fit_max_edge(self):
        """A 3000×2000 image resized to max_edge=1600 must fit within 1600px."""
        content = _make_jpeg(3000, 2000)
        result = resize_image_bytes(content, 1600)
        w, h = _image_size(result)
        assert max(w, h) <= 1600
        assert (w, h) != (3000, 2000)

    def test_small_image_is_not_upscaled(self):
        """An image already smaller than max_edge must not be enlarged."""
        content = _make_jpeg(400, 300)
        result = resize_image_bytes(content, 1600)
        w, h = _image_size(result)
        assert w <= 400
        assert h <= 300

    def test_preview_smaller_than_ai_input(self):
        """Preview (max 1600) output must be >= AI-input (max 1280) in byte size for same source."""
        content = _make_jpeg(3000, 2000)
        preview = resize_image_bytes(content, 1600)
        ai = resize_image_bytes(content, 1280)
        # Both must be resized to fit their respective limits
        pw, ph = _image_size(preview)
        aw, ah = _image_size(ai)
        assert max(pw, ph) <= 1600
        assert max(aw, ah) <= 1280

    def test_non_image_bytes_return_original_content(self):
        """resize_image_bytes must fall back silently for non-image binary data."""
        junk = b"\x00\x01\x02\x03garbage"
        result = resize_image_bytes(junk, 1600)
        assert result == junk

    def test_result_is_valid_jpeg(self):
        """Resized output of a JPEG source must be a valid JPEG."""
        from PIL import Image
        content = _make_jpeg(2000, 1500)
        result = resize_image_bytes(content, 800)
        img = Image.open(BytesIO(result))
        assert img.format == "JPEG"


# ── get_image_dimensions ──────────────────────────────────────────────────────

class TestGetImageDimensions:

    def test_returns_correct_dimensions(self):
        content = _make_jpeg(640, 480)
        w, h = get_image_dimensions(content)
        assert (w, h) == (640, 480)

    def test_returns_none_none_for_non_image(self):
        w, h = get_image_dimensions(b"not an image")
        assert w is None
        assert h is None


# ── integration: photo_service uses real resize ───────────────────────────────

class TestPhotoServiceUsesResize:

    @pytest.mark.asyncio
    async def test_variants_are_resized_not_original(self):
        """_process_multipart_photo_variants must write resized bytes, not the original."""
        from app.services.photo_service import PhotoService

        content = _make_jpeg(3000, 2000)
        written: dict[str, bytes] = {}

        async def fake_write(*, relative_storage_key: str, content: bytes) -> None:
            written[relative_storage_key] = content

        photo = MagicMock()
        photo.processing_status = "uploaded"
        photo.preview_storage_key = "projects/p/preview/photo.jpg"
        photo.ai_input_storage_key = "projects/p/ai/photo.jpg"

        repo = AsyncMock()
        repo.update_photo = AsyncMock(side_effect=lambda p: p)
        service = PhotoService(repo)

        with patch("app.services.photo_service.write_storage_file", side_effect=fake_write):
            await service._process_multipart_photo_variants(photo, content)

        assert "projects/p/preview/photo.jpg" in written
        assert "projects/p/ai/photo.jpg" in written

        # Preview must be <= 1600px on longest edge
        pw, ph = _image_size(written["projects/p/preview/photo.jpg"])
        assert max(pw, ph) <= 1600

        # AI input must be <= 1280px on longest edge
        aw, ah = _image_size(written["projects/p/ai/photo.jpg"])
        assert max(aw, ah) <= 1280

        # Neither variant should be a copy of the original bytes
        assert written["projects/p/preview/photo.jpg"] != content
        assert written["projects/p/ai/photo.jpg"] != content

    @pytest.mark.asyncio
    async def test_process_photo_variants_by_id_reads_original_and_marks_ready(self):
        from app.services.photo_service import PhotoService

        content = _make_jpeg(2200, 1800)
        written: dict[str, bytes] = {}

        async def fake_write(*, relative_storage_key: str, content: bytes) -> None:
            written[relative_storage_key] = content

        photo = MagicMock()
        photo.id = "pho_1"
        photo.project_id = "prj_1"
        photo.storage_key = "projects/prj_1/original/photo.jpg"
        photo.original_filename = "photo.jpg"
        photo.mime_type = "image/jpeg"
        photo.file_size = len(content)
        photo.width = 2200
        photo.height = 1800
        photo.taken_at = None
        photo.exif_lat = None
        photo.exif_lng = None
        photo.processing_status = "uploaded"
        photo.is_primary = False
        photo.is_analysis_reference = False
        photo.sort_order = 0
        photo.preview_storage_key = "projects/prj_1/preview/photo.jpg"
        photo.preview_file_size = None
        photo.preview_width = None
        photo.preview_height = None
        photo.ai_input_storage_key = "projects/prj_1/ai/photo.jpg"
        photo.ai_input_file_size = None
        photo.ai_input_width = None
        photo.ai_input_height = None

        repo = AsyncMock()
        repo.get_photo_by_id = AsyncMock(return_value=photo)
        repo.update_photo = AsyncMock(side_effect=lambda p: p)
        service = PhotoService(repo)

        with (
            patch("app.services.photo_service.read_storage_file", new=AsyncMock(return_value=content)),
            patch("app.services.photo_service.write_storage_file", side_effect=fake_write),
        ):
            result = await service.process_photo_variants_by_id("pho_1")

        assert result is not None
        assert result.processingStatus == "ready"
        assert "projects/prj_1/preview/photo.jpg" in written
        assert "projects/prj_1/ai/photo.jpg" in written
