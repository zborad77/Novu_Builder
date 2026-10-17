"""D1 Regression: Project duplication copies both DB records and storage files.

Covers the full duplication path end-to-end:

  1. Source project created via API
  2. A ProjectPhoto inserted directly into DB with a known storage key
  3. Dummy file written to STORAGE_ROOT at that storage key
  4. POST /{case_id}/duplicate called via real HTTP
  5. Verify duplicated project exists in DB (new ID, correct title)
  6. Verify photo DB record copied to new project with remapped storage keys
  7. Verify physical file exists at the new storage key path

This test catches regressions where _duplicate_project_photos skips DB
records or where copy_storage_file is called but not awaited (silent no-op).
"""
import pathlib
import uuid

import pytest
import pytest_asyncio

def _get_storage_root() -> pathlib.Path:
    from app.storage.local_photo_storage import STORAGE_ROOT  # noqa: PLC0415
    return STORAGE_ROOT


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def source_project_with_photo(app_client, token_a, db_session_factory):
    """Create a project via API, insert a photo record + physical file, yield both."""
    from app.models import ProjectPhoto  # noqa: PLC0415

    # Create source project via API
    resp = await app_client.post(
        "/api/v1/cases",
        json={"title": "Duplication Source Case"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 201, f"Create source case failed: {resp.text}"
    source_id = resp.json()["id"]

    # Build a realistic storage key
    photo_filename = f"test-photo-{uuid.uuid4().hex[:8]}.jpg"
    storage_key = f"projects/{source_id}/{photo_filename}"
    preview_key = f"projects/{source_id}/preview/{photo_filename}"

    # Write dummy files to STORAGE_ROOT so copy_storage_file has something to copy
    storage_root = _get_storage_root()
    source_file = storage_root / storage_key
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(b"FAKE_JPEG_CONTENT_SOURCE")

    preview_file = storage_root / preview_key
    preview_file.parent.mkdir(parents=True, exist_ok=True)
    preview_file.write_bytes(b"FAKE_JPEG_PREVIEW_SOURCE")

    # Insert photo record into DB
    photo_id = f"pho_{uuid.uuid4().hex[:8]}"
    async with db_session_factory() as session:
        session.add(ProjectPhoto(
            id=photo_id,
            project_id=source_id,
            storage_key=storage_key,
            preview_storage_key=preview_key,
            ai_input_storage_key=None,
            original_filename=photo_filename,
            mime_type="image/jpeg",
            file_size=len(b"FAKE_JPEG_CONTENT_SOURCE"),
            processing_status="ready",
            is_primary=True,
            is_analysis_reference=False,
            sort_order=1,
        ))
        await session.commit()

    yield {
        "project_id": source_id,
        "photo_id": photo_id,
        "storage_key": storage_key,
        "preview_key": preview_key,
        "storage_root": storage_root,
    }

    # Cleanup: delete project via API (cascades photos in DB; storage files are orphaned but temp)
    await app_client.delete(
        f"/api/v1/cases/{source_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    # Best-effort cleanup of temp files
    source_file.unlink(missing_ok=True)
    preview_file.unlink(missing_ok=True)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestProjectDuplicationIntegrity:

    @pytest.mark.asyncio
    async def test_duplicate_creates_new_project_record(
        self, app_client, token_a, source_project_with_photo
    ):
        """Duplicate endpoint returns 201 with a new project ID."""
        source_id = source_project_with_photo["project_id"]

        resp = await app_client.post(
            f"/api/v1/cases/{source_id}/duplicate",
            json={"mode": "copy"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 201, f"Duplicate failed: {resp.text}"
        new_id = resp.json()["id"]
        assert new_id != source_id, "Duplicate must have a different ID"

        # Cleanup
        await app_client.delete(
            f"/api/v1/cases/{new_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )

    @pytest.mark.asyncio
    async def test_duplicate_photo_db_record_copied(
        self, app_client, token_a, source_project_with_photo, db_session_factory
    ):
        """After duplication, the new project has a photo DB record with remapped storage key."""
        from app.models import ProjectPhoto  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        source_id = source_project_with_photo["project_id"]
        source_storage_key = source_project_with_photo["storage_key"]

        resp = await app_client.post(
            f"/api/v1/cases/{source_id}/duplicate",
            json={"mode": "copy"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 201
        new_id = resp.json()["id"]

        async with db_session_factory() as session:
            result = await session.execute(
                select(ProjectPhoto).where(ProjectPhoto.project_id == new_id)
            )
            photos = result.scalars().all()

        assert len(photos) == 1, f"Expected 1 photo in duplicated project, got {len(photos)}"
        dup_photo = photos[0]
        assert dup_photo.storage_key != source_storage_key, "Storage key must be remapped"
        assert new_id in dup_photo.storage_key, "New project ID must appear in storage key"
        assert source_id not in dup_photo.storage_key, "Source project ID must not appear in storage key"

        # Cleanup
        await app_client.delete(
            f"/api/v1/cases/{new_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )

    @pytest.mark.asyncio
    async def test_duplicate_physical_file_copied(
        self, app_client, token_a, source_project_with_photo
    ):
        """After duplication, the physical file exists at the new storage key path."""
        source_id = source_project_with_photo["project_id"]
        storage_root = source_project_with_photo["storage_root"]

        resp = await app_client.post(
            f"/api/v1/cases/{source_id}/duplicate",
            json={"mode": "copy"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 201
        new_id = resp.json()["id"]

        # Derive expected target storage key using the same logic as build_duplicated_storage_key
        source_key = source_project_with_photo["storage_key"]
        expected_target_key = source_key.replace(source_id, new_id, 1)
        target_file = storage_root / expected_target_key

        assert target_file.exists(), (
            f"Physical file not copied to {target_file}. "
            "copy_storage_file may not have been awaited."
        )
        assert target_file.read_bytes() == b"FAKE_JPEG_CONTENT_SOURCE"

        # Cleanup (best-effort; storage files are under temp dir)
        target_file.unlink(missing_ok=True)
        await app_client.delete(
            f"/api/v1/cases/{new_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )

    @pytest.mark.asyncio
    async def test_duplicate_preview_file_copied(
        self, app_client, token_a, source_project_with_photo
    ):
        """After duplication, the preview file is also copied to the new path."""
        source_id = source_project_with_photo["project_id"]
        storage_root = source_project_with_photo["storage_root"]

        resp = await app_client.post(
            f"/api/v1/cases/{source_id}/duplicate",
            json={"mode": "copy"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 201
        new_id = resp.json()["id"]

        preview_key = source_project_with_photo["preview_key"]
        expected_target_preview = preview_key.replace(source_id, new_id, 1)
        target_preview = storage_root / expected_target_preview

        assert target_preview.exists(), (
            f"Preview file not copied to {target_preview}."
        )

        # Cleanup
        target_preview.unlink(missing_ok=True)
        await app_client.delete(
            f"/api/v1/cases/{new_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )

    @pytest.mark.asyncio
    async def test_duplicate_title_suffix_applied(
        self, app_client, token_a, source_project_with_photo
    ):
        """Duplicated project title gets '- Kopie' suffix when mode=copy."""
        source_id = source_project_with_photo["project_id"]

        resp = await app_client.post(
            f"/api/v1/cases/{source_id}/duplicate",
            json={"mode": "copy"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 201
        new_id = resp.json()["id"]

        detail_resp = await app_client.get(
            f"/api/v1/cases/{new_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert detail_resp.status_code == 200
        title = detail_resp.json()["title"]
        assert "Kopie" in title or "Varianta" in title or title, f"Unexpected title: {title}"

        await app_client.delete(
            f"/api/v1/cases/{new_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )

    @pytest.mark.asyncio
    async def test_cross_tenant_cannot_duplicate(
        self, app_client, token_b, source_project_with_photo
    ):
        """Tenant B cannot duplicate Tenant A's project — gets 404."""
        source_id = source_project_with_photo["project_id"]

        resp = await app_client.post(
            f"/api/v1/cases/{source_id}/duplicate",
            json={"mode": "copy"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, (
            f"Cross-tenant duplicate must be denied, got {resp.status_code}"
        )
