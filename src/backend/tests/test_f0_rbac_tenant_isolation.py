"""F0 regression suite: role hierarchy, privilege escalation and tenant isolation.

Covers SECURITY_AUDIT.md SA-01 (manager → superadmin takeover), SA-02 (foreign
client on a case), SA-03 (forged Authorization header vs. login rate limit) and
SA-04 (admin password change without policy or session revocation).

Every scenario goes through the real ASGI app and database; the
role_permissions fixture recreates what migration 0018 seeded on historical
databases, so the checks prove the application no longer trusts that table.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.rbac import is_tenant_operator
from app.models import AuditLog, Client, Project, RolePermission, User
from app.schemas.auth import AuthUserRead
from app.services.auth_service import hash_password

ORG_A = "org_e2e_a"
ORG_B = "org_e2e_b"
PASSWORD = "F0-Initial-Pass-1!"
NEW_PASSWORD = "F0-Rotated-Pass-2!"
WEAK_PASSWORDS = ["a", "short1!", "alllowercase-no-digits"]

# id -> (organization, role, is_superadmin)
_STATIC_USERS = {
    "f0_superadmin": (ORG_A, "superadmin", True),
    "f0_superadmin_2": (ORG_B, "superadmin", True),
    "f0_admin_a": (ORG_A, "admin", False),
    "f0_admin_a2": (ORG_A, "admin", False),
    "f0_admin_b": (ORG_B, "admin", False),
    "f0_manager_a": (ORG_A, "manager", False),
    "f0_technician_a": (ORG_A, "technician", False),
    "f0_technician_b": (ORG_B, "technician", False),
}

# Exactly what 20260326_0018 seeded on every historical installation.
_HISTORICAL_PERMISSIONS = [
    ("superadmin", "admin:read"),
    ("superadmin", "admin:write"),
    ("superadmin", "admin:jobs"),
    ("superadmin", "admin:impersonate"),
    ("manager", "admin:read"),
    ("manager", "admin:write"),
]


def _email(user_id: str) -> str:
    return f"{user_id}@f0.test"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def f0_users(test_tenants, db_session_factory):
    # Function-scoped but idempotent: rows are inserted once and reused.
    async with db_session_factory() as session:
        for user_id, (org, role, flag) in _STATIC_USERS.items():
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
        for role, capability in _HISTORICAL_PERMISSIONS:
            if await session.get(RolePermission, (role, capability)) is None:
                session.add(RolePermission(role=role, capability=capability))
        await session.commit()
    return {user_id: _email(user_id) for user_id in _STATIC_USERS}


async def _login(client: AsyncClient, email: str, password: str = PASSWORD) -> dict:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


async def _token(client: AsyncClient, user_id: str) -> str:
    return (await _login(client, _email(user_id)))["accessToken"]


async def _create_user(db_session_factory, *, org: str, role: str) -> str:
    """Throwaway target so state-changing tests never interfere with each other."""
    user_id = f"f0_tmp_{uuid.uuid4().hex[:10]}"
    async with db_session_factory() as session:
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
    return user_id


async def _db_user(db_session_factory, user_id: str) -> User:
    async with db_session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        return user


async def _login_status(client: AsyncClient, email: str, password: str) -> int:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return response.status_code


# ── Superadmin accounts are untouchable through the administration API ─────────


async def test_manager_cannot_change_superadmin_password(app_client, f0_users, db_session_factory):
    token = await _token(app_client, "f0_manager_a")
    before = (await _db_user(db_session_factory, "f0_superadmin")).password_hash

    reset = await app_client.post(
        "/api/v1/admin/users/f0_superadmin/reset-password",
        json={"password": NEW_PASSWORD},
        headers=_auth(token),
    )
    patch = await app_client.patch(
        "/api/v1/admin/users/f0_superadmin",
        json={"password": NEW_PASSWORD},
        headers=_auth(token),
    )

    assert reset.status_code == 403
    assert patch.status_code == 403
    assert (await _db_user(db_session_factory, "f0_superadmin")).password_hash == before
    assert await _login_status(app_client, f0_users["f0_superadmin"], PASSWORD) == 200


async def test_company_admin_cannot_change_superadmin_password(app_client, f0_users, db_session_factory):
    # f0_superadmin belongs to ORG_A, the admin's own organization.
    token = await _token(app_client, "f0_admin_a")
    before = (await _db_user(db_session_factory, "f0_superadmin")).password_hash

    for response in (
        await app_client.post(
            "/api/v1/admin/users/f0_superadmin/reset-password",
            json={"password": NEW_PASSWORD},
            headers=_auth(token),
        ),
        await app_client.patch(
            "/api/v1/admin/users/f0_superadmin",
            json={"password": NEW_PASSWORD, "isActive": False},
            headers=_auth(token),
        ),
        await app_client.get("/api/v1/admin/users/f0_superadmin", headers=_auth(token)),
    ):
        # Hidden like a missing record: no confirmation the account exists.
        assert response.status_code == 404, response.text

    superadmin = await _db_user(db_session_factory, "f0_superadmin")
    assert superadmin.password_hash == before and superadmin.is_active
    listed = await app_client.get("/api/v1/admin/users", headers=_auth(token))
    assert listed.status_code == 200
    assert "f0_superadmin" not in {item["id"] for item in listed.json()["items"]}


async def test_superadmin_cannot_manage_another_superadmin_via_api(app_client, f0_users, db_session_factory):
    token = await _token(app_client, "f0_superadmin")
    before = (await _db_user(db_session_factory, "f0_superadmin_2")).password_hash

    reset = await app_client.post(
        "/api/v1/admin/users/f0_superadmin_2/reset-password",
        json={"password": NEW_PASSWORD},
        headers=_auth(token),
    )
    demote = await app_client.patch(
        "/api/v1/admin/users/f0_superadmin_2",
        json={"role": "technician"},
        headers=_auth(token),
    )

    assert reset.status_code == 403
    assert demote.status_code == 403
    target = await _db_user(db_session_factory, "f0_superadmin_2")
    assert target.password_hash == before and target.role == "superadmin" and target.is_superadmin


@pytest.mark.parametrize(
    "payload",
    [
        {"role": "superadmin"},
        {"role": "superadmin", "isSuperAdmin": True},
        {"isSuperAdmin": True},
        {"role": "dispatcher"},
    ],
)
@pytest.mark.parametrize("actor", ["f0_admin_a", "f0_superadmin"])
async def test_nobody_can_create_a_superadmin_or_unknown_role(app_client, f0_users, actor, payload):
    token = await _token(app_client, actor)
    email = f"f0_new_{uuid.uuid4().hex[:8]}@f0.test"
    response = await app_client.post(
        "/api/v1/admin/users",
        json={"organizationId": ORG_A, "email": email, "fullName": "X", "password": PASSWORD, **payload},
        headers=_auth(token),
    )
    assert response.status_code == 422, response.text
    assert await _login_status(app_client, email, PASSWORD) == 401


async def test_superadmin_changes_own_password_only_with_reauthentication(app_client, f0_users, db_session_factory):
    user_id = "f0_superadmin_selfservice"
    async with db_session_factory() as session:
        if await session.get(User, user_id) is None:
            session.add(
                User(
                    id=user_id,
                    organization_id=ORG_A,
                    email=_email(user_id),
                    password_hash=hash_password(PASSWORD),
                    full_name="Self service SA",
                    role="superadmin",
                    is_active=True,
                    is_superadmin=True,
                )
            )
            await session.commit()
    login = await _login(app_client, _email(user_id))
    token = login["accessToken"]

    # Not through the administration API, not even for one's own account.
    via_admin_api = await app_client.patch(
        f"/api/v1/admin/users/{user_id}", json={"password": NEW_PASSWORD}, headers=_auth(token)
    )
    assert via_admin_api.status_code == 403

    wrong_current = await app_client.post(
        "/api/v1/auth/change-password",
        json={"currentPassword": "not-the-password-1!", "newPassword": NEW_PASSWORD},
        headers=_auth(token),
    )
    assert wrong_current.status_code == 401

    changed = await app_client.post(
        "/api/v1/auth/change-password",
        json={"currentPassword": PASSWORD, "newPassword": NEW_PASSWORD},
        headers=_auth(token),
    )
    assert changed.status_code == 200, changed.text
    assert (await app_client.get("/api/v1/auth/me", headers=_auth(token))).status_code == 401
    refreshed = await app_client.post("/api/v1/auth/refresh", json={"refreshToken": login["refreshToken"]})
    assert refreshed.status_code == 401
    assert await _login_status(app_client, _email(user_id), PASSWORD) == 401
    assert await _login_status(app_client, _email(user_id), NEW_PASSWORD) == 200


# ── Company admin: own tenant only ─────────────────────────────────────────────


async def test_company_admin_cannot_manage_other_tenants_users(app_client, f0_users, db_session_factory):
    token = await _token(app_client, "f0_admin_a")
    foreign = "f0_technician_b"
    before = await _db_user(db_session_factory, foreign)

    responses = [
        await app_client.get(f"/api/v1/admin/users/{foreign}", headers=_auth(token)),
        await app_client.patch(
            f"/api/v1/admin/users/{foreign}", json={"fullName": "Owned", "isActive": False}, headers=_auth(token)
        ),
        await app_client.post(
            f"/api/v1/admin/users/{foreign}/reset-password", json={"password": NEW_PASSWORD}, headers=_auth(token)
        ),
        await app_client.get("/api/v1/admin/users", params={"org_id": ORG_B}, headers=_auth(token)),
        await app_client.post(
            "/api/v1/admin/users",
            json={
                "organizationId": ORG_B,
                "email": f"f0_x_{uuid.uuid4().hex[:8]}@f0.test",
                "fullName": "X",
                "role": "technician",
                "password": PASSWORD,
            },
            headers=_auth(token),
        ),
        await app_client.get(f"/api/v1/admin/companies/{ORG_B}", headers=_auth(token)),
        await app_client.patch(f"/api/v1/admin/companies/{ORG_B}", json={"name": "Owned"}, headers=_auth(token)),
    ]
    for response in responses:
        assert response.status_code == 404, response.text
        # Nothing about tenant B leaks into the error body.
        assert ORG_B not in response.text and "Tenant B" not in response.text

    after = await _db_user(db_session_factory, foreign)
    assert (after.full_name, after.is_active, after.password_hash) == (
        before.full_name,
        before.is_active,
        before.password_hash,
    )

    own_list = await app_client.get("/api/v1/admin/users", headers=_auth(token))
    assert own_list.status_code == 200
    assert {item["organizationId"] for item in own_list.json()["items"]} == {ORG_A}


async def test_company_admin_creates_user_in_own_company(app_client, f0_users):
    token = await _token(app_client, "f0_admin_a")
    email = f"f0_new_{uuid.uuid4().hex[:8]}@f0.test"
    response = await app_client.post(
        "/api/v1/admin/users",
        json={"organizationId": ORG_A, "email": email, "fullName": "New Tech", "password": PASSWORD},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["organizationId"], body["role"], body["isSuperAdmin"]) == (ORG_A, "technician", False)
    assert await _login_status(app_client, email, PASSWORD) == 200

    manager = await app_client.post(
        "/api/v1/admin/users",
        json={
            "organizationId": ORG_A,
            "email": f"f0_new_{uuid.uuid4().hex[:8]}@f0.test",
            "fullName": "New Manager",
            "role": "manager",
            "password": PASSWORD,
        },
        headers=_auth(token),
    )
    assert manager.status_code == 201, manager.text


async def test_company_admin_cannot_appoint_company_admins(app_client, f0_users, db_session_factory):
    token = await _token(app_client, "f0_admin_a")
    created = await app_client.post(
        "/api/v1/admin/users",
        json={
            "organizationId": ORG_A,
            "email": f"f0_new_{uuid.uuid4().hex[:8]}@f0.test",
            "fullName": "Wannabe admin",
            "role": "admin",
            "password": PASSWORD,
        },
        headers=_auth(token),
    )
    assert created.status_code == 403

    target = await _create_user(db_session_factory, org=ORG_A, role="technician")
    promoted = await app_client.patch(f"/api/v1/admin/users/{target}", json={"role": "admin"}, headers=_auth(token))
    assert promoted.status_code == 403
    assert (await _db_user(db_session_factory, target)).role == "technician"


async def test_superadmin_appoints_company_admin(app_client, f0_users, db_session_factory):
    token = await _token(app_client, "f0_superadmin")
    target = await _create_user(db_session_factory, org=ORG_B, role="manager")
    response = await app_client.patch(f"/api/v1/admin/users/{target}", json={"role": "admin"}, headers=_auth(token))
    assert response.status_code == 200, response.text
    assert (await _db_user(db_session_factory, target)).role == "admin"


async def test_company_admin_cannot_touch_other_company_admins(app_client, f0_users, db_session_factory):
    token = await _token(app_client, "f0_admin_a")
    before = await _db_user(db_session_factory, "f0_admin_a2")
    for response in (
        await app_client.post(
            "/api/v1/admin/users/f0_admin_a2/reset-password", json={"password": NEW_PASSWORD}, headers=_auth(token)
        ),
        await app_client.patch(
            "/api/v1/admin/users/f0_admin_a2", json={"isActive": False}, headers=_auth(token)
        ),
        await app_client.patch(
            "/api/v1/admin/users/f0_admin_a2", json={"role": "technician"}, headers=_auth(token)
        ),
    ):
        assert response.status_code == 403, response.text
    after = await _db_user(db_session_factory, "f0_admin_a2")
    assert (after.password_hash, after.is_active, after.role) == (before.password_hash, before.is_active, before.role)


async def test_company_admin_resets_own_user_password_and_kills_sessions(app_client, f0_users, db_session_factory):
    target = await _create_user(db_session_factory, org=ORG_A, role="technician")
    target_login = await _login(app_client, _email(target))
    admin_token = await _token(app_client, "f0_admin_a")

    response = await app_client.post(
        f"/api/v1/admin/users/{target}/reset-password",
        json={"password": NEW_PASSWORD},
        headers=_auth(admin_token),
    )

    assert response.status_code == 204, response.text
    assert (await app_client.get("/api/v1/auth/me", headers=_auth(target_login["accessToken"]))).status_code == 401
    refreshed = await app_client.post("/api/v1/auth/refresh", json={"refreshToken": target_login["refreshToken"]})
    assert refreshed.status_code == 401
    assert await _login_status(app_client, _email(target), PASSWORD) == 401
    assert await _login_status(app_client, _email(target), NEW_PASSWORD) == 200
    async with db_session_factory() as session:
        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.action == "admin.user.reset_password", AuditLog.resource_id == target
            )
        )
        assert audit is not None and audit.user_id == "f0_admin_a"
        assert NEW_PASSWORD not in str(audit.detail)


async def test_admin_patch_password_enforces_policy_and_kills_sessions(app_client, f0_users, db_session_factory):
    target = await _create_user(db_session_factory, org=ORG_A, role="manager")
    target_login = await _login(app_client, _email(target))
    admin_token = await _token(app_client, "f0_admin_a")

    response = await app_client.patch(
        f"/api/v1/admin/users/{target}", json={"password": NEW_PASSWORD}, headers=_auth(admin_token)
    )

    assert response.status_code == 200, response.text
    assert (await app_client.get("/api/v1/auth/me", headers=_auth(target_login["accessToken"]))).status_code == 401
    refreshed = await app_client.post("/api/v1/auth/refresh", json={"refreshToken": target_login["refreshToken"]})
    assert refreshed.status_code == 401
    assert await _login_status(app_client, _email(target), NEW_PASSWORD) == 200
    async with db_session_factory() as session:
        audit = await session.scalar(
            select(AuditLog).where(AuditLog.action == "admin.user.patch", AuditLog.resource_id == target)
        )
        assert audit is not None
        assert audit.detail["password_changed"] is True
        assert NEW_PASSWORD not in str(audit.detail)


async def test_deactivation_kills_sessions(app_client, f0_users, db_session_factory):
    target = await _create_user(db_session_factory, org=ORG_A, role="technician")
    target_login = await _login(app_client, _email(target))
    admin_token = await _token(app_client, "f0_admin_a")

    response = await app_client.patch(
        f"/api/v1/admin/users/{target}", json={"isActive": False}, headers=_auth(admin_token)
    )

    assert response.status_code == 200, response.text
    assert (await app_client.get("/api/v1/auth/me", headers=_auth(target_login["accessToken"]))).status_code == 401
    refreshed = await app_client.post("/api/v1/auth/refresh", json={"refreshToken": target_login["refreshToken"]})
    assert refreshed.status_code == 401


@pytest.mark.parametrize("weak", WEAK_PASSWORDS)
async def test_weak_passwords_are_rejected_everywhere(app_client, f0_users, db_session_factory, weak):
    target = await _create_user(db_session_factory, org=ORG_A, role="technician")
    before = (await _db_user(db_session_factory, target)).password_hash
    admin_token = await _token(app_client, "f0_admin_a")

    patch = await app_client.patch(f"/api/v1/admin/users/{target}", json={"password": weak}, headers=_auth(admin_token))
    reset = await app_client.post(
        f"/api/v1/admin/users/{target}/reset-password", json={"password": weak}, headers=_auth(admin_token)
    )
    create = await app_client.post(
        "/api/v1/admin/users",
        json={"organizationId": ORG_A, "email": f"f0_w_{uuid.uuid4().hex[:8]}@f0.test", "fullName": "W", "password": weak},
        headers=_auth(admin_token),
    )
    own_token = await _token(app_client, target)
    self_service = await app_client.post(
        "/api/v1/auth/change-password",
        json={"currentPassword": PASSWORD, "newPassword": weak},
        headers=_auth(own_token),
    )

    assert (patch.status_code, reset.status_code, create.status_code, self_service.status_code) == (400, 400, 400, 400)
    assert (await _db_user(db_session_factory, target)).password_hash == before


# ── No self-promotion, no tenant hopping ───────────────────────────────────────


@pytest.mark.parametrize("role", ["admin", "manager"])
async def test_manager_cannot_promote_self(app_client, f0_users, db_session_factory, role):
    token = await _token(app_client, "f0_manager_a")
    response = await app_client.patch(
        "/api/v1/admin/users/f0_manager_a", json={"role": role}, headers=_auth(token)
    )
    superadmin = await app_client.patch(
        "/api/v1/admin/users/f0_manager_a", json={"role": "superadmin"}, headers=_auth(token)
    )
    assert response.status_code == 403
    assert superadmin.status_code in (403, 422)
    user = await _db_user(db_session_factory, "f0_manager_a")
    assert (user.role, user.is_superadmin) == ("manager", False)


async def test_company_admin_cannot_change_own_role_activation_or_password_via_admin_api(
    app_client, f0_users, db_session_factory
):
    token = await _token(app_client, "f0_admin_a")
    before = await _db_user(db_session_factory, "f0_admin_a")
    for payload in ({"role": "manager"}, {"isActive": False}, {"password": NEW_PASSWORD}):
        response = await app_client.patch("/api/v1/admin/users/f0_admin_a", json=payload, headers=_auth(token))
        assert response.status_code == 403, payload
    after = await _db_user(db_session_factory, "f0_admin_a")
    assert (after.role, after.is_active, after.password_hash) == (before.role, before.is_active, before.password_hash)


@pytest.mark.parametrize("actor", ["f0_technician_a", "f0_manager_a", "f0_admin_a"])
@pytest.mark.parametrize("field", ["organizationId", "organization_id", "tenant_id", "isSuperAdmin"])
async def test_nobody_can_move_a_user_to_another_tenant(app_client, f0_users, db_session_factory, actor, field):
    token = await _token(app_client, actor)
    value = True if field == "isSuperAdmin" else ORG_B
    response = await app_client.patch(
        f"/api/v1/admin/users/{actor}", json={"fullName": "Moved", field: value}, headers=_auth(token)
    )
    assert response.status_code in (403, 422), response.text
    user = await _db_user(db_session_factory, actor)
    assert (user.organization_id, user.is_superadmin, user.full_name) == (ORG_A, False, actor)

    if actor == "f0_admin_a":
        target = await _create_user(db_session_factory, org=ORG_A, role="technician")
        moved = await app_client.patch(
            f"/api/v1/admin/users/{target}", json={field: value}, headers=_auth(token)
        )
        assert moved.status_code == 422, moved.text
        moved_user = await _db_user(db_session_factory, target)
        assert (moved_user.organization_id, moved_user.is_superadmin) == (ORG_A, False)


# ── Direct API calls: system administration is superadmin-only ─────────────────

_SYSTEM_ENDPOINTS = [
    ("get", "/api/v1/admin/companies", None),
    ("post", "/api/v1/admin/companies", {"name": "Evil Corp"}),
    ("get", "/api/v1/admin/jobs", None),
    ("get", "/api/v1/admin/jobs/job_does_not_matter", None),
    ("post", "/api/v1/admin/jobs/job_does_not_matter/retry", None),
    ("post", "/api/v1/admin/jobs/job_does_not_matter/reprocess", None),
    ("get", "/api/v1/admin/logs", None),
    ("get", "/api/v1/admin/audit", None),
    ("post", "/api/v1/admin/impersonate/f0_technician_b", None),
    ("get", "/api/v1/health/internal", None),
]

_USER_ADMIN_ENDPOINTS = [
    ("get", "/api/v1/admin/users", None),
    ("get", "/api/v1/admin/users/f0_technician_a", None),
    ("post", "/api/v1/admin/users", {"organizationId": ORG_A, "email": "f0_never@f0.test", "fullName": "N", "password": PASSWORD}),
    ("patch", "/api/v1/admin/users/f0_technician_a", {"fullName": "Hijacked"}),
    ("post", "/api/v1/admin/users/f0_technician_a/reset-password", {"password": NEW_PASSWORD}),
    ("get", f"/api/v1/admin/companies/{ORG_A}", None),
    ("patch", f"/api/v1/admin/companies/{ORG_A}", {"name": "Hijacked"}),
]


async def _call(client: AsyncClient, method: str, path: str, body, token: str):
    kwargs = {"headers": _auth(token)}
    if body is not None:
        kwargs["json"] = body
    return await getattr(client, method)(path, **kwargs)


@pytest.mark.parametrize("method,path,body", _SYSTEM_ENDPOINTS)
@pytest.mark.parametrize("actor", ["f0_technician_a", "f0_manager_a", "f0_admin_a"])
async def test_system_endpoints_reject_every_tenant_role(app_client, f0_users, actor, method, path, body):
    # f0_users also seeds the historical manager → admin:write rows: they must not matter.
    token = await _token(app_client, actor)
    response = await _call(app_client, method, path, body, token)
    assert response.status_code == 403, f"{actor} {method.upper()} {path} -> {response.status_code}"


@pytest.mark.parametrize("method,path,body", _USER_ADMIN_ENDPOINTS)
@pytest.mark.parametrize("actor", ["f0_technician_a", "f0_manager_a"])
async def test_user_administration_rejects_non_admins(app_client, f0_users, db_session_factory, actor, method, path, body):
    token = await _token(app_client, actor)
    response = await _call(app_client, method, path, body, token)
    assert response.status_code == 403, f"{actor} {method.upper()} {path} -> {response.status_code}"
    assert (await _db_user(db_session_factory, "f0_technician_a")).full_name == "f0_technician_a"


async def test_role_string_alone_never_grants_superadmin_powers():
    forged = AuthUserRead(
        id="x", email="x@f0.test", fullName="X", role="superadmin", isActive=True, organizationId=ORG_A, isSuperAdmin=False
    )
    assert is_tenant_operator(forged) is False


async def test_database_rejects_superadmin_role_without_flag(db_session_factory, test_tenants):
    from sqlalchemy.exc import IntegrityError

    async with db_session_factory() as session:
        session.add(
            User(
                id=f"f0_bad_{uuid.uuid4().hex[:8]}",
                organization_id=ORG_A,
                email=f"f0_bad_{uuid.uuid4().hex[:8]}@f0.test",
                password_hash="x",
                full_name="Bad",
                role="superadmin",
                is_active=True,
                is_superadmin=False,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


# ── Clients belong to the case's tenant ───────────────────────────────────────


@pytest_asyncio.fixture
async def foreign_client_id(db_session_factory, test_tenants):
    client_id = f"cli_f0_{uuid.uuid4().hex[:8]}"
    async with db_session_factory() as session:
        session.add(
            Client(
                id=client_id,
                organization_id=ORG_B,
                full_name="Tenant B Secret Client",
                email="secret-client@tenant-b.test",
                phone="+420 777 000 000",
            )
        )
        await session.commit()
    return client_id


async def test_case_cannot_be_linked_to_another_tenants_client(
    app_client, token_a, case_a_id, foreign_client_id, db_session_factory
):
    response = await app_client.patch(
        f"/api/v1/cases/{case_a_id}", json={"clientId": foreign_client_id}, headers=_auth(token_a)
    )
    assert response.status_code == 400, response.text
    assert "Tenant B Secret Client" not in response.text

    detail = await app_client.get(f"/api/v1/cases/{case_a_id}", headers=_auth(token_a))
    assert detail.status_code == 200
    assert "secret-client@tenant-b.test" not in detail.text
    async with db_session_factory() as session:
        project = await session.get(Project, case_a_id)
        assert project is not None and project.client_id != foreign_client_id

    created = await app_client.post(
        "/api/v1/cases", json={"title": "F0 foreign client", "clientId": foreign_client_id}, headers=_auth(token_a)
    )
    assert created.status_code == 400


async def test_case_can_be_linked_to_own_client(app_client, token_a, case_a_id, db_session_factory):
    client_id = f"cli_f0_{uuid.uuid4().hex[:8]}"
    async with db_session_factory() as session:
        session.add(Client(id=client_id, organization_id=ORG_A, full_name="Tenant A client"))
        await session.commit()
    response = await app_client.patch(
        f"/api/v1/cases/{case_a_id}", json={"clientId": client_id}, headers=_auth(token_a)
    )
    assert response.status_code == 200, response.text


async def test_offer_request_cannot_reference_another_tenants_client(app_client, token_a, foreign_client_id):
    response = await app_client.post(
        "/api/v1/offer-requests",
        json={
            "idempotency_key": f"f0-{uuid.uuid4().hex}",
            "work_type_code": "roof_repair",
            "title": "F0 foreign client offer",
            "client_id": foreign_client_id,
        },
        headers=_auth(token_a),
    )
    assert response.status_code == 400, response.text


# ── Company admin keeps manager-level case work in own tenant ─────────────────


async def test_company_admin_can_operate_own_cases_but_not_foreign(app_client, f0_users, case_b_id):
    token = await _token(app_client, "f0_admin_a")
    created = await app_client.post("/api/v1/cases", json={"title": "F0 admin case"}, headers=_auth(token))
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    patched = await app_client.patch(f"/api/v1/cases/{case_id}", json={"title": "Renamed"}, headers=_auth(token))
    assert patched.status_code == 200, patched.text

    foreign = await app_client.patch(f"/api/v1/cases/{case_b_id}", json={"title": "Owned"}, headers=_auth(token))
    assert foreign.status_code == 404


# ── Forged Authorization header vs. login rate limiting (SA-03) ──────────────


def _forged_token(org: str) -> str:
    import base64
    import json

    def segment(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    return f"{segment({'alg': 'HS256'})}.{segment({'org': org, 'sub': org})}.forged"


def test_unauthenticated_auth_routes_are_keyed_by_client_ip_only():
    from app.api.routes import auth

    # Read through the auth module: other tests reload app.core.limiter, and the
    # limits live on the instance the routes were decorated with.
    for name in ("login", "refresh", "logout", "forgot_password", "reset_password"):
        limits = auth.limiter._route_limits[f"app.api.routes.auth.{name}"]
        assert limits, name
        assert all(limit.key_func.__name__ == "client_ip_rate_limit_key" for limit in limits), name


async def test_forged_authorization_header_cannot_escape_ip_rate_limit():
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.extension import _rate_limit_exceeded_handler

    from app.core.limiter import client_ip_rate_limit_key

    test_limiter = Limiter(key_func=client_ip_rate_limit_key)
    app = FastAPI()
    app.state.limiter = test_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.post("/login")
    @test_limiter.limit("3/minute", key_func=client_ip_rate_limit_key)
    async def login(request: Request) -> dict:
        return {"ok": True}

    statuses = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for attempt in range(6):
            response = await client.post(
                "/login", headers={"Authorization": f"Bearer {_forged_token(f'org_{attempt}')}"}
            )
            statuses.append(response.status_code)
    assert statuses == [200, 200, 200, 429, 429, 429]
