"""E2E: skutečná gateway proti skutečnému core v zóně ``gateway`` (NC-007 etapa 1).

Nepoužívá mock core: ověřuje, že podpis HMAC, allowlist, session, CSRF, streamování
souborů a odhlášení fungují dohromady přes HTTP. Spouští se jen explicitně, když
běží obě služby (viz ``run_e2e.sh``)::

    NC_E2E_GATEWAY_URL=http://127.0.0.1:8080 NC_E2E_ORIGIN=http://localhost:5173 \
        .venv/Scripts/python.exe -m pytest tests_e2e -q

Účty jsou vývojový seed core (``app/composition/bootstrap.py``).
"""

from __future__ import annotations

import io
import os
import struct
import uuid
import zlib
from collections.abc import Iterator

import httpx
import pytest

GATEWAY = os.environ.get("NC_E2E_GATEWAY_URL", "")
ORIGIN = os.environ.get("NC_E2E_ORIGIN", "")

pytestmark = pytest.mark.skipif(
    not (GATEWAY and ORIGIN),
    reason="NC_E2E_GATEWAY_URL a NC_E2E_ORIGIN nejsou nastavené (E2E běží jen proti živým službám)",
)

MANAGER = ("demo@novu.local", "demo1234")
TECHNICIAN = ("tech@novu.local", "tech1234")
SUPERADMIN = ("admin@novu.cz", "NovuAdmin2024!")
COOKIE = "nc_sid_dev"


def _png() -> bytes:
    """Malé platné PNG 8×8 bez závislosti na Pillow."""
    width = height = 8
    raw = b"".join(b"\x00" + b"\x10\x80\xc0" * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def _client() -> httpx.Client:
    return httpx.Client(base_url=GATEWAY, timeout=30.0, headers={"Origin": ORIGIN})


def _login(client: httpx.Client, credentials: tuple[str, str]) -> httpx.Response:
    return client.post("/bff/auth/login", json={"email": credentials[0], "password": credentials[1]})


def _csrf(client: httpx.Client) -> dict[str, str]:
    session = client.get("/bff/session").json()
    assert session["authenticated"] is True
    return {"X-CSRF-Token": session["csrfToken"]}


@pytest.fixture
def manager() -> Iterator[httpx.Client]:
    with _client() as client:
        response = _login(client, MANAGER)
        assert response.status_code == 200, response.text
        yield client


def test_health_and_core_surface_are_not_public() -> None:
    with _client() as client:
        assert client.get("/bff/health").json() == {"status": "ok"}
        for path in ("/api/v1/cases", "/api/v1/health", "/docs", "/openapi.json", "/metrics", "/admin"):
            assert client.get(path).status_code == 404, path


def test_unauthenticated_api_is_401() -> None:
    with _client() as client:
        assert client.get("/bff/api/cases").status_code == 401
        assert client.get("/bff/session").json() == {"authenticated": False}


def test_bad_credentials_and_unknown_account_answer_the_same() -> None:
    with _client() as client:
        wrong = _login(client, (MANAGER[0], "spatne-heslo"))
        unknown = _login(client, (f"nikdo-{uuid.uuid4().hex[:6]}@example.com", "spatne-heslo"))
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]
    assert COOKIE not in wrong.cookies


def test_superadmin_cannot_log_in_through_the_gateway() -> None:
    with _client() as client:
        response = _login(client, SUPERADMIN)
    assert response.status_code == 401


def test_login_sets_an_opaque_httponly_cookie_and_never_returns_a_jwt() -> None:
    with _client() as client:
        response = _login(client, MANAGER)
    assert response.status_code == 200
    body = response.text
    assert "eyJ" not in body and "accessToken" not in body and "refreshToken" not in body
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=")
    lowered = cookie.lower()
    assert "httponly" in lowered and "samesite=strict" in lowered and "path=/" in lowered
    assert response.json()["user"]["email"] == MANAGER[0]
    assert response.json()["csrfToken"]


def test_api_call_mutation_csrf_and_origin(manager: httpx.Client) -> None:
    assert manager.get("/bff/api/cases").status_code == 200

    title = {"title": f"NC007 E2E {uuid.uuid4().hex[:6]}"}
    missing = manager.post("/bff/api/cases", json=title)
    assert missing.status_code == 403 and missing.json()["code"] == "CSRF_FAILED"

    foreign = manager.post("/bff/api/cases", json=title, headers={**_csrf(manager), "Origin": "https://evil.example"})
    assert foreign.status_code == 403 and foreign.json()["code"] == "ORIGIN_REJECTED"

    created = manager.post("/bff/api/cases", json=title, headers=_csrf(manager))
    assert created.status_code == 201, created.text


