from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.auth import AuthUserRead


def test_bind_request_audit_actor_stores_full_actor_context():
    from app.core.audit import _audit_actor_from_context, _request_audit_actor, bind_request_audit_actor

    request = SimpleNamespace(state=SimpleNamespace())
    current_user = AuthUserRead(
        id="usr-1",
        email="audit@test.local",
        fullName="Audit User",
        role="manager",
        isActive=True,
        organizationId="org-1",
        isSuperAdmin=False,
        impersonatedBy="admin-1",
    )

    token = _request_audit_actor.set(None)
    try:
        bind_request_audit_actor(request, current_user)

        actor = request.state.audit_actor
        assert actor.user_id == "usr-1"
        assert actor.user_email == "audit@test.local"
        assert actor.org_id == "org-1"
        assert actor.impersonated_by == "admin-1"
        assert _audit_actor_from_context("usr-1") == actor
    finally:
        _request_audit_actor.reset(token)


@pytest.mark.asyncio
async def test_enrich_audit_actor_skips_lookup_when_request_state_already_has_identity():
    from app.core.audit import _AuditActor, _enrich_audit_actor

    session = AsyncMock()
    actor = _AuditActor(
        user_id="usr-1",
        user_email="audit@test.local",
        org_id="org-1",
        impersonated_by=None,
    )

    enriched = await _enrich_audit_actor(session, actor)

    assert enriched == actor
    session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_enrich_audit_actor_uses_request_context_without_lookup():
    from app.core.audit import _AuditActor, _enrich_audit_actor, _request_audit_actor

    session = AsyncMock()
    token = _request_audit_actor.set(
        _AuditActor(
            user_id="usr-1",
            user_email="audit@test.local",
            org_id="org-1",
            impersonated_by="admin-1",
        )
    )
    try:
        enriched = await _enrich_audit_actor(
            session,
            _AuditActor(
                user_id="usr-1",
                user_email=None,
                org_id=None,
                impersonated_by=None,
            ),
        )
    finally:
        _request_audit_actor.reset(token)

    assert enriched.user_id == "usr-1"
    assert enriched.user_email == "audit@test.local"
    assert enriched.org_id == "org-1"
    assert enriched.impersonated_by == "admin-1"
    session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_write_audit_log_skips_lookup_when_request_context_has_identity():
    from app.core.audit import _request_audit_actor, bind_request_audit_actor, write_audit_log

    request = SimpleNamespace(state=SimpleNamespace())
    current_user = AuthUserRead(
        id="usr-1",
        email="audit@test.local",
        fullName="Audit User",
        role="manager",
        isActive=True,
        organizationId="org-1",
        isSuperAdmin=False,
        impersonatedBy="admin-1",
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    token = _request_audit_actor.set(None)
    try:
        bind_request_audit_actor(request, current_user)

        await write_audit_log(
            session,
            current_user_id="usr-1",
            action="case.update",
            resource_type="cases",
            resource_id="case-1",
            detail={"field": "status"},
        )
    finally:
        _request_audit_actor.reset(token)

    session.get.assert_not_awaited()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_write_audit_log_rolls_back_on_commit_failure():
    from app.core.audit import write_audit_log

    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    session.rollback = AsyncMock()

    await write_audit_log(
        session,
        current_user_id="usr-1",
        action="case.update",
        resource_type="cases",
        resource_id="case-1",
        detail={"field": "status"},
    )

    session.rollback.assert_awaited_once()
