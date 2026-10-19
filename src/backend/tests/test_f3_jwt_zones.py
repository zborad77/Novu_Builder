"""F3.3: JWT tokens are bound to the zone that issued them; superadmins only in admin.

The zone is switched through process configuration (``nc_zone``), exactly as a
separate systemd instance would run, never through anything in the request.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
import pytest_asyncio
from pydantic import ValidationError

from app.models import User
from app.services.auth_service import hash_password

ORG_A = "org_e2e_a"
PASSWORD = "F3-Zone-Pass-1!"
USERS = {
    "f3_manager": ("manager", False),
    "f3_superadmin": ("superadmin", True),
}


def _email(user_id: str) -> str:
    return f"{user_id}@f3.test"


@pytest_asyncio.fixture
async def f3_users(test_tenants, db_session_factory):
    async with db_session_factory() as session:
        for user_id, (role, flag) in USERS.items():
            if await session.get(User, user_id) is None:
                session.add(
                    User(
                        id=user_id,
                        organization_id=ORG_A,
                        email=_email(user_id),
                        password_hash=hash_password(PASSWORD),
                        full_name=user_id,
                        role=role,
                        is_active=True,
                        is_superadmin=flag,
                    )
                )
        await session.commit()


@pytest.fixture
def zone(monkeypatch):
    from app.platform.config import get_settings

    def switch(name: str) -> None:
        monkeypatch.setattr(get_settings(), "nc_zone", name)

    return switch


async def _login(client, user_id: str):
    return await client.post("/api/v1/auth/login", json={"email": _email(user_id), "password": PASSWORD})


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _claims(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


@pytest.mark.parametrize(
    "zone_name, audience",
    [("gateway", "nc-web"), ("desktop", "nc-desktop"), ("admin", "nc-admin")],
)
async def test_tokens_carry_issuer_zone_audience_and_issue_time(app_client, f3_users, zone, zone_name, audience):
    zone(zone_name)
    response = await _login(app_client, "f3_manager")
    assert response.status_code == 200, response.text
    for token in (response.json()["accessToken"], response.json()["refreshToken"]):
        claims = _claims(token)
        assert claims["iss"] == "novuconstruct-core"
        assert claims["aud"] == audience
        assert isinstance(claims["iat"], int) and claims["iat"] <= claims["exp"]


@pytest.mark.parametrize("issued_in, used_in", [("desktop", "gateway"), ("gateway", "desktop"), ("desktop", "admin")])
async def test_token_from_another_zone_is_rejected(app_client, f3_users, zone, issued_in, used_in):
    zone(issued_in)
    tokens = (await _login(app_client, "f3_manager")).json()
    zone(used_in)
    assert (await app_client.get("/api/v1/auth/me", headers=_auth(tokens["accessToken"]))).status_code == 401
    refreshed = await app_client.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert refreshed.status_code == 401
    zone(issued_in)
    assert (await app_client.get("/api/v1/auth/me", headers=_auth(tokens["accessToken"]))).status_code == 200


@pytest.mark.parametrize("zone_name", ["gateway", "desktop"])
async def test_superadmin_cannot_authenticate_outside_admin_zone(app_client, f3_users, zone, zone_name):
    zone(zone_name)
    response = await _login(app_client, "f3_superadmin")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials."  # same answer as a wrong password


async def test_superadmin_authenticates_in_admin_zone_only(app_client, f3_users, zone):
    zone("admin")
    tokens = (await _login(app_client, "f3_superadmin")).json()
    assert (await app_client.get("/api/v1/admin/users", headers=_auth(tokens["accessToken"]))).status_code == 200
    zone("desktop")
    assert (await app_client.get("/api/v1/auth/me", headers=_auth(tokens["accessToken"]))).status_code == 401


def _forge(**overrides) -> str:
    from app.platform.config import get_settings

    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": "f3_manager",
        "jti": "f3" + "0" * 30,
        "type": "access",
        "exp": now + timedelta(minutes=5),
        "iat": now,
        "iss": settings.jwt_issuer,
        "aud": "nc-desktop",
        "ver": 0,
    }
    secret = overrides.pop("_secret", settings.jwt_secret)
    algorithm = overrides.pop("_algorithm", settings.jwt_algorithm)
    for key, value in overrides.items():
        if value is None:
            payload.pop(key, None)
        else:
            payload[key] = value
    return jwt.encode(payload, secret, algorithm=algorithm)


@pytest.mark.parametrize(
    "token_overrides",
    [
        {"iss": "someone-else"},
        {"iss": None},
        {"aud": "nc-admin"},
        {"aud": ["nc-web", "nc-admin"]},
        {"aud": None},
        {"iat": None},
        {"exp": datetime(2020, 1, 1, tzinfo=UTC)},
        {"_secret": "x" * 40},
        {"_algorithm": "HS512"},
    ],
)
async def test_tokens_failing_any_required_check_are_rejected(app_client, f3_users, zone, token_overrides):
    zone("desktop")
    token = _forge(**dict(token_overrides))
    assert (await app_client.get("/api/v1/auth/me", headers=_auth(token))).status_code == 401


async def test_unsigned_token_is_rejected(app_client, f3_users, zone):
    zone("desktop")
    token = jwt.encode(_claims(_forge()), key=None, algorithm="none")
    assert (await app_client.get("/api/v1/auth/me", headers=_auth(token))).status_code == 401


async def test_impersonation_token_targets_the_web_gateway_only(app_client, f3_users, zone):
    zone("admin")
    superadmin = (await _login(app_client, "f3_superadmin")).json()["accessToken"]
    response = await app_client.post("/api/v1/admin/impersonate/f3_manager", headers=_auth(superadmin))
    assert response.status_code == 200, response.text
    token = response.json()["accessToken"]
    assert _claims(token)["aud"] == "nc-web"
    for other in ("admin", "desktop"):
        zone(other)
        assert (await app_client.get("/api/v1/auth/me", headers=_auth(token))).status_code == 401


# ── Development vs production zone rules ──────────────────────────────────────


def test_unknown_zone_is_rejected(monkeypatch):
    from app.platform.config import Settings

    monkeypatch.setenv("NC_ZONE", "public")
    with pytest.raises(ValidationError, match="NC_ZONE"):
        Settings()


def test_dev_zone_is_refused_outside_development(monkeypatch):
    from app.platform.config import Settings
    from tests.test_config_production_hardening import _set_valid_prod_env

    _set_valid_prod_env(monkeypatch)
    monkeypatch.setenv("NC_ZONE", "dev")
    with pytest.raises(ValidationError, match="NC_ZONE=dev"):
        Settings()


def test_insecure_jwt_algorithm_is_refused(monkeypatch):
    from app.platform.config import Settings

    monkeypatch.setenv("JWT_ALGORITHM", "none")
    with pytest.raises(ValidationError, match="JWT_ALGORITHM"):
        Settings()


async def test_api_refuses_to_start_without_a_production_zone(monkeypatch):
    from fastapi import FastAPI

    import app.main as main
    from app.platform.config import Settings
    from tests.test_config_production_hardening import _set_valid_prod_env

    _set_valid_prod_env(monkeypatch)
    monkeypatch.delenv("NC_ZONE", raising=False)
    strict = Settings()
    assert strict.effective_nc_zone == ""
    monkeypatch.setattr(main, "get_settings", lambda: strict)
    with pytest.raises(RuntimeError, match="NC_ZONE"):
        async with main.lifespan(FastAPI()):
            pass


def test_development_defaults_to_dev_zone(monkeypatch):
    from app.platform.config import Settings

    monkeypatch.delenv("NC_ZONE", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    assert Settings().effective_nc_zone == "dev"
