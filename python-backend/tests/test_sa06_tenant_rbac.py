"""SA-06 regression suite: tenant RBAC for configuration, offers, exports and photos.

Variant A (approved 17. 10. 2026, docs/security/RBAC_ROLE_MATRIX.md):
technicians work in the field (photos, measurements, markers) but may not change
catalogs, pricebooks, suppliers or work-type settings, approve offers, skip
review, cancel analysis, download exports, or delete/restore photos. Managers and
company admins may, inside their own tenant only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AuditLog, ProjectPhoto, User
from app.services.auth_service import hash_password

ORG_A = "org_e2e_a"
ORG_B = "org_e2e_b"
PASSWORD = "Sa06-Initial-Pass-1!"

_USERS = {
    "sa06_technician_a": (ORG_A, "technician"),
    "sa06_manager_a": (ORG_A, "manager"),
    "sa06_admin_a": (ORG_A, "admin"),
    "sa06_manager_b": (ORG_B, "manager"),
}


def _email(user_id: str) -> str:
    return f"{user_id}@sa06.test"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def sa06_users(test_tenants, db_session_factory):
    async with db_session_factory() as session:
        for user_id, (org, role) in _USERS.items():
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
                        is_superadmin=False,
                    )
                )
        await session.commit()
    return test_tenants


async def _token(client, user_id: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": _email(user_id), "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["accessToken"]


async def _new_case(client, token: str) -> str:
    response = await client.post("/api/v1/cases", json={"title": f"SA-06 {uuid.uuid4().hex[:6]}"}, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _new_photo(db_session_factory, case_id: str) -> str:
    photo_id = f"pho_sa06_{uuid.uuid4().hex[:8]}"
    async with db_session_factory() as session:
        session.add(
            ProjectPhoto(
                id=photo_id,
                project_id=case_id,
                status="active",
                storage_key=f"projects/{case_id}/{photo_id}.jpg",
                preview_storage_key=f"projects/{case_id}/preview/{photo_id}.jpg",
                original_filename=f"{photo_id}.jpg",
                mime_type="image/jpeg",
                file_size=1,
            )
        )
        await session.commit()
    return photo_id


async def _photo(db_session_factory, photo_id: str) -> ProjectPhoto:
    async with db_session_factory() as session:
        photo = await session.get(ProjectPhoto, photo_id)
        assert photo is not None
        return photo


# ── Company configuration and approvals: technicians are refused ──────────────


def _config_writes(tenants: dict) -> list[tuple[str, str, object]]:
    # Bodies are deliberately invalid (a JSON array): the role dependency rejects a
    # technician before the body is read, while managers/admins get 422 instead of
    # mutating the shared session fixtures.
    return [
        ("patch", f"/api/v1/material-catalog/{tenants['material_a']}", []),
        ("patch", f"/api/v1/suppliers/{tenants['supplier_a']}", []),
        ("post", "/api/v1/pricebooks", []),
        ("put", "/api/v1/work-catalog/work-types/roof_repair/settings", []),
        ("patch", "/api/v1/offer-requests/offer_does_not_matter", {"action": "approve"}),
        ("post", "/api/v1/analysis-jobs/job_does_not_matter/cancel", None),
        ("get", "/api/v1/exports/export_does_not_matter", None),
    ]


async def _call(client, method: str, path: str, body, token: str):
    kwargs = {"headers": _auth(token)}
    if body is not None:
        kwargs["json"] = body
    return await getattr(client, method)(path, **kwargs)


@pytest.mark.parametrize("index", range(7))
async def test_technician_cannot_change_company_configuration_or_approve(app_client, sa06_users, index):
    method, path, body = _config_writes(sa06_users)[index]
    token = await _token(app_client, "sa06_technician_a")
    response = await _call(app_client, method, path, body, token)
    assert response.status_code == 403, f"{method.upper()} {path} -> {response.status_code} {response.text}"


@pytest.mark.parametrize("actor", ["sa06_manager_a", "sa06_admin_a"])
@pytest.mark.parametrize("index", range(7))
async def test_manager_and_company_admin_pass_the_role_check(app_client, sa06_users, actor, index):
    method, path, body = _config_writes(sa06_users)[index]
    token = await _token(app_client, actor)
    response = await _call(app_client, method, path, body, token)
    # Role check passed; the outcome now depends only on the payload/target.
    assert response.status_code != 403, f"{actor} {method.upper()} {path} -> {response.text}"


async def test_manager_updates_own_material_and_supplier(app_client, sa06_users):
    token = await _token(app_client, "sa06_manager_a")
    material = await app_client.patch(
        f"/api/v1/material-catalog/{sa06_users['material_a']}",
        json={"defaultUnitPrice": 120.0},  # unchanged seed value
        headers=_auth(token),
    )
    supplier = await app_client.patch(
        f"/api/v1/suppliers/{sa06_users['supplier_a']}",
        json={"name": "Dodavatel Alpha", "integrationType": "manual"},
        headers=_auth(token),
    )
    assert material.status_code == 200, material.text
    assert supplier.status_code == 200, supplier.text


async def test_manager_cannot_touch_another_tenants_configuration(app_client, sa06_users):
    token = await _token(app_client, "sa06_manager_a")
    material = await app_client.patch(
        f"/api/v1/material-catalog/{sa06_users['material_b']}",
        json={"defaultUnitPrice": 1.0},
        headers=_auth(token),
    )
    supplier = await app_client.patch(
        f"/api/v1/suppliers/{sa06_users['supplier_b']}",
        json={"name": "Owned", "integrationType": "manual"},
        headers=_auth(token),
    )
    assert material.status_code == 404, material.text
    assert supplier.status_code == 404, supplier.text


@pytest.mark.parametrize("flags", [{"auto_send": True}, {"auto_review_bypass": True}])
async def test_technician_cannot_skip_offer_review(app_client, sa06_users, flags):
    token = await _token(app_client, "sa06_technician_a")
    response = await app_client.post(
        "/api/v1/offer-requests",
        json={
            "idempotency_key": f"sa06-{uuid.uuid4().hex}",
            "work_type_code": "roof_repair",
            "title": "Technician offer",
            **flags,
        },
        headers=_auth(token),
    )
    assert response.status_code == 403, response.text


async def test_technician_can_still_submit_a_reviewed_offer(app_client, sa06_users):
    token = await _token(app_client, "sa06_technician_a")
    response = await app_client.post(
        "/api/v1/offer-requests",
        json={
            "idempotency_key": f"sa06-{uuid.uuid4().hex}",
            "work_type_code": "roof_repair",
            "title": "Technician offer",
        },
        headers=_auth(token),
    )
    assert response.status_code in (200, 201), response.text


# ── Photos: audited soft delete with restore ──────────────────────────────────


async def test_technician_cannot_delete_or_restore_photos(app_client, sa06_users, db_session_factory):
    manager = await _token(app_client, "sa06_manager_a")
    technician = await _token(app_client, "sa06_technician_a")
    case_id = await _new_case(app_client, manager)
    photo_id = await _new_photo(db_session_factory, case_id)

    deleted = await app_client.delete(f"/api/v1/cases/{case_id}/images/{photo_id}", headers=_auth(technician))
    assert deleted.status_code == 403
    assert (await _photo(db_session_factory, photo_id)).status == "active"

    await app_client.delete(f"/api/v1/cases/{case_id}/images/{photo_id}", headers=_auth(manager))
    restore = await app_client.post(
        f"/api/v1/cases/{case_id}/images/{photo_id}/restore", headers=_auth(technician)
    )
    listing = await app_client.get(f"/api/v1/cases/{case_id}/images/deleted", headers=_auth(technician))
    assert restore.status_code == 403
    assert listing.status_code == 403
    assert (await _photo(db_session_factory, photo_id)).status == "pending_delete"


@pytest.mark.parametrize("actor", ["sa06_manager_a", "sa06_admin_a"])
async def test_soft_delete_is_audited_and_restorable(app_client, sa06_users, db_session_factory, actor):
    token = await _token(app_client, actor)
    case_id = await _new_case(app_client, token)
    photo_id = await _new_photo(db_session_factory, case_id)

    deleted = await app_client.delete(f"/api/v1/cases/{case_id}/images/{photo_id}", headers=_auth(token))
    assert deleted.status_code == 200, deleted.text
    photo = await _photo(db_session_factory, photo_id)
    assert photo.status == "pending_delete"
    assert photo.deleted_by_user_id == actor and photo.deleted_at is not None

    listed = await app_client.get(f"/api/v1/cases/{case_id}/images", headers=_auth(token))
    assert photo_id not in listed.text
    detail = await app_client.get(f"/api/v1/cases/{case_id}", headers=_auth(token))
    assert photo_id not in detail.text  # exports are built from this detail
    trash = await app_client.get(f"/api/v1/cases/{case_id}/images/deleted", headers=_auth(token))
    assert trash.status_code == 200
    assert [(item["id"], item["deletedByUserId"]) for item in trash.json()["items"]] == [(photo_id, actor)]

    restored = await app_client.post(f"/api/v1/cases/{case_id}/images/{photo_id}/restore", headers=_auth(token))
    assert restored.status_code == 200, restored.text
    photo = await _photo(db_session_factory, photo_id)
    assert (photo.status, photo.deleted_at, photo.deleted_by_user_id) == ("active", None, None)
    assert photo_id in (await app_client.get(f"/api/v1/cases/{case_id}/images", headers=_auth(token))).text

    async with db_session_factory() as session:
        actions = {
            row.action
            for row in (
                await session.execute(
                    select(AuditLog).where(AuditLog.resource_id == photo_id, AuditLog.user_id == actor)
                )
            ).scalars()
        }
    assert {"image.delete", "image.restore"} <= actions


async def test_photo_delete_and_restore_are_tenant_isolated(app_client, sa06_users, db_session_factory):
    owner = await _token(app_client, "sa06_manager_a")
    stranger = await _token(app_client, "sa06_manager_b")
    case_id = await _new_case(app_client, owner)
    photo_id = await _new_photo(db_session_factory, case_id)

    deleted = await app_client.delete(f"/api/v1/cases/{case_id}/images/{photo_id}", headers=_auth(stranger))
    assert deleted.status_code == 404
    assert (await _photo(db_session_factory, photo_id)).status == "active"

    await app_client.delete(f"/api/v1/cases/{case_id}/images/{photo_id}", headers=_auth(owner))
    for response in (
        await app_client.post(f"/api/v1/cases/{case_id}/images/{photo_id}/restore", headers=_auth(stranger)),
        await app_client.get(f"/api/v1/cases/{case_id}/images/deleted", headers=_auth(stranger)),
    ):
        assert response.status_code == 404
    assert (await _photo(db_session_factory, photo_id)).status == "pending_delete"


async def test_storage_is_purged_only_after_the_restore_window(app_client, sa06_users, db_session_factory, monkeypatch):
    from app.core.config import get_settings
    from app.repositories.photo_repository import PhotoRepository
    from app.services.photo_service import PhotoService

    token = await _token(app_client, "sa06_manager_a")
    case_id = await _new_case(app_client, token)
    recent = await _new_photo(db_session_factory, case_id)
    expired = await _new_photo(db_session_factory, case_id)
    for photo_id in (recent, expired):
        await app_client.delete(f"/api/v1/cases/{case_id}/images/{photo_id}", headers=_auth(token))
    async with db_session_factory() as session:
        photo = await session.get(ProjectPhoto, expired)
        photo.deleted_at = datetime.now(UTC) - timedelta(hours=200)
        await session.commit()

    monkeypatch.setattr(get_settings(), "photo_delete_retention_hours", 168)
    with patch("app.services.photo_service.delete_storage_file", new_callable=AsyncMock) as purge:
        async with db_session_factory() as session:
            await PhotoService(PhotoRepository(session)).cleanup_pending_deletes(limit=1000)

    purged_keys = {call.kwargs["relative_storage_key"] for call in purge.await_args_list}
    assert f"projects/{case_id}/{expired}.jpg" in purged_keys
    assert f"projects/{case_id}/{recent}.jpg" not in purged_keys
    assert (await _photo(db_session_factory, expired)).status == "deleted"
    assert (await _photo(db_session_factory, recent)).status == "pending_delete"

    gone = await app_client.post(f"/api/v1/cases/{case_id}/images/{expired}/restore", headers=_auth(token))
    assert gone.status_code == 404
    kept = await app_client.post(f"/api/v1/cases/{case_id}/images/{recent}/restore", headers=_auth(token))
    assert kept.status_code == 200
