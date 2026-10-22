"""NC-007 etapa 1, kap. 6.1–6.3: streamování fotek a exportů z core.

Kontrakt: docs/security/NC-007_STAGE1_CONTRACT.md. Ověřuje:
* ``GET /api/v1/files/images/{id}/{variant}`` – obsah bajt po bajtu, Range
  (206/416), bezpečnostní hlavičky, allowlist Content-Type, stejné 404 pro
  cizí/smazanou/purgnutou/neexistující fotku, neznámou a nehotovou variantu,
* ``GET /api/v1/files/exports/{id}`` – role jako ``GET /exports/{id}``, jen
  dokončený a neexpirovaný export, audit ``export.downloaded``,
* hodnoty URL polí v odpovědích API (žádná URL úložiště),
* zóny: files v G a D, v zóně A 404,
* starý ``/images/{id}/preview`` streamuje místo přesměrování na úložiště.

Testy běží na lokálním adaptéru úložiště (STORAGE_ROOT z conftest).
"""

from __future__ import annotations

import io
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import select, update

from app.modules.audit.models import AuditLog
from app.modules.exports.models import ProjectExport
from app.modules.identity.auth_service import hash_password
from app.modules.identity.models import User
from app.modules.media.models import ProjectPhoto
from app.platform.http.file_streaming import FILE_RESPONSE_CSP, parse_byte_range, RangeNotSatisfiableError
from app.platform.storage.local_photo_storage import (
    iter_storage_file,
    validate_storage_key,
    write_storage_file,
)

ORG_A = "org_e2e_a"
ORG_B = "org_e2e_b"
PASSWORD = "Nc007-Files-Pass-1!"
_USERS = {
    "nc7_technician_a": (ORG_A, "technician"),
    "nc7_manager_a": (ORG_A, "manager"),
    "nc7_manager_b": (ORG_B, "manager"),
}
_STORAGE_URL_MARKERS = ("X-Amz-", "x-amz-", ":9000", "/mock-storage/", "/storage/")


