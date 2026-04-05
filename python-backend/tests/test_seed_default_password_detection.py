from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.db.bootstrap import audit_seed_default_passwords
from app.models import Organization, User
from app.services.auth_service import hash_password
from app.main import verify_seed_credentials_on_startup


async def _create_user(
    db_session,
    *,
    user_id: str,
    organization_id: str,
    email: str,
    password: str,
    role: str = "manager",
    is_active: bool = True,
) -> User:
    organization = await db_session.get(Organization, organization_id)
    if organization is None:
        db_session.add(
            Organization(
                id=organization_id,
                name=f"Org {organization_id}",
                ico="",
                email=None,
                phone=None,
                default_currency="CZK",
            )
        )

    user = await db_session.get(User, user_id)
    if user is None:
        user = User(
            id=user_id,
            organization_id=organization_id,
            email=email,
            password_hash=hash_password(password),
            full_name=f"Seed user {user_id}",
            role=role,
            is_active=is_active,
            is_superadmin=role == "superadmin",
        )
        db_session.add(user)
    else:
        user.organization_id = organization_id
        user.email = email
        user.password_hash = hash_password(password)
        user.full_name = f"Seed user {user_id}"
        user.role = role
        user.is_active = is_active
        user.is_superadmin = role == "superadmin"

    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_seed_default_password_check_is_silent_when_monitored_account_does_not_exist(db_session):
    with (
        patch("app.db.bootstrap.logger.critical") as critical_log,
        patch("app.db.bootstrap.logger.warning") as warning_log,
    ):
        findings = await audit_seed_default_passwords(
            db_session,
            app_env="production",
            strict_environment=True,
        )

    assert findings == []
    critical_log.assert_not_called()
    warning_log.assert_not_called()


@pytest.mark.asyncio
async def test_seed_default_password_check_is_silent_when_password_was_rotated(db_session):
    await _create_user(
        db_session,
        user_id="usr_novu_admin",
        organization_id="org_seed_prod",
        email="admin@novu.cz",
        password="StrongRotatedPass!9",
        role="superadmin",
    )

    with patch("app.db.bootstrap.logger.critical") as critical_log:
        findings = await audit_seed_default_passwords(
            db_session,
            app_env="production",
            strict_environment=True,
        )

    assert findings == []
    critical_log.assert_not_called()


@pytest.mark.asyncio
async def test_seed_default_password_check_logs_critical_for_active_default_seed_account(db_session):
    await _create_user(
        db_session,
        user_id="usr_novu_admin",
        organization_id="org_novu",
        email="admin@novu.cz",
        password="NovuAdmin2024!",
        role="superadmin",
    )

    with patch("app.db.bootstrap.logger.critical") as critical_log:
        findings = await audit_seed_default_passwords(
            db_session,
            app_env="production",
            strict_environment=True,
        )

    assert findings == [
        {
            "user_id": "usr_novu_admin",
            "email": "admin@novu.cz",
            "role": "superadmin",
            "organization_id": "org_novu",
        }
    ]
    critical_log.assert_called_once()
    event = critical_log.call_args.args[0]
    payload = critical_log.call_args.kwargs
    assert event == "SECURITY_EVENT: seed_default_password_detected"
    assert payload["fail_fast"] is False
    assert payload["user_id"] == "usr_novu_admin"
    assert payload["email"] == "admin@novu.cz"
    assert "NovuAdmin2024!" not in str(payload)
    assert "password_hash" not in str(payload)


@pytest.mark.asyncio
async def test_seed_default_password_check_downgrades_to_warning_in_development(db_session):
    await _create_user(
        db_session,
        user_id="usr_novu_admin",
        organization_id="org_novu",
        email="admin@novu.cz",
        password="StrongRotatedPass!9",
        role="superadmin",
    )
    await _create_user(
        db_session,
        user_id="usr_1",
        organization_id="org_1",
        email="demo@novu.local",
        password="demo1234",
        role="manager",
    )
    await _create_user(
        db_session,
        user_id="usr_2",
        organization_id="org_1",
        email="tech@novu.local",
        password="AnotherRotatedPass!4",
        role="technician",
    )

    with (
        patch("app.db.bootstrap.logger.warning") as warning_log,
        patch("app.db.bootstrap.logger.critical") as critical_log,
    ):
        findings = await audit_seed_default_passwords(
            db_session,
            app_env="development",
            strict_environment=False,
        )

    assert findings == [
        {
            "user_id": "usr_1",
            "email": "demo@novu.local",
            "role": "manager",
            "organization_id": "org_1",
        }
    ]
    warning_log.assert_called_once()
    critical_log.assert_not_called()


@pytest.mark.asyncio
async def test_verify_seed_credentials_on_startup_uses_startup_environment_policy():
    settings = SimpleNamespace(app_env="staging")
    findings = [{"user_id": "usr_novu_admin"}]

    with (
        patch("app.main.AsyncSessionFactory") as session_factory,
        patch("app.main.audit_seed_default_passwords", new=AsyncMock(return_value=findings)) as audit_mock,
    ):
        session_factory.return_value.__aenter__.return_value = "session"
        result = await verify_seed_credentials_on_startup(settings)

    assert result == findings
    audit_mock.assert_awaited_once_with(
        "session",
        app_env="staging",
        strict_environment=True,
    )
