"""F0.3 regression suite: photo ownership and permanent deletion.

Ownership: the server records ``uploaded_by_user_id`` from the authenticated
uploader; technicians soft-delete/restore only their own photos, managers and
company admins any photo of their tenant; unknown authors (NULL) belong to nobody.

Permanent deletion: company admins (own tenant) through the case API,
superadmins only through /admin; confirmation required; audited fail-closed;
original and derived files removed; case exports invalidated; storage outages
leave the photo hidden in purge_pending and the worker retries.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import select

from app.modules.audit.models import AuditLog
from app.modules.exports.models import ProjectExport
from app.modules.media.models import ProjectPhoto
from app.modules.identity.models import User
from app.modules.identity.auth_service import hash_password

ORG_A = "org_e2e_a"
ORG_B = "org_e2e_b"
PASSWORD = "F03-Initial-Pass-1!"

_USERS = {
    "f03_technician_a": (ORG_A, "technician", False),
    "f03_technician_a2": (ORG_A, "technician", False),
    "f03_manager_a": (ORG_A, "manager", False),
    "f03_admin_a": (ORG_A, "admin", False),
    "f03_admin_b": (ORG_B, "admin", False),
    "f03_superadmin": (ORG_A, "superadmin", True),
}


def _email(user_id: str) -> str:
    return f"{user_id}@f03.test"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def f03_users(test_tenants, db_session_factory):
    async with db_session_factory() as session:
        for user_id, (org, role, flag) in _USERS.items():
            if await session.get(User, user_id) is None:
                session.add(
                    User(
                        id=user_id,
                        organization_id=org,
                        email=_email(user_id),
                        password_hash=hash_password(PASSWORD),
                        full_name=user_id,
                        role=role,
                        is_active=True,
                        is_superadmin=flag,
                    )
                )
        await session.commit()
    return test_tenants


async def _token(client, user_id: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": _email(user_id), "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["accessToken"]


async def _new_case(client, token: str) -> str:
    response = await client.post("/api/v1/cases", json={"title": f"F03 {uuid.uuid4().hex[:6]}"}, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _new_photo(db_session_factory, case_id: str, *, uploaded_by: str | None, status: str = "active") -> str:
    photo_id = f"pho_f03_{uuid.uuid4().hex[:8]}"
    async with db_session_factory() as session:
        session.add(
            ProjectPhoto(
                id=photo_id,
                project_id=case_id,
                status=status,
                storage_key=f"projects/{case_id}/{photo_id}.jpg",
                preview_storage_key=f"projects/{case_id}/preview/{photo_id}.jpg",
                ai_input_storage_key=f"projects/{case_id}/ai/{photo_id}.jpg",
                original_filename=f"{photo_id}.jpg",
                mime_type="image/jpeg",
                file_size=1,
                uploaded_by_user_id=uploaded_by,
                deleted_at=datetime.now(UTC) if status == "pending_delete" else None,
            )
        )
        await session.commit()
    return photo_id


async def _photo(db_session_factory, photo_id: str) -> ProjectPhoto:
    async with db_session_factory() as session:
        photo = await session.get(ProjectPhoto, photo_id)
        assert photo is not None
        return photo


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


# ── Author is set by the server only ──────────────────────────────────────────


async def test_upload_records_the_author_passed_by_the_route():
    from unittest.mock import MagicMock

    from fastapi import UploadFile

    from app.modules.media.photo_service import PhotoService

    repo = AsyncMock()
    repo.count_photos = AsyncMock(return_value=0)
    repo.get_next_sort_order = AsyncMock(return_value=1)
    repo.add_photo = AsyncMock(side_effect=lambda photo: photo)
    repo.update_photo = AsyncMock(side_effect=lambda photo: photo)
    upload = MagicMock(spec=UploadFile)
    upload.filename, upload.content_type, upload.size = "roof.png", "image/png", None
    upload.read = AsyncMock(return_value=_png())
    project = MagicMock(id="prj_f03", organization_id=ORG_A)

    with (
        patch("app.modules.media.photo_service.save_original_photo", return_value=("projects/prj_f03/roof.png", None)),
        patch("app.modules.media.photo_service.enqueue_heavy_job", new=AsyncMock()),
    ):
        await PhotoService(repo, work_queue=MagicMock()).create_multipart_photo(
            project, upload, is_primary=False, uploaded_by_user_id="f03_technician_a"
        )
    assert repo.add_photo.await_args.args[0].uploaded_by_user_id == "f03_technician_a"


def test_upload_route_takes_the_author_from_the_verified_identity_only():
    import inspect

    from app.modules.media.api.images import upload_case_images

    source = inspect.getsource(upload_case_images)
    assert "uploaded_by_user_id=current_user.id" in source
    # No form field can name the author: the handler reads only files/isPrimary.
    assert "uploaded_by" not in source.replace("uploaded_by_user_id=current_user.id", "")


# ── Soft delete / restore ownership ───────────────────────────────────────────


async def test_technician_manages_only_own_photos(app_client, f03_users, db_session_factory):
    technician = await _token(app_client, "f03_technician_a")
    case_id = await _new_case(app_client, technician)
    own = await _new_photo(db_session_factory, case_id, uploaded_by="f03_technician_a")
    colleague = await _new_photo(db_session_factory, case_id, uploaded_by="f03_technician_a2")
    legacy = await _new_photo(db_session_factory, case_id, uploaded_by=None)

    for photo_id in (colleague, legacy):
        response = await app_client.delete(f"/api/v1/cases/{case_id}/images/{photo_id}", headers=_auth(technician))
        assert response.status_code == 403, photo_id
        assert (await _photo(db_session_factory, photo_id)).status == "active"

    deleted = await app_client.delete(f"/api/v1/cases/{case_id}/images/{own}", headers=_auth(technician))
    assert deleted.status_code == 200, deleted.text
    assert (await _photo(db_session_factory, own)).deleted_by_user_id == "f03_technician_a"

    # Another technician's trash does not show it and cannot restore it.
    other = await _token(app_client, "f03_technician_a2")
    trash_other = await app_client.get(f"/api/v1/cases/{case_id}/images/deleted", headers=_auth(other))
    assert trash_other.status_code == 200 and own not in trash_other.text
    stolen = await app_client.post(f"/api/v1/cases/{case_id}/images/{own}/restore", headers=_auth(other))
    assert stolen.status_code == 403

    trash = await app_client.get(f"/api/v1/cases/{case_id}/images/deleted", headers=_auth(technician))
    assert [item["id"] for item in trash.json()["items"]] == [own]
    restored = await app_client.post(f"/api/v1/cases/{case_id}/images/{own}/restore", headers=_auth(technician))
    assert restored.status_code == 200
    assert (await _photo(db_session_factory, own)).status == "active"


@pytest.mark.parametrize("actor", ["f03_manager_a", "f03_admin_a"])
async def test_manager_and_admin_manage_any_photo_of_their_tenant(app_client, f03_users, db_session_factory, actor):
    token = await _token(app_client, actor)
    case_id = await _new_case(app_client, token)
    for author in ("f03_technician_a", None):
        photo_id = await _new_photo(db_session_factory, case_id, uploaded_by=author)
        assert (await app_client.delete(f"/api/v1/cases/{case_id}/images/{photo_id}", headers=_auth(token))).status_code == 200
        assert (
            await app_client.post(f"/api/v1/cases/{case_id}/images/{photo_id}/restore", headers=_auth(token))
        ).status_code == 200


async def test_photo_operations_never_cross_tenants(app_client, f03_users, db_session_factory):
    owner = await _token(app_client, "f03_admin_a")
    stranger = await _token(app_client, "f03_admin_b")
    case_id = await _new_case(app_client, owner)
    photo_id = await _new_photo(db_session_factory, case_id, uploaded_by="f03_technician_a")
    for response in (
        await app_client.delete(f"/api/v1/cases/{case_id}/images/{photo_id}", headers=_auth(stranger)),
        await app_client.post(f"/api/v1/cases/{case_id}/images/{photo_id}/restore", headers=_auth(stranger)),
        await app_client.post(
            f"/api/v1/cases/{case_id}/images/{photo_id}/purge",
            json={"confirmImageId": photo_id},
            headers=_auth(stranger),
        ),
    ):
        assert response.status_code == 404, response.text
    assert (await _photo(db_session_factory, photo_id)).status == "active"


async def test_deactivated_or_removed_author(app_client, f03_users, db_session_factory):
    manager = await _token(app_client, "f03_manager_a")
    case_id = await _new_case(app_client, manager)
    author_id = f"f03_tmp_{uuid.uuid4().hex[:8]}"
    async with db_session_factory() as session:
        session.add(
            User(
                id=author_id,
                organization_id=ORG_A,
                email=_email(author_id),
                password_hash=hash_password(PASSWORD),
                full_name="Temporary technician",
                role="technician",
                is_active=True,
                is_superadmin=False,
            )
        )
        await session.commit()
    author_token = await _token(app_client, author_id)
    photo_id = await _new_photo(db_session_factory, case_id, uploaded_by=author_id)

    # Deactivated: the author's token stops working; the photo stays manageable.
    async with db_session_factory() as session:
        user = await session.get(User, author_id)
        user.is_active = False
        await session.commit()
    denied = await app_client.delete(f"/api/v1/cases/{case_id}/images/{photo_id}", headers=_auth(author_token))
    assert denied.status_code == 401
    assert (await _photo(db_session_factory, photo_id)).uploaded_by_user_id == author_id

    # Removed: ownership falls back to NULL (managers/admins only), photo is kept.
    async with db_session_factory() as session:
        await session.delete(await session.get(User, author_id))
        await session.commit()
    photo = await _photo(db_session_factory, photo_id)
    assert (photo.status, photo.uploaded_by_user_id) == ("active", None)
    assert (await app_client.delete(f"/api/v1/cases/{case_id}/images/{photo_id}", headers=_auth(manager))).status_code == 200


# ── Permanent deletion: who may ───────────────────────────────────────────────


@pytest.mark.parametrize("actor", ["f03_technician_a", "f03_manager_a", "f03_superadmin"])
async def test_only_company_admin_may_purge_through_case_api(app_client, f03_users, db_session_factory, actor):
    admin = await _token(app_client, "f03_admin_a")
    case_id = await _new_case(app_client, admin)
    photo_id = await _new_photo(db_session_factory, case_id, uploaded_by=actor if actor != "f03_superadmin" else None)
    token = await _token(app_client, actor)
    response = await app_client.post(
        f"/api/v1/cases/{case_id}/images/{photo_id}/purge",
        json={"confirmImageId": photo_id},
        headers=_auth(token),
    )
    assert response.status_code == 403, response.text
    assert (await _photo(db_session_factory, photo_id)).status == "active"


@pytest.mark.parametrize("body", [{}, {"confirmImageId": "pho_other"}, {"confirmImageId": None}])
async def test_purge_requires_explicit_confirmation(app_client, f03_users, db_session_factory, body):
    admin = await _token(app_client, "f03_admin_a")
    case_id = await _new_case(app_client, admin)
    photo_id = await _new_photo(db_session_factory, case_id, uploaded_by=None)
    response = await app_client.post(f"/api/v1/cases/{case_id}/images/{photo_id}/purge", json=body, headers=_auth(admin))
    assert response.status_code in (400, 422)
    assert (await _photo(db_session_factory, photo_id)).status == "active"


async def test_non_superadmins_cannot_use_system_purge(app_client, f03_users, db_session_factory):
    admin = await _token(app_client, "f03_admin_a")
    case_id = await _new_case(app_client, admin)
    photo_id = await _new_photo(db_session_factory, case_id, uploaded_by=None)
    for actor in ("f03_admin_a", "f03_manager_a", "f03_technician_a"):
        response = await app_client.post(
            f"/api/v1/admin/photos/{photo_id}/purge",
            json={"confirmImageId": photo_id},
            headers=_auth(await _token(app_client, actor)),
        )
        assert response.status_code == 403, actor
    assert (await _photo(db_session_factory, photo_id)).status == "active"


# ── Permanent deletion: effects ───────────────────────────────────────────────


@pytest.mark.parametrize("initial_status", ["active", "pending_delete"])
async def test_company_admin_purge_removes_files_exports_and_access(
    app_client, f03_users, db_session_factory, initial_status
):
    admin = await _token(app_client, "f03_admin_a")
    case_id = await _new_case(app_client, admin)
    photo_id = await _new_photo(db_session_factory, case_id, uploaded_by="f03_technician_a", status=initial_status)
    export_id = f"exp_f03_{uuid.uuid4().hex[:8]}"
    async with db_session_factory() as session:
        session.add(
            ProjectExport(
                id=export_id,
                project_id=case_id,
                export_type="case_zip",
                status="completed",
                file_name="case.zip",
                storage_key=f"exports/{case_id}/case.zip",
                completed_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
        )
        await session.commit()

    with patch("app.modules.media.photo_service.delete_storage_file", new_callable=AsyncMock) as storage_delete:
        response = await app_client.post(
            f"/api/v1/cases/{case_id}/images/{photo_id}/purge",
            json={"confirmImageId": photo_id},
            headers=_auth(admin),
        )
    assert response.status_code == 200, response.text
    assert response.json() == {"imageId": photo_id, "status": "purged"}
    assert {call.kwargs["relative_storage_key"] for call in storage_delete.await_args_list} == {
        f"projects/{case_id}/{photo_id}.jpg",
        f"projects/{case_id}/preview/{photo_id}.jpg",
        f"projects/{case_id}/ai/{photo_id}.jpg",
    }
    assert (await _photo(db_session_factory, photo_id)).status == "deleted"

    # Not reachable through the API, the trash, a restore, the preview link or exports.
    assert photo_id not in (await app_client.get(f"/api/v1/cases/{case_id}/images", headers=_auth(admin))).text
    assert photo_id not in (await app_client.get(f"/api/v1/cases/{case_id}/images/deleted", headers=_auth(admin))).text
    assert (await app_client.post(f"/api/v1/cases/{case_id}/images/{photo_id}/restore", headers=_auth(admin))).status_code == 404
    assert (await app_client.get(f"/api/v1/images/{photo_id}/preview", headers=_auth(admin))).status_code == 404
    assert (await app_client.get(f"/api/v1/exports/{export_id}", headers=_auth(admin))).status_code == 404

    async with db_session_factory() as session:
        rows = (
            await session.execute(
                select(AuditLog).where(AuditLog.resource_id == photo_id, AuditLog.action == "image.purge")
            )
        ).scalars().all()
    assert len(rows) == 1 and rows[0].user_id == "f03_admin_a"
    assert rows[0].detail["previous_status"] == initial_status and rows[0].detail["exports_expired"] == 1

    # Repeating is safe and does not audit again.
    again = await app_client.post(
        f"/api/v1/cases/{case_id}/images/{photo_id}/purge",
        json={"confirmImageId": photo_id},
        headers=_auth(admin),
    )
    assert again.status_code == 200 and again.json()["status"] == "purged"


async def test_superadmin_purges_through_system_administration(app_client, f03_users, db_session_factory):
    admin = await _token(app_client, "f03_admin_a")
    superadmin = await _token(app_client, "f03_superadmin")
    case_id = await _new_case(app_client, admin)
    photo_id = await _new_photo(db_session_factory, case_id, uploaded_by=None)
    with patch("app.modules.media.photo_service.delete_storage_file", new_callable=AsyncMock):
        response = await app_client.post(
            f"/api/v1/admin/photos/{photo_id}/purge",
            json={"confirmImageId": photo_id},
            headers=_auth(superadmin),
        )
    assert response.status_code == 200, response.text
    assert (await _photo(db_session_factory, photo_id)).status == "deleted"
    async with db_session_factory() as session:
        audit = await session.scalar(
            select(AuditLog).where(AuditLog.resource_id == photo_id, AuditLog.action == "admin.image.purge")
        )
    assert audit is not None and audit.detail["target_org"] == ORG_A


async def test_storage_outage_leaves_photo_hidden_and_worker_finishes(app_client, f03_users, db_session_factory):
    from app.modules.media.photo_repository import PhotoRepository
    from app.modules.media.photo_service import PhotoService

    admin = await _token(app_client, "f03_admin_a")
    case_id = await _new_case(app_client, admin)
    photo_id = await _new_photo(db_session_factory, case_id, uploaded_by=None)

    async def flaky(*, relative_storage_key: str) -> None:
        if "/preview/" in relative_storage_key:
            raise OSError("MinIO unavailable")

    with patch("app.modules.media.photo_service.delete_storage_file", side_effect=flaky):
        response = await app_client.post(
            f"/api/v1/cases/{case_id}/images/{photo_id}/purge",
            json={"confirmImageId": photo_id},
            headers=_auth(admin),
        )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "purge_pending"
    assert (await _photo(db_session_factory, photo_id)).status == "purge_pending"
    # Hidden and not restorable while pending.
    assert photo_id not in (await app_client.get(f"/api/v1/cases/{case_id}/images", headers=_auth(admin))).text
    assert (await app_client.post(f"/api/v1/cases/{case_id}/images/{photo_id}/restore", headers=_auth(admin))).status_code == 404

    # Worker retry (no retention wait for purge_pending) removes every object.
    with patch("app.modules.media.photo_service.delete_storage_file", new_callable=AsyncMock) as storage_delete:
        async with db_session_factory() as session:
            await PhotoService(PhotoRepository(session)).cleanup_pending_deletes(limit=1000)
    assert f"projects/{case_id}/preview/{photo_id}.jpg" in {
        call.kwargs["relative_storage_key"] for call in storage_delete.await_args_list
    }
    assert (await _photo(db_session_factory, photo_id)).status == "deleted"


async def test_retrying_a_pending_purge_through_the_api_completes_it(app_client, f03_users, db_session_factory):
    admin = await _token(app_client, "f03_admin_a")
    case_id = await _new_case(app_client, admin)
    photo_id = await _new_photo(db_session_factory, case_id, uploaded_by=None)
    body = {"confirmImageId": photo_id}
    with patch("app.modules.media.photo_service.delete_storage_file", side_effect=OSError("down")):
        first = await app_client.post(f"/api/v1/cases/{case_id}/images/{photo_id}/purge", json=body, headers=_auth(admin))
    with patch("app.modules.media.photo_service.delete_storage_file", new_callable=AsyncMock):
        second = await app_client.post(f"/api/v1/cases/{case_id}/images/{photo_id}/purge", json=body, headers=_auth(admin))
    assert (first.status_code, second.status_code) == (202, 200)
    assert (await _photo(db_session_factory, photo_id)).status == "deleted"
    async with db_session_factory() as session:
        audits = (
            await session.execute(select(AuditLog).where(AuditLog.resource_id == photo_id, AuditLog.action == "image.purge"))
        ).scalars().all()
    assert len(audits) == 1


async def test_audit_outage_blocks_the_purge(app_client, f03_users, db_session_factory):
    from app.modules.audit.audit_log import SecurityAuditWriteError

    admin = await _token(app_client, "f03_admin_a")
    case_id = await _new_case(app_client, admin)
    photo_id = await _new_photo(db_session_factory, case_id, uploaded_by=None)
    with (
        patch("app.modules.media.photo_purge.commit_security_critical_audit", side_effect=SecurityAuditWriteError("down")),
        patch("app.modules.media.photo_service.delete_storage_file", new_callable=AsyncMock) as storage_delete,
    ):
        response = await app_client.post(
            f"/api/v1/cases/{case_id}/images/{photo_id}/purge",
            json={"confirmImageId": photo_id},
            headers=_auth(admin),
        )
    assert response.status_code == 503
    storage_delete.assert_not_awaited()
    assert (await _photo(db_session_factory, photo_id)).status == "active"


async def test_reapply_script_purges_restored_photos_idempotently(app_client, f03_users, db_session_factory):
    from scripts.reapply_photo_purges import _reapply

    admin = await _token(app_client, "f03_admin_a")
    case_id = await _new_case(app_client, admin)
    restored = await _new_photo(db_session_factory, case_id, uploaded_by=None)
    with patch("app.modules.media.photo_service.delete_storage_file", new_callable=AsyncMock) as storage_delete:
        assert await _reapply([restored, "pho_absent_from_db"]) == 0
        assert await _reapply([restored]) == 0  # second run: already deleted, skipped
    assert storage_delete.await_count == 3
    assert (await _photo(db_session_factory, restored)).status == "deleted"
    async with db_session_factory() as session:
        audits = (
            await session.execute(
                select(AuditLog).where(AuditLog.resource_id == restored, AuditLog.action == "system.image.purge")
            )
        ).scalars().all()
    assert len(audits) == 1


# ── F0.3 finalization ─────────────────────────────────────────────────────────


async def test_photo_list_reports_author_and_per_user_delete_permission(app_client, f03_users, db_session_factory):
    technician = await _token(app_client, "f03_technician_a")
    manager = await _token(app_client, "f03_manager_a")
    case_id = await _new_case(app_client, manager)
    own = await _new_photo(db_session_factory, case_id, uploaded_by="f03_technician_a")
    other = await _new_photo(db_session_factory, case_id, uploaded_by="f03_manager_a")
    legacy = await _new_photo(db_session_factory, case_id, uploaded_by=None)

    def by_id(response):
        assert response.status_code == 200, response.text
        return {item["id"]: (item["uploadedByUserId"], item["canDelete"]) for item in response.json()["items"]}

    as_technician = by_id(await app_client.get(f"/api/v1/cases/{case_id}/images", headers=_auth(technician)))
    assert as_technician == {
        own: ("f03_technician_a", True),
        other: ("f03_manager_a", False),
        legacy: (None, False),
    }
    as_manager = by_id(await app_client.get(f"/api/v1/cases/{case_id}/images", headers=_auth(manager)))
    assert {photo_id: can for photo_id, (_, can) in as_manager.items()} == {own: True, other: True, legacy: True}


async def test_purge_removes_markers_and_keeps_historical_analysis(app_client, f03_users, db_session_factory):
    from app.models import AnalysisResult
    from app.modules.media.models import Marker

    admin = await _token(app_client, "f03_admin_a")
    case_id = await _new_case(app_client, admin)
    photo_id = await _new_photo(db_session_factory, case_id, uploaded_by=None)
    keep_id = await _new_photo(db_session_factory, case_id, uploaded_by=None)
    for image_id in (photo_id, keep_id):
        created = await app_client.post(
            "/api/v1/markers",
            json={"caseId": case_id, "imageId": image_id, "markerType": "defect", "x": 0.5, "y": 0.5, "label": "crack"},
            headers=_auth(admin),
        )
        assert created.status_code == 201, created.text
    result_id = f"res_f03_{uuid.uuid4().hex[:8]}"
    async with db_session_factory() as session:
        session.add(AnalysisResult(id=result_id, project_id=case_id, reference_photo_id=photo_id, estimated_area_sqm=12.5))
        await session.commit()

    with patch("app.modules.media.photo_service.delete_storage_file", new_callable=AsyncMock):
        purged = await app_client.post(
            f"/api/v1/cases/{case_id}/images/{photo_id}/purge",
            json={"confirmImageId": photo_id},
            headers=_auth(admin),
        )
    assert purged.status_code == 200, purged.text

    async with db_session_factory() as session:
        markers = (await session.execute(select(Marker).where(Marker.case_id == case_id))).scalars().all()
        result = await session.get(AnalysisResult, result_id)
        audit = await session.scalar(
            select(AuditLog).where(AuditLog.resource_id == photo_id, AuditLog.action == "image.purge")
        )
    assert {marker.image_id for marker in markers} == {keep_id}  # annotations of erased content are gone
    assert (result.reference_photo_id, result.estimated_area_sqm) == (photo_id, 12.5)  # history unchanged
    assert audit.detail["markers_deleted"] == 1
    assert (await app_client.get(f"/api/v1/markers?image_id={photo_id}", headers=_auth(admin))).status_code == 404


@pytest.mark.parametrize("status", ["pending_delete", "deleted"])
async def test_new_references_to_unavailable_photos_are_rejected(app_client, f03_users, db_session_factory, status):
    admin = await _token(app_client, "f03_admin_a")
    case_id = await _new_case(app_client, admin)
    photo_id = await _new_photo(db_session_factory, case_id, uploaded_by=None, status=status)
    measurement = await app_client.post(
        f"/api/v1/cases/{case_id}/measurements", json={"referenceImageId": photo_id}, headers=_auth(admin)
    )
    marker = await app_client.post(
        "/api/v1/markers",
        json={"caseId": case_id, "imageId": photo_id, "markerType": "note", "x": 0.1, "y": 0.1, "label": "x"},
        headers=_auth(admin),
    )
    assert (measurement.status_code, marker.status_code) == (422, 422)


async def test_purge_ledger_survives_database_restore_and_drives_reapply(
    app_client, f03_users, db_session_factory, tmp_path, monkeypatch
):
    import json

    from app.platform.config import get_settings
    from app.modules.media.purge_ledger import read_purged_photo_ids
    from scripts.reapply_photo_purges import _reapply

    ledger = tmp_path / "ledger" / "photo-purge-ledger.jsonl"
    monkeypatch.setattr(get_settings(), "photo_purge_ledger_path", str(ledger))
    admin = await _token(app_client, "f03_admin_a")
    case_id = await _new_case(app_client, admin)
    backup_taken_at = datetime.now(UTC)
    photo_id = await _new_photo(db_session_factory, case_id, uploaded_by=None)

    with patch("app.modules.media.photo_service.delete_storage_file", new_callable=AsyncMock):
        purged = await app_client.post(
            f"/api/v1/cases/{case_id}/images/{photo_id}/purge",
            json={"confirmImageId": photo_id},
            headers=_auth(admin),
        )
    assert purged.status_code == 200, purged.text
    entry = json.loads(ledger.read_text(encoding="utf-8").splitlines()[-1])
    assert {key: entry[key] for key in ("photo_id", "case_id", "org_id", "actor_id", "action")} == {
        "photo_id": photo_id,
        "case_id": case_id,
        "org_id": ORG_A,
        "actor_id": "f03_admin_a",
        "action": "image.purge",
    }

    # Simulate restoring a database backup taken before the purge: the photo is
    # active again and the DB audit row is gone (storage would be restored too).
    async with db_session_factory() as session:
        photo = await session.get(ProjectPhoto, photo_id)
        photo.status, photo.deleted_at, photo.deleted_by_user_id = "active", None, None
        for row in (await session.execute(select(AuditLog).where(AuditLog.resource_id == photo_id))).scalars():
            await session.delete(row)
        await session.commit()
    assert photo_id in (await app_client.get(f"/api/v1/cases/{case_id}/images", headers=_auth(admin))).text

    # The ledger lives outside the DB, so it still knows; re-apply erases photo and files again.
    ids = read_purged_photo_ids(ledger, since=backup_taken_at)
    assert ids == [photo_id]
    assert read_purged_photo_ids(ledger, since=datetime.now(UTC) + timedelta(seconds=5)) == []
    with patch("app.modules.media.photo_service.delete_storage_file", new_callable=AsyncMock) as storage_delete:
        assert await _reapply(ids) == 0
    assert storage_delete.await_count == 3
    assert (await _photo(db_session_factory, photo_id)).status == "deleted"
    assert photo_id not in (await app_client.get(f"/api/v1/cases/{case_id}/images", headers=_auth(admin))).text


async def test_purge_fails_closed_without_a_writable_ledger(app_client, f03_users, db_session_factory, tmp_path, monkeypatch):
    from app.platform.config import get_settings

    admin = await _token(app_client, "f03_admin_a")
    case_id = await _new_case(app_client, admin)
    photo_id = await _new_photo(db_session_factory, case_id, uploaded_by=None)
    body = {"confirmImageId": photo_id}

    # Production without a configured ledger: refused before anything changes.
    # A production API process always has a zone (F3); purge lives in the tenant zones.
    # The token was issued in the dev zone, so authenticate again in the desktop zone.
    monkeypatch.setattr(get_settings(), "nc_zone", "desktop")
    desktop_admin = await _token(app_client, "f03_admin_a")
    monkeypatch.setattr(get_settings(), "app_env", "production")
    refused = await app_client.post(
        f"/api/v1/cases/{case_id}/images/{photo_id}/purge", json=body, headers=_auth(desktop_admin)
    )
    monkeypatch.setattr(get_settings(), "app_env", "development")
    monkeypatch.setattr(get_settings(), "nc_zone", "")
    assert refused.status_code == 503

    # Ledger configured but not writable (a directory sits at its path).
    blocked = tmp_path / "ledger-is-a-directory"
    blocked.mkdir()
    monkeypatch.setattr(get_settings(), "photo_purge_ledger_path", str(blocked))
    with patch("app.modules.media.photo_service.delete_storage_file", new_callable=AsyncMock) as storage_delete:
        failed = await app_client.post(f"/api/v1/cases/{case_id}/images/{photo_id}/purge", json=body, headers=_auth(admin))
    assert failed.status_code == 503
    storage_delete.assert_not_awaited()
    assert (await _photo(db_session_factory, photo_id)).status == "active"


async def test_marker_create_and_delete_are_persisted(app_client, f03_users, db_session_factory):
    from app.modules.media.models import Marker

    admin = await _token(app_client, "f03_admin_a")
    case_id = await _new_case(app_client, admin)
    photo_id = await _new_photo(db_session_factory, case_id, uploaded_by=None)
    created = await app_client.post(
        "/api/v1/markers",
        json={"caseId": case_id, "imageId": photo_id, "markerType": "note", "x": 0.2, "y": 0.3, "label": "persist"},
        headers=_auth(admin),
    )
    assert created.status_code == 201, created.text
    marker_id = created.json()["id"]
    async with db_session_factory() as session:
        assert await session.get(Marker, marker_id) is not None
    listed = await app_client.get(f"/api/v1/markers?case_id={case_id}", headers=_auth(admin))
    assert marker_id in listed.text

    deleted = await app_client.delete(f"/api/v1/markers/{marker_id}", headers=_auth(admin))
    assert deleted.status_code == 200, deleted.text
    async with db_session_factory() as session:
        assert await session.get(Marker, marker_id) is None
