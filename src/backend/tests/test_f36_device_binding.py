"""F3.6: device ↔ company binding in the desktop zone (NC_DEVICE_BINDING).

Prepared now, activated with enrollment in F7.4. The device is identified by its
WireGuard address (the client address after TrustedProxyMiddleware); the test
client connects from 127.0.0.1, which plays the WG address of the device.
"""

from __future__ import annotations

import json

import pytest

from app.platform.config import get_settings
from app.core.device_binding import DeviceRegistryError, decide, parse_registry

LOGIN_A = {"email": "manager_a@test.local", "password": "TestPassA1!"}
ORG_A = "org_e2e_a"
ORG_B = "org_e2e_b"
DEVICE_IP = "127.0.0.1"


def _registry(tmp_path, organization_id: str, *, revoked: bool = False, address: str = DEVICE_IP) -> str:
    path = tmp_path / "devices.json"
    path.write_text(
        json.dumps({"version": 1, "devices": [
            {"deviceId": "dev-01", "wgAddress": address, "organizationId": organization_id, "revoked": revoked}
        ]}),
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def enforce(monkeypatch):
    settings = get_settings()

    def apply(registry_file: str, zone: str = "desktop") -> None:
        monkeypatch.setattr(settings, "nc_zone", zone)
        monkeypatch.setattr(settings, "nc_device_binding", "enforce")
        monkeypatch.setattr(settings, "nc_device_registry_file", registry_file)

    return apply


# ── Decision ─────────────────────────────────────────────────────────────────


def test_decisions():
    devices = parse_registry({"version": 1, "devices": [
        {"deviceId": "a", "wgAddress": "10.50.16.10", "organizationId": ORG_A, "revoked": False},
        {"deviceId": "r", "wgAddress": "10.50.16.11", "organizationId": ORG_A, "revoked": True},
    ]})
    assert decide(devices, "10.50.16.10", ORG_A) == "allow"
    assert decide(devices, "10.50.16.10", ORG_B) == "organization_mismatch"
    assert decide(devices, "10.50.16.10", None) == "organization_mismatch"
    assert decide(devices, "10.50.16.11", ORG_A) == "revoked_device"
    assert decide(devices, "10.50.16.12", ORG_A) == "unknown_device"
    assert decide(devices, None, ORG_A) == "unknown_device"
    assert decide(None, "10.50.16.10", ORG_A) == "registry_unavailable"


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"version": 2, "devices": []},
        {"version": 1, "devices": [{"deviceId": "a", "wgAddress": "nope", "organizationId": ORG_A}]},
        {"version": 1, "devices": [{"deviceId": "a", "wgAddress": "10.0.0.1", "organizationId": ""}]},
        {"version": 1, "devices": [{"deviceId": "a", "wgAddress": "10.0.0.1", "organizationId": ORG_A, "revoked": "no"}]},
        {"version": 1, "devices": [
            {"deviceId": "a", "wgAddress": "10.0.0.1", "organizationId": ORG_A},
            {"deviceId": "b", "wgAddress": "10.0.0.1", "organizationId": ORG_B},
        ]},
    ],
)
def test_malformed_registry_is_rejected(data):
    with pytest.raises(DeviceRegistryError):
        parse_registry(data)


# ── Configuration ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "update, message",
    [
        ({"nc_device_binding": "maybe"}, "must be 'off' or 'enforce'"),
        ({"nc_device_binding": "enforce", "nc_zone": "gateway", "nc_device_registry_file": "x"}, "desktop zone"),
        ({"nc_device_binding": "enforce", "nc_zone": "desktop", "nc_device_registry_file": ""}, "NC_DEVICE_REGISTRY_FILE"),
    ],
)
def test_configuration_is_validated(update, message):
    settings = get_settings().model_copy(update=update)
    with pytest.raises(ValueError, match=message):
        settings._check_network_zone()


# ── Through the application ──────────────────────────────────────────────────


async def test_off_by_default_changes_nothing(app_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "nc_zone", "desktop")
    assert get_settings().nc_device_binding == "off"
    assert (await app_client.post("/api/v1/auth/login", json=LOGIN_A)).status_code == 200


async def test_device_of_the_users_company_is_allowed(app_client, enforce, tmp_path):
    enforce(_registry(tmp_path, ORG_A))
    response = await app_client.post("/api/v1/auth/login", json=LOGIN_A)
    assert response.status_code == 200, response.text
    token = response.json()["accessToken"]
    assert (await app_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})).status_code == 200


async def test_user_of_another_company_is_refused_on_this_device(app_client, enforce, tmp_path, monkeypatch):
    # User of company A on a device enrolled for company B (plan F7.4: "403").
    enforce(_registry(tmp_path, ORG_B))
    response = await app_client.post("/api/v1/auth/login", json=LOGIN_A)
    assert response.status_code == 403
    assert "accessToken" not in response.text


async def test_existing_token_stops_working_on_a_foreign_device(app_client, enforce, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "nc_zone", "desktop")
    token = (await app_client.post("/api/v1/auth/login", json=LOGIN_A)).json()["accessToken"]
    enforce(_registry(tmp_path, ORG_B))
    assert (await app_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})).status_code == 403


async def test_tokens_issued_before_refusal_are_revoked(app_client, enforce, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "nc_zone", "desktop")
    refresh = (await app_client.post("/api/v1/auth/login", json=LOGIN_A)).json()["refreshToken"]
    enforce(_registry(tmp_path, ORG_B))
    assert (await app_client.post("/api/v1/auth/refresh", json={"refreshToken": refresh})).status_code == 403


@pytest.mark.parametrize("variant", ["revoked", "unknown", "missing_file", "unreadable_file"])
async def test_revoked_unknown_or_unavailable_registry_fails_closed(app_client, enforce, tmp_path, variant):
    if variant == "revoked":
        path = _registry(tmp_path, ORG_A, revoked=True)
    elif variant == "unknown":
        path = _registry(tmp_path, ORG_A, address="10.50.16.200")
    elif variant == "missing_file":
        path = str(tmp_path / "absent.json")
    else:
        path = str(tmp_path / "broken.json")
        (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    enforce(path)
    assert (await app_client.post("/api/v1/auth/login", json=LOGIN_A)).status_code == 403
