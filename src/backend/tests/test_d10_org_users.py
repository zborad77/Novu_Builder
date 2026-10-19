"""D-10: a company admin manages the users of their own company (/org/users).

Allowed: list, detail, create (manager/technician), rename, change role between
manager and technician, deactivate/reactivate, reset password – all inside the
admin's company. Refused: other companies (404), superadmins (invisible),
other company admins and one's own account (403), assigning admin/superadmin,
non-admins and superadmins (403). The system administration API stays in the
admin zone only; the gateway exposes just the company operations.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.platform.config import get_settings
from app.modules.audit.models import AuditLog
from app.modules.identity.models import User
from app.modules.identity.auth_service import hash_password

ORG_A = "org_e2e_a"
ORG_B = "org_e2e_b"
PASSWORD = "D10-Initial-Pass-1!"
NEW_PASSWORD = "D10-Rotated-Pass-2!"

_STATIC = {
    "d10_admin_a": (ORG_A, "admin", False),
    "d10_admin_a2": (ORG_A, "admin", False),
    "d10_admin_b": (ORG_B, "admin", False),
    "d10_manager_a": (ORG_A, "manager", False),
    "d10_tech_b": (ORG_B, "technician", False),
    "d10_superadmin_a": (ORG_A, "superadmin", True),
}


def _email(user_id: str) -> str:
    return f"{user_id}@d10.test"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def d10_users(test_tenants, db_session_factory):
    async with db_session_factory() as session:
        for user_id, (org, role, flag) in _STATIC.items():
            if await session.get(User, user_id) is None:
                session.add(User(
                    id=user_id, organization_id=org, email=_email(user_id),
                    password_hash=hash_password(PASSWORD), full_name=user_id, role=role,
                    is_active=True, is_superadmin=flag,
                ))
        await session.commit()


@pytest_asyncio.fixture
async def fresh_user(test_tenants, db_session_factory):
    """A disposable technician of company A (tests mutate it)."""
    user_id = f"d10_tmp_{uuid.uuid4().hex[:10]}"
    async with db_session_factory() as session:
        session.add(User(
            id=user_id, organization_id=ORG_A, email=_email(user_id), password_hash=hash_password(PASSWORD),
            full_name="Temp", role="technician", is_active=True, is_superadmin=False,
        ))
        await session.commit()
    return user_id


async def _token(client, user_id: str, password: str = PASSWORD) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": _email(user_id), "password": password})
    assert response.status_code == 200, response.text
    return response.json()["accessToken"]


# ── Allowed operations ───────────────────────────────────────────────────────


async def test_admin_lists_only_users_of_their_company(app_client, d10_users):
    token = await _token(app_client, "d10_admin_a")
    response = await app_client.get("/api/v1/org/users", headers=_auth(token))
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items and {u["organizationId"] for u in items} == {ORG_A}
    assert not any(u["isSuperAdmin"] for u in items)
    assert "d10_superadmin_a" not in {u["id"] for u in items}


async def test_admin_creates_a_user_in_their_own_company(app_client, d10_users, db_session_factory):
    token = await _token(app_client, "d10_admin_a")
    email = f"new_{uuid.uuid4().hex[:8]}@d10.test"
    response = await app_client.post(
        "/api/v1/org/users",
        json={"email": email, "fullName": "Nový technik", "role": "technician", "password": NEW_PASSWORD},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    assert response.json()["organizationId"] == ORG_A
    async with db_session_factory() as session:
        audit = (await session.execute(
            select(AuditLog).where(AuditLog.action == "org.user.create", AuditLog.resource_id == response.json()["id"])
        )).scalar_one()
    assert audit.user_id == "d10_admin_a"
    assert (await app_client.post("/api/v1/auth/login", json={"email": email, "password": NEW_PASSWORD})).status_code == 200


async def test_company_cannot_be_chosen_by_the_request(app_client, d10_users):
    token = await _token(app_client, "d10_admin_a")
    response = await app_client.post(
        "/api/v1/org/users",
        json={"email": "x@d10.test", "fullName": "X", "role": "technician", "password": NEW_PASSWORD,
              "organizationId": ORG_B},
        headers=_auth(token),
    )
    assert response.status_code == 422


async def test_admin_changes_role_between_manager_and_technician(app_client, d10_users, fresh_user):
    token = await _token(app_client, "d10_admin_a")
    response = await app_client.patch(f"/api/v1/org/users/{fresh_user}", json={"role": "manager", "fullName": "Mgr"},
                                      headers=_auth(token))
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "manager"


async def test_deactivation_revokes_the_users_sessions(app_client, d10_users, fresh_user):
    user_token = await _token(app_client, fresh_user)
    admin_token = await _token(app_client, "d10_admin_a")
    response = await app_client.patch(f"/api/v1/org/users/{fresh_user}", json={"isActive": False}, headers=_auth(admin_token))
    assert response.status_code == 200
    assert (await app_client.get("/api/v1/auth/me", headers=_auth(user_token))).status_code == 401
    login = await app_client.post("/api/v1/auth/login", json={"email": _email(fresh_user), "password": PASSWORD})
    assert login.status_code == 401
    # Reactivation lets the user in again.
    assert (await app_client.patch(f"/api/v1/org/users/{fresh_user}", json={"isActive": True},
                                   headers=_auth(admin_token))).status_code == 200
    assert (await app_client.post("/api/v1/auth/login",
                                  json={"email": _email(fresh_user), "password": PASSWORD})).status_code == 200


async def test_password_reset_replaces_the_password_and_revokes_sessions(app_client, d10_users, fresh_user):
    user_token = await _token(app_client, fresh_user)
    admin_token = await _token(app_client, "d10_admin_a")
    response = await app_client.post(f"/api/v1/org/users/{fresh_user}/reset-password",
                                     json={"password": NEW_PASSWORD}, headers=_auth(admin_token))
    assert response.status_code == 204, response.text
    assert (await app_client.get("/api/v1/auth/me", headers=_auth(user_token))).status_code == 401
    assert (await app_client.post("/api/v1/auth/login",
                                  json={"email": _email(fresh_user), "password": PASSWORD})).status_code == 401
    await _token(app_client, fresh_user, NEW_PASSWORD)


async def test_weak_password_is_refused(app_client, d10_users, fresh_user):
    token = await _token(app_client, "d10_admin_a")
    response = await app_client.post(f"/api/v1/org/users/{fresh_user}/reset-password", json={"password": "short1!"},
                                     headers=_auth(token))
    assert response.status_code == 400


# ── Refused operations ───────────────────────────────────────────────────────


@pytest.mark.parametrize("target", ["d10_tech_b", "d10_admin_b", "d10_superadmin_a", "missing-user"])
async def test_other_companies_and_superadmins_are_invisible(app_client, d10_users, target):
    token = await _token(app_client, "d10_admin_a")
    for method, path, body in (
        ("GET", f"/api/v1/org/users/{target}", None),
        ("PATCH", f"/api/v1/org/users/{target}", {"isActive": False}),
        ("POST", f"/api/v1/org/users/{target}/reset-password", {"password": NEW_PASSWORD}),
    ):
        response = await app_client.request(method, path, json=body, headers=_auth(token))
        assert response.status_code == 404, (method, path, response.text)


@pytest.mark.parametrize(
    "target, payload",
    [
        ("d10_admin_a2", {"isActive": False}),
        ("d10_admin_a2", {"role": "technician"}),
        ("d10_admin_a", {"role": "manager"}),
        ("d10_admin_a", {"isActive": False}),
    ],
)
async def test_other_company_admins_and_own_account_cannot_be_changed(app_client, d10_users, target, payload):
    token = await _token(app_client, "d10_admin_a")
    response = await app_client.patch(f"/api/v1/org/users/{target}", json=payload, headers=_auth(token))
    assert response.status_code == 403


async def test_other_admins_password_cannot_be_reset(app_client, d10_users):
    token = await _token(app_client, "d10_admin_a")
    response = await app_client.post("/api/v1/org/users/d10_admin_a2/reset-password", json={"password": NEW_PASSWORD},
                                     headers=_auth(token))
    assert response.status_code == 403


@pytest.mark.parametrize("role", ["admin", "superadmin"])
async def test_admin_and_superadmin_roles_cannot_be_assigned(app_client, d10_users, fresh_user, role):
    token = await _token(app_client, "d10_admin_a")
    created = await app_client.post(
        "/api/v1/org/users",
        json={"email": f"r_{uuid.uuid4().hex[:8]}@d10.test", "fullName": "R", "role": role, "password": NEW_PASSWORD},
        headers=_auth(token),
    )
    patched = await app_client.patch(f"/api/v1/org/users/{fresh_user}", json={"role": role}, headers=_auth(token))
    # "superadmin" is not even a valid company role (422); "admin" is a company role it may not hand out (403).
    expected = 403 if role == "admin" else 422
    assert created.status_code == expected
    assert patched.status_code == expected


@pytest.mark.parametrize("actor", ["d10_manager_a", "d10_superadmin_a"])
async def test_only_company_admins_may_use_the_api(app_client, d10_users, actor):
    token = await _token(app_client, actor)
    assert (await app_client.get("/api/v1/org/users", headers=_auth(token))).status_code == 403


# ── Zones ────────────────────────────────────────────────────────────────────


async def test_gateway_zone_offers_company_operations_but_not_the_admin_api(app_client, d10_users, monkeypatch):
    monkeypatch.setattr(get_settings(), "nc_zone", "gateway")
    token = await _token(app_client, "d10_admin_a")
    assert (await app_client.get("/api/v1/org/users", headers=_auth(token))).status_code == 200
    assert (await app_client.get("/api/v1/admin/users", headers=_auth(token))).status_code == 404
    assert (await app_client.get("/api/v1/admin/companies", headers=_auth(token))).status_code == 404


async def test_admin_zone_does_not_serve_company_user_administration(app_client, d10_users, monkeypatch):
    monkeypatch.setattr(get_settings(), "nc_zone", "admin")
    token = await _token(app_client, "d10_admin_a")
    assert (await app_client.get("/api/v1/org/users", headers=_auth(token))).status_code == 404