def test_upload_and_stream_photo_through_gateway(manager: httpx.Client) -> None:
    csrf = _csrf(manager)
    case = manager.post("/bff/api/cases", json={"title": f"NC007 foto {uuid.uuid4().hex[:6]}"}, headers=csrf)
    assert case.status_code == 201, case.text
    case_id = case.json()["id"]

    image = _png()
    uploaded = manager.post(
        f"/bff/api/cases/{case_id}/images",
        files={"files": ("nc007.png", io.BytesIO(image), "image/png")},
        headers=csrf,
    )
    assert uploaded.status_code == 201, uploaded.text

    listed = manager.get(f"/bff/api/cases/{case_id}/images")
    assert listed.status_code == 200
    assert "X-Amz-" not in listed.text and ":9000" not in listed.text and "/storage/" not in listed.text
    photo = listed.json()["items"][0] if isinstance(listed.json(), dict) else listed.json()[0]
    url = photo["url"]
    assert url == f"/api/v1/files/images/{photo['id']}/original"

    streamed = manager.get(url.replace("/api/v1/", "/bff/api/", 1))
    assert streamed.status_code == 200
    assert streamed.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in streamed.headers["cache-control"]
    assert len(streamed.content) > 0

    ranged = manager.get(url.replace("/api/v1/", "/bff/api/", 1), headers={"Range": "bytes=0-7"})
    assert ranged.status_code == 206
    assert ranged.content == streamed.content[:8]

    # cizí uživatel (bez session) soubor nedostane
    with _client() as anonymous:
        assert anonymous.get(url.replace("/api/v1/", "/bff/api/", 1)).status_code == 401


def test_routes_outside_the_web_allowlist_are_404(manager: httpx.Client) -> None:
    for path in (
        "/bff/api/admin/companies",
        "/bff/api/admin/users",
        "/bff/api/auth/me",
        "/bff/api/auth/refresh",
        "/bff/api/does-not-exist",
        "/bff/api/cases/..%2F..%2Fadmin",
    ):
        assert manager.get(path).status_code == 404, path
    internal = manager.post("/bff/api/internal/security-events", json={"events": []}, headers=_csrf(manager))
    assert internal.status_code == 404


def test_org_users_is_denied_by_core_for_non_company_admins() -> None:
    for credentials in (TECHNICIAN, MANAGER):
        with _client() as client:
            assert _login(client, credentials).status_code == 200
            assert client.get("/bff/api/org/users").status_code == 403, credentials[0]


def test_logout_invalidates_the_cookie() -> None:
    with _client() as client:
        assert _login(client, TECHNICIAN).status_code == 200
        stolen = client.cookies.get(COOKIE)
        assert stolen
        response = client.post("/bff/auth/logout", headers=_csrf(client))
        assert response.status_code == 204
        assert "max-age=0" in response.headers["set-cookie"].lower()
    with _client() as replay:
        replay.cookies.set(COOKIE, stolen)
        assert replay.get("/bff/api/cases").status_code == 401


def test_logout_all_ends_every_session_of_the_user() -> None:
    with _client() as first, _client() as second:
        assert _login(first, TECHNICIAN).status_code == 200
        assert _login(second, TECHNICIAN).status_code == 200
        assert second.get("/bff/api/cases").status_code == 200
        assert first.post("/bff/auth/logout-all", headers=_csrf(first)).status_code == 204
        assert second.get("/bff/api/cases").status_code == 401


def test_proxy_responses_carry_csp(manager: httpx.Client) -> None:
    """Review L1: odpověď z /bff/api má vždy CSP – vlastní CSP core projde, jinak výchozí gateway."""
    response = manager.get("/bff/api/cases")
    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    assert "unsafe" not in csp


def test_sse_stream_with_last_event_id_passes_through(manager: httpx.Client) -> None:
    """QA F-1: SSE přes gateway s Last-Event-ID (core ji přijme, stream se otevře)."""
    case = manager.post("/bff/api/cases", json={"title": f"NC007 sse {uuid.uuid4().hex[:6]}"}, headers=_csrf(manager))
    assert case.status_code == 201, case.text
    url = f"/bff/api/cases/{case.json()['id']}/activity/stream"
    headers = {"Accept": "text/event-stream", "Last-Event-ID": "0"}
    with manager.stream("GET", url, headers=headers, timeout=httpx.Timeout(10.0, read=5.0)) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers.get("x-accel-buffering") == "no"