def _email(user_id: str) -> str:
    return f"{user_id}@nc007.test"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _jpeg(size: tuple[int, int] = (64, 48), color=(10, 120, 200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest_asyncio.fixture
async def nc7_users(test_tenants, db_session_factory):
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


@pytest_asyncio.fixture
async def tokens(app_client, nc7_users) -> dict[str, str]:
    return {user_id: await _token(app_client, user_id) for user_id in _USERS}


async def _new_case(client, token: str) -> str:
    response = await client.post("/api/v1/cases", json={"title": f"NC007 {uuid.uuid4().hex[:6]}"}, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _new_photo(
    db_session_factory,
    case_id: str,
    *,
    original: bytes,
    preview: bytes | None = None,
    ai_input: bytes | None = None,
    processing_status: str = "ready",
    mime_type: str = "image/jpeg",
    original_filename: str = "střecha fotka.jpg",
    write_files: bool = True,
) -> str:
    photo_id = f"pho_nc7_{uuid.uuid4().hex[:8]}"
    keys = {
        "storage_key": f"projects/{case_id}/{photo_id}.jpg",
        "preview_storage_key": f"projects/{case_id}/preview/{photo_id}.jpg",
        "ai_input_storage_key": f"projects/{case_id}/ai/{photo_id}.jpg",
    }
    if write_files:
        await write_storage_file(relative_storage_key=keys["storage_key"], content=original)
        if preview is not None:
            await write_storage_file(relative_storage_key=keys["preview_storage_key"], content=preview)
        if ai_input is not None:
            await write_storage_file(relative_storage_key=keys["ai_input_storage_key"], content=ai_input)
    async with db_session_factory() as session:
        session.add(
            ProjectPhoto(
                id=photo_id,
                project_id=case_id,
                status="active",
                original_filename=original_filename,
                mime_type=mime_type,
                file_size=len(original),
                processing_status=processing_status,
                uploaded_by_user_id="nc7_manager_a",
                **keys,
            )
        )
        await session.commit()
    return photo_id


async def _new_export(
    db_session_factory,
    case_id: str,
    *,
    content: bytes | None = b"%PDF-1.4 nc007 export",
    status: str = "completed",
    expires_in: timedelta = timedelta(days=7),
    file_name: str = "nabidka.pdf",
) -> str:
    export_id = f"exp_nc7_{uuid.uuid4().hex[:8]}"
    storage_key = f"exports/{case_id}/{export_id}-{file_name}" if status == "completed" else None
    if storage_key and content is not None:
        await write_storage_file(relative_storage_key=storage_key, content=content)
    now = datetime.now(UTC)
    async with db_session_factory() as session:
        session.add(
            ProjectExport(
                id=export_id,
                project_id=case_id,
                export_type="quote-pdf",
                status=status,
                file_name=file_name,
                storage_key=storage_key,
                created_at=now,
                completed_at=now if status == "completed" else None,
                expires_at=now + expires_in,
            )
        )
        await session.commit()
    return export_id


def _assert_security_headers(response, *, disposition: str) -> None:
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["content-security-policy"] == FILE_RESPONSE_CSP == "default-src 'none'; sandbox"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-disposition"].startswith(f'{disposition}; filename="')
    assert "location" not in response.headers


@pytest_asyncio.fixture
async def ready_photo(app_client, tokens, db_session_factory):
    case_id = await _new_case(app_client, tokens["nc7_manager_a"])
    original = _jpeg((640, 480)) + os.urandom(150_000)  # > 2 bloky po 64 KiB
    preview = _jpeg((160, 120), (1, 2, 3))
    ai_input = _jpeg((128, 96), (4, 5, 6))
    photo_id = await _new_photo(db_session_factory, case_id, original=original, preview=preview, ai_input=ai_input)
    return {"case_id": case_id, "photo_id": photo_id, "original": original, "preview": preview, "ai-input": ai_input}


# ── Obsah a hlavičky ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("variant", ["original", "preview", "ai-input"])
async def test_each_variant_streams_its_exact_bytes(app_client, tokens, ready_photo, variant):
    response = await app_client.get(
        f"/api/v1/files/images/{ready_photo['photo_id']}/{variant}", headers=_auth(tokens["nc7_manager_a"])
    )
    assert response.status_code == 200, response.text
    assert response.content == ready_photo[variant]
    assert response.headers["content-length"] == str(len(ready_photo[variant]))
    assert response.headers["content-type"] == "image/jpeg"
    _assert_security_headers(response, disposition="attachment" if variant == "original" else "inline")
    # Bezpečné jméno: jen ASCII bez mezer a uvozovek.
    assert response.headers["content-disposition"].endswith('filename="st-echa-fotka.jpg"')


async def test_range_returns_206_with_the_exact_slice(app_client, tokens, ready_photo):
    url = f"/api/v1/files/images/{ready_photo['photo_id']}/original"
    data = ready_photo["original"]
    size = len(data)
    cases = {
        "bytes=10-19": (10, 19),
        "bytes=-5": (size - 5, size - 1),
        f"bytes={size - 7}-": (size - 7, size - 1),
        f"bytes=65530-{size + 1000}": (65530, size - 1),  # konec se zařízne na velikost
    }
    for header, (start, end) in cases.items():
        response = await app_client.get(url, headers={**_auth(tokens["nc7_manager_a"]), "Range": header})
        assert response.status_code == 206, (header, response.text)
        assert response.content == data[start : end + 1], header
        assert response.headers["content-range"] == f"bytes {start}-{end}/{size}"
        assert response.headers["content-length"] == str(end - start + 1)
        _assert_security_headers(response, disposition="attachment")


@pytest.mark.parametrize("header", ["bytes={size}-", "bytes=20-10", "bytes=abc", "items=0-1", "bytes=0-1,3-4", "bytes=-0"])
async def test_invalid_range_returns_416(app_client, tokens, ready_photo, header):
    size = len(ready_photo["original"])
    response = await app_client.get(
        f"/api/v1/files/images/{ready_photo['photo_id']}/original",
        headers={**_auth(tokens["nc7_manager_a"]), "Range": header.format(size=size)},
    )
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{size}"
    assert response.content == b""
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_if_range_without_validators_serves_the_whole_file(app_client, tokens, ready_photo):
    response = await app_client.get(
        f"/api/v1/files/images/{ready_photo['photo_id']}/original",
        headers={**_auth(tokens["nc7_manager_a"]), "Range": "bytes=0-9", "If-Range": '"etag"'},
    )
    assert response.status_code == 200
    assert response.content == ready_photo["original"]


@pytest.mark.parametrize(
    ("stored", "served"),
    [
        ("image/png", "image/png"),
        ("image/webp", "image/webp"),
        ("image/heic", "image/heic"),
        ("image/svg+xml", "application/octet-stream"),
        ("text/html", "application/octet-stream"),
    ],
)
async def test_content_type_comes_from_the_allowlist(app_client, tokens, db_session_factory, stored, served):
    case_id = await _new_case(app_client, tokens["nc7_manager_a"])
    photo_id = await _new_photo(db_session_factory, case_id, original=b"<svg onload=alert(1)>", mime_type=stored)
    response = await app_client.get(f"/api/v1/files/images/{photo_id}/original", headers=_auth(tokens["nc7_manager_a"]))
    assert response.status_code == 200
    assert response.headers["content-type"] == served
    assert response.headers["content-security-policy"] == FILE_RESPONSE_CSP


# ── 404: izolace firem, smazání, varianty ────────────────────────────────────


async def test_foreign_deleted_and_missing_photos_answer_the_same_404(app_client, tokens, ready_photo, db_session_factory):
    photo_id = ready_photo["photo_id"]
    foreign = await app_client.get(f"/api/v1/files/images/{photo_id}/original", headers=_auth(tokens["nc7_manager_b"]))
    missing = await app_client.get("/api/v1/files/images/pho_missing0/original", headers=_auth(tokens["nc7_manager_a"]))
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "Image not found."}

    # Soft delete přes API: okamžitě 404, i pro náhled a AI vstup.
    deleted = await app_client.delete(
        f"/api/v1/cases/{ready_photo['case_id']}/images/{photo_id}", headers=_auth(tokens["nc7_manager_a"])
    )
    assert deleted.status_code == 200, deleted.text
    for variant in ("original", "preview", "ai-input"):
        response = await app_client.get(f"/api/v1/files/images/{photo_id}/{variant}", headers=_auth(tokens["nc7_manager_a"]))
        assert response.status_code == 404
        assert response.json() == missing.json()
    legacy = await app_client.get(f"/api/v1/images/{photo_id}/preview", headers=_auth(tokens["nc7_manager_a"]))
    assert legacy.status_code == 404


@pytest.mark.parametrize("status", ["pending_delete", "purge_pending", "deleted"])
async def test_purged_photo_answers_404_immediately(app_client, tokens, ready_photo, db_session_factory, status):
    async with db_session_factory() as session:
        await session.execute(update(ProjectPhoto).where(ProjectPhoto.id == ready_photo["photo_id"]).values(status=status))
        await session.commit()
    # Soubory v úložišti pořád existují (purge je dvoufázový) – přesto 404.
    response = await app_client.get(
        f"/api/v1/files/images/{ready_photo['photo_id']}/original", headers=_auth(tokens["nc7_manager_a"])
    )
    assert response.status_code == 404


async def test_purge_through_the_api_makes_the_photo_404(app_client, tokens, ready_photo, db_session_factory):
    from app.modules.identity.models import User as UserModel

    async with db_session_factory() as session:
        if await session.get(UserModel, "nc7_admin_a") is None:
            session.add(
                UserModel(
                    id="nc7_admin_a", organization_id=ORG_A, email=_email("nc7_admin_a"),
                    password_hash=hash_password(PASSWORD), full_name="nc7_admin_a", role="admin",
                    is_active=True, is_superadmin=False,
                )
            )
            await session.commit()
    admin = await _token(app_client, "nc7_admin_a")
    photo_id = ready_photo["photo_id"]
    purge = await app_client.post(
        f"/api/v1/cases/{ready_photo['case_id']}/images/{photo_id}/purge",
        json={"confirmImageId": photo_id},
        headers=_auth(admin),
    )
    assert purge.status_code in (200, 202), purge.text
    for variant in ("original", "preview", "ai-input"):
        response = await app_client.get(f"/api/v1/files/images/{photo_id}/{variant}", headers=_auth(admin))
        assert response.status_code == 404


@pytest.mark.parametrize("variant", ["thumbnail", "ai_input", "ORIGINAL", "aiInput", ".."])
async def test_unknown_variant_is_404(app_client, tokens, ready_photo, variant):
    response = await app_client.get(
        f"/api/v1/files/images/{ready_photo['photo_id']}/{variant}", headers=_auth(tokens["nc7_manager_a"])
    )
    assert response.status_code == 404


async def test_unfinished_variants_are_404_but_the_original_streams(app_client, tokens, db_session_factory):
    case_id = await _new_case(app_client, tokens["nc7_manager_a"])
    original = _jpeg()
    photo_id = await _new_photo(
        db_session_factory, case_id, original=original, preview=b"stale", ai_input=b"stale", processing_status="processing"
    )
    headers = _auth(tokens["nc7_manager_a"])
    assert (await app_client.get(f"/api/v1/files/images/{photo_id}/preview", headers=headers)).status_code == 404
    assert (await app_client.get(f"/api/v1/files/images/{photo_id}/ai-input", headers=headers)).status_code == 404
    response = await app_client.get(f"/api/v1/files/images/{photo_id}/original", headers=headers)
    assert response.status_code == 200
    assert response.content == original

    listed = await app_client.get(f"/api/v1/cases/{case_id}/images", headers=headers)
    item = next(i for i in listed.json()["items"] if i["id"] == photo_id)
    assert item["variants"]["preview"]["url"] is None
    assert item["variants"]["aiInput"]["url"] is None
    assert item["url"] == f"/api/v1/files/images/{photo_id}/original"


async def test_object_missing_in_storage_is_404(app_client, tokens, db_session_factory):
    case_id = await _new_case(app_client, tokens["nc7_manager_a"])
    photo_id = await _new_photo(db_session_factory, case_id, original=b"x", write_files=False)
    response = await app_client.get(f"/api/v1/files/images/{photo_id}/original", headers=_auth(tokens["nc7_manager_a"]))
    assert response.status_code == 404


async def test_traversal_key_in_the_database_is_never_read(app_client, tokens, ready_photo, db_session_factory):
    async with db_session_factory() as session:
        await session.execute(
            update(ProjectPhoto)
            .where(ProjectPhoto.id == ready_photo["photo_id"])
            .values(storage_key=f"projects/{ready_photo['case_id']}/../../../conftest.py")
        )
        await session.commit()
    response = await app_client.get(
        f"/api/v1/files/images/{ready_photo['photo_id']}/original", headers=_auth(tokens["nc7_manager_a"])
    )
    assert response.status_code == 404


async def test_unauthenticated_file_request_is_401(app_client, ready_photo):
    response = await app_client.get(f"/api/v1/files/images/{ready_photo['photo_id']}/original")
    assert response.status_code == 401


# ── Starý /images/{id}/preview ───────────────────────────────────────────────


async def test_legacy_preview_streams_instead_of_redirecting(app_client, tokens, ready_photo, db_session_factory):
    headers = _auth(tokens["nc7_manager_a"])
    response = await app_client.get(
        f"/api/v1/images/{ready_photo['photo_id']}/preview", headers=headers, follow_redirects=False
    )
    assert response.status_code == 200
    assert response.content == ready_photo["preview"]
    _assert_security_headers(response, disposition="inline")

    # Náhled ještě není hotový → originál (jako dřív `preview.url or url`).
    case_id = await _new_case(app_client, tokens["nc7_manager_a"])
    original = _jpeg((20, 20))
    pending = await _new_photo(db_session_factory, case_id, original=original, processing_status="uploaded")
    fallback = await app_client.get(f"/api/v1/images/{pending}/preview", headers=headers, follow_redirects=False)
    assert fallback.status_code == 200
    assert fallback.content == original
    assert fallback.headers["content-disposition"].startswith("inline;")


# ── Exporty ──────────────────────────────────────────────────────────────────


async def test_completed_export_streams_with_audit(app_client, tokens, db_session_factory):
    case_id = await _new_case(app_client, tokens["nc7_manager_a"])
    content = b"%PDF-1.7\n" + os.urandom(100_000)
    export_id = await _new_export(db_session_factory, case_id, content=content)

    response = await app_client.get(f"/api/v1/files/exports/{export_id}", headers=_auth(tokens["nc7_manager_a"]))
    assert response.status_code == 200, response.text
    assert response.content == content
    assert response.headers["content-type"] == "application/pdf"
    _assert_security_headers(response, disposition="attachment")
    assert response.headers["content-disposition"] == 'attachment; filename="nabidka.pdf"'

    partial = await app_client.get(
        f"/api/v1/files/exports/{export_id}", headers={**_auth(tokens["nc7_manager_a"]), "Range": "bytes=0-99"}
    )
    assert partial.status_code == 206
    assert partial.content == content[:100]

    async with db_session_factory() as session:
        rows = (
            await session.execute(
                select(AuditLog).where(AuditLog.action == "export.downloaded", AuditLog.resource_id == export_id)
            )
        ).scalars().all()
    assert len(rows) == 2
    row = rows[0]
    assert row.user_id == "nc7_manager_a"
    assert row.org_id == ORG_A
    assert row.resource_type == "export"
    assert row.ip
    assert row.detail["caseId"] == case_id
    assert sorted(r.detail["partial"] for r in rows) == [False, True]


async def test_export_download_requires_the_same_role_as_get_export(app_client, tokens, db_session_factory):
    case_id = await _new_case(app_client, tokens["nc7_manager_a"])
    export_id = await _new_export(db_session_factory, case_id)
    technician = _auth(tokens["nc7_technician_a"])
    meta = await app_client.get(f"/api/v1/exports/{export_id}", headers=technician)
    download = await app_client.get(f"/api/v1/files/exports/{export_id}", headers=technician)
    assert meta.status_code == download.status_code == 403


async def test_foreign_unfinished_expired_and_missing_exports_are_404(app_client, tokens, db_session_factory):
    case_id = await _new_case(app_client, tokens["nc7_manager_a"])
    manager_a = _auth(tokens["nc7_manager_a"])
    completed = await _new_export(db_session_factory, case_id)
    foreign = await app_client.get(f"/api/v1/files/exports/{completed}", headers=_auth(tokens["nc7_manager_b"]))
    assert foreign.status_code == 404
    expected = foreign.json()
    for export_id in (
        await _new_export(db_session_factory, case_id, status="pending"),
        await _new_export(db_session_factory, case_id, status="generating"),
        await _new_export(db_session_factory, case_id, status="failed"),
        await _new_export(db_session_factory, case_id, expires_in=timedelta(seconds=-1)),
        await _new_export(db_session_factory, case_id, content=None),  # chybí v úložišti
        "exp_nc7_missing",
    ):
        response = await app_client.get(f"/api/v1/files/exports/{export_id}", headers=manager_a)
        assert response.status_code == 404, export_id
        assert response.json() == expected

    async with db_session_factory() as session:
        audited = (
            await session.execute(select(AuditLog).where(AuditLog.action == "export.downloaded", AuditLog.resource_id == completed))
        ).scalars().all()
    assert audited == []


async def test_export_expired_by_photo_purge_is_404_immediately(app_client, tokens, db_session_factory):
    case_id = await _new_case(app_client, tokens["nc7_manager_a"])
    export_id = await _new_export(db_session_factory, case_id)
    headers = _auth(tokens["nc7_manager_a"])
    assert (await app_client.get(f"/api/v1/files/exports/{export_id}", headers=headers)).status_code == 200
    async with db_session_factory() as session:
        await session.execute(
            update(ProjectExport).where(ProjectExport.id == export_id).values(expires_at=datetime.now(UTC))
        )
        await session.commit()
    assert (await app_client.get(f"/api/v1/files/exports/{export_id}", headers=headers)).status_code == 404


# ── Hodnoty URL polí: žádná URL úložiště ─────────────────────────────────────


async def test_api_responses_contain_no_storage_urls(app_client, tokens, ready_photo, db_session_factory):
    headers = _auth(tokens["nc7_manager_a"])
    case_id, photo_id = ready_photo["case_id"], ready_photo["photo_id"]
    export_id = await _new_export(db_session_factory, case_id)

    listed = await app_client.get(f"/api/v1/cases/{case_id}/images", headers=headers)
    detail = await app_client.get(f"/api/v1/cases/{case_id}", headers=headers)
    export = await app_client.get(f"/api/v1/exports/{export_id}", headers=headers)
    for response in (listed, detail, export):
        assert response.status_code == 200, response.text
        for marker in _STORAGE_URL_MARKERS:
            assert marker not in response.text, (response.request.url, marker)

    item = next(i for i in listed.json()["items"] if i["id"] == photo_id)
    assert item["url"] == f"/api/v1/files/images/{photo_id}/original"
    assert item["variants"]["original"]["url"] == f"/api/v1/files/images/{photo_id}/original"
    assert item["variants"]["preview"]["url"] == f"/api/v1/files/images/{photo_id}/preview"
    assert item["variants"]["aiInput"]["url"] == f"/api/v1/files/images/{photo_id}/ai-input"
    assert export.json()["downloadUrl"] == f"/api/v1/files/exports/{export_id}"

    # Každá vrácená URL je skutečně stažitelná stejným tokenem.
    for url in (item["url"], item["variants"]["preview"]["url"], item["variants"]["aiInput"]["url"], export.json()["downloadUrl"]):
        assert (await app_client.get(url, headers=headers)).status_code == 200, url


# ── Zóny ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("zone", "expected"),
    [("gateway", 401), ("desktop", 401), ("admin", 404)],
)
async def test_file_routes_are_exposed_in_gateway_and_desktop_only(app_client, monkeypatch, zone, expected):
    from app.platform.config import get_settings
    from app.platform.http.exposure import EXPOSURE

    assert EXPOSURE[("GET", "/api/v1/files/images/{image_id}/{variant}")] == frozenset({"gateway", "desktop"})
    assert EXPOSURE[("GET", "/api/v1/files/exports/{export_id}")] == frozenset({"gateway", "desktop"})
    monkeypatch.setattr(get_settings(), "nc_zone", zone)
    for url in ("/api/v1/files/images/pho_x/original", "/api/v1/files/exports/exp_x"):
        response = await app_client.get(url)
        assert response.status_code == expected, (zone, url, response.text)
        if expected == 404:
            assert response.json() == {"detail": "Not Found"}


# ── Úložiště a parser rozsahu (jednotkově) ───────────────────────────────────


@pytest.mark.parametrize(
    "key",
    [
        "projects/../secret",
        "projects/a/../../x",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "projects\\a\\b.jpg",
        "projects//a.jpg",
        "projects/./a.jpg",
        "projects/a\x00.jpg",
        "",
    ],
)
def test_storage_refuses_unsafe_keys(key):
    with pytest.raises(ValueError):
        validate_storage_key(key)


def test_storage_accepts_regular_keys():
    assert validate_storage_key("projects/prj_1/preview/a-b_c.jpg") == "projects/prj_1/preview/a-b_c.jpg"
    assert validate_storage_key("exports/prj_1/exp_1-nabidka.pdf")


async def test_local_storage_reads_in_chunks_and_ranges():
    data = os.urandom(200_000)
    key = f"projects/nc7_chunks/{uuid.uuid4().hex}.bin"
    await write_storage_file(relative_storage_key=key, content=data)
    chunks = [chunk async for chunk in iter_storage_file(relative_storage_key=key)]
    assert b"".join(chunks) == data
    assert max(len(c) for c in chunks) == 64 * 1024
    assert len(chunks) == 4
    ranged = b"".join([c async for c in iter_storage_file(relative_storage_key=key, start=70_000, end=140_000, chunk_size=1000)])
    assert ranged == data[70_000:140_001]


def test_parse_byte_range():
    assert parse_byte_range(None, 10) is None
    assert parse_byte_range("bytes=0-0", 10) == (0, 0)
    assert parse_byte_range("bytes=5-", 10) == (5, 9)
    assert parse_byte_range("bytes=-3", 10) == (7, 9)
    assert parse_byte_range("bytes=-30", 10) == (0, 9)
    assert parse_byte_range("BYTES=2-4", 10) == (2, 4)
    for bad in ("bytes=10-", "bytes=", "bytes=-", "bytes=1-2-3", "bytes=0-1,2-3", "bytes=٣-5", "bytes=4-2"):
        with pytest.raises(RangeNotSatisfiableError):
            parse_byte_range(bad, 10)
    with pytest.raises(RangeNotSatisfiableError):
        parse_byte_range("bytes=0-0", 0)


async def test_s3_adapter_streams_with_range_and_validates_keys(monkeypatch):
    """S3 adaptér: HTTP Range na get_object, čtení po blocích, žádná URL."""
    from unittest.mock import MagicMock, patch

    import app.platform.storage.s3_photo_storage as s3

    monkeypatch.setenv("S3_BUCKET", "nc-test")
    data = os.urandom(10_000)
    body = io.BytesIO(data[100:5101])
    client = MagicMock()
    client.get_object.return_value = {"Body": body}
    client.head_object.return_value = {"ContentLength": len(data)}
    with patch.object(s3, "_get_s3_client", return_value=client):
        assert await s3.get_storage_object_size(relative_storage_key="projects/p/a.jpg") == len(data)
        chunks = [c async for c in s3.iter_storage_file(relative_storage_key="projects/p/a.jpg", start=100, end=5100, chunk_size=1024)]
        with pytest.raises(ValueError):
            await s3.get_storage_object_size(relative_storage_key="projects/../a.jpg")
    assert b"".join(chunks) == data[100:5101]
    assert max(len(c) for c in chunks) == 1024
    client.get_object.assert_called_once_with(Bucket="nc-test", Key="projects/p/a.jpg", Range="bytes=100-5100")
    assert body.closed
