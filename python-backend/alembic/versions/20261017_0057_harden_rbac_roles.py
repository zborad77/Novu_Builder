"""Separate system and tenant permissions; repair escalated roles (SA-01).

Revision ID: 20261017_0057
Revises: 20261003_0056

Migration 20260326_0018 seeded ``manager -> admin:read, admin:write`` into
role_permissions. Combined with role_permissions-based checks, that let any
tenant manager reset the superadmin's password, create users in other tenants
and set their own role to "superadmin". The application no longer consults
role_permissions for non-superadmins; this revision removes the data that made
the escalation possible and adds database guarantees so it cannot reappear:

1. Delete every role_permissions row whose role is not ``superadmin``.
2. Repair users whose role cannot be legitimate:
   * ``role = 'superadmin'`` without ``is_superadmin`` (the escalation path), and
   * any role outside ``superadmin | admin | manager | technician``
     (e.g. the former API default ``dispatcher``).
   They are moved to the least-privileged tenant role ``technician`` and every
   token they hold is invalidated (``token_version`` bump). Nobody is ever
   promoted, and ``is_superadmin`` is never inferred from the role string.
3. Record each repair in audit_logs (``migration.rbac_role_repair`` and
   ``migration.rbac_permissions_revoked``) so operators can review them.
4. Add CHECK constraints ``ck_users_role_valid`` and
   ``ck_users_superadmin_requires_flag``.

Downgrade drops the two constraints only. It deliberately does not restore the
manager permissions or the repaired roles: re-granting them would reopen the
privilege escalation. Review the audit rows written by upgrade to restore an
individual role by hand if a repair was wrong.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "20261017_0057"
down_revision = "20261003_0056"
branch_labels = None
depends_on = None

_log = logging.getLogger("alembic.runtime.migration")

_VALID_ROLES = ("superadmin", "admin", "manager", "technician")
_REPAIRED_ROLE = "technician"
_ROLE_CHECK = "ck_users_role_valid"
_SUPERADMIN_CHECK = "ck_users_superadmin_requires_flag"


def _tables(bind):
    detail_type = JSONB() if bind.dialect.name == "postgresql" else sa.JSON()
    metadata = sa.MetaData()
    users = sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.String(64)),
        sa.Column("organization_id", sa.String(64)),
        sa.Column("email", sa.String(255)),
        sa.Column("role", sa.String(64)),
        sa.Column("is_superadmin", sa.Boolean()),
        sa.Column("token_version", sa.Integer()),
        sa.Column("tokens_valid_after", sa.DateTime(timezone=True)),
    )
    role_permissions = sa.Table(
        "role_permissions",
        metadata,
        sa.Column("role", sa.String(64)),
        sa.Column("capability", sa.String(128)),
    )
    audit_logs = sa.Table(
        "audit_logs",
        metadata,
        sa.Column("id", sa.String(64)),
        sa.Column("user_id", sa.String(64)),
        sa.Column("user_email", sa.String(255)),
        sa.Column("org_id", sa.String(64)),
        sa.Column("action", sa.String(128)),
        sa.Column("resource_type", sa.String(64)),
        sa.Column("resource_id", sa.String(64)),
        sa.Column("detail", detail_type),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    return users, role_permissions, audit_logs


def upgrade() -> None:
    bind = op.get_bind()
    users, role_permissions, audit_logs = _tables(bind)
    now = datetime.now(UTC).replace(microsecond=0)

    revoked = bind.execute(
        sa.select(role_permissions.c.role, role_permissions.c.capability)
        .where(role_permissions.c.role != "superadmin")
        .order_by(role_permissions.c.role, role_permissions.c.capability)
    ).all()
    if revoked:
        bind.execute(sa.delete(role_permissions).where(role_permissions.c.role != "superadmin"))
        bind.execute(
            sa.insert(audit_logs).values(
                id=uuid4().hex,
                action="migration.rbac_permissions_revoked",
                resource_type="role_permissions",
                detail={
                    "revision": revision,
                    "revoked": [{"role": role, "capability": capability} for role, capability in revoked],
                },
                created_at=now,
            )
        )
        _log.warning("RBAC repair: revoked %d non-superadmin role_permissions rows", len(revoked))

    invalid = bind.execute(
        sa.select(users.c.id, users.c.organization_id, users.c.email, users.c.role)
        .where(
            sa.or_(
                users.c.role.not_in(_VALID_ROLES),
                sa.and_(users.c.role == "superadmin", sa.not_(users.c.is_superadmin)),
            )
        )
        .order_by(users.c.id)
    ).all()
    for user_id, organization_id, _email, previous_role in invalid:
        bind.execute(
            sa.update(users)
            .where(users.c.id == user_id)
            .values(
                role=_REPAIRED_ROLE,
                token_version=sa.func.coalesce(users.c.token_version, 0) + 1,
                tokens_valid_after=now,
            )
        )
        bind.execute(
            sa.insert(audit_logs).values(
                id=uuid4().hex,
                org_id=organization_id,
                action="migration.rbac_role_repair",
                resource_type="user",
                resource_id=user_id,
                detail={
                    "revision": revision,
                    "previous_role": previous_role,
                    "new_role": _REPAIRED_ROLE,
                    "reason": (
                        "superadmin role without is_superadmin flag"
                        if previous_role == "superadmin"
                        else "role outside the supported role set"
                    ),
                    "tokens_invalidated": True,
                },
                created_at=now,
            )
        )
    if invalid:
        _log.warning(
            "RBAC repair: moved %d user(s) to role %r and invalidated their tokens; see audit_logs "
            "action 'migration.rbac_role_repair'",
            len(invalid),
            _REPAIRED_ROLE,
        )

    with op.batch_alter_table("users") as batch_op:
        batch_op.create_check_constraint(
            _ROLE_CHECK,
            "role IN ('superadmin', 'admin', 'manager', 'technician')",
        )
        batch_op.create_check_constraint(
            _SUPERADMIN_CHECK,
            "role <> 'superadmin' OR is_superadmin",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint(_SUPERADMIN_CHECK, type_="check")
        batch_op.drop_constraint(_ROLE_CHECK, type_="check")
