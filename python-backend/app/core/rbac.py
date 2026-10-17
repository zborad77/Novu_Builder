"""Central role model and authorization rules.

Two separate permission planes:

* **system** – platform administration across all tenants. Held only by users
  with ``users.is_superadmin = true`` (role string ``superadmin``). Never granted
  through ``role_permissions`` and never assignable through any HTTP API;
  superadmin accounts are created and recovered only with the server CLI
  (``scripts/create_pilot_admin.py``).
* **tenant** – administration and work inside exactly one organization:
  ``admin`` (company administrator) ⊃ ``manager`` (operations) ⊃ ``technician``
  (regular user).

Everything not explicitly allowed here is denied. Callers raise the HTTP error;
this module only decides.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.models import ProjectPhoto, User
    from app.schemas.auth import AuthUserRead


SUPERADMIN_ROLE = "superadmin"
TENANT_ADMIN_ROLE = "admin"
MANAGER_ROLE = "manager"
TECHNICIAN_ROLE = "technician"

TENANT_ROLES: frozenset[str] = frozenset({TENANT_ADMIN_ROLE, MANAGER_ROLE, TECHNICIAN_ROLE})
ALL_ROLES: frozenset[str] = TENANT_ROLES | {SUPERADMIN_ROLE}

# Roles that may run manager-level case operations inside their own tenant.
TENANT_OPERATOR_ROLES: frozenset[str] = frozenset({TENANT_ADMIN_ROLE, MANAGER_ROLE})

# Roles each actor may hand out through the user administration API.
_ASSIGNABLE_BY_SUPERADMIN: frozenset[str] = TENANT_ROLES
_ASSIGNABLE_BY_TENANT_ADMIN: frozenset[str] = frozenset({MANAGER_ROLE, TECHNICIAN_ROLE})

TenantRole = Literal["admin", "manager", "technician"]

Decision = Literal["allow", "not_found", "forbidden"]


def is_system_admin(user: AuthUserRead) -> bool:
    """Superadmin acting as themselves (never through an impersonation token)."""
    return bool(user.isSuperAdmin) and not user.impersonatedBy


def is_tenant_admin(user: AuthUserRead) -> bool:
    return (
        not user.isSuperAdmin
        and not user.impersonatedBy
        and user.role == TENANT_ADMIN_ROLE
        and bool(user.organizationId)
    )


def is_tenant_operator(user: AuthUserRead) -> bool:
    """Manager-level access to tenant data (case workflow, exports, …)."""
    return bool(user.isSuperAdmin) or user.role in TENANT_OPERATOR_ROLES


def is_protected_account(target: User) -> bool:
    """Superadmin accounts are never manageable through the administration API."""
    return bool(target.is_superadmin) or target.role == SUPERADMIN_ROLE


def assignable_roles(actor: AuthUserRead) -> frozenset[str]:
    if is_system_admin(actor):
        return _ASSIGNABLE_BY_SUPERADMIN
    if is_tenant_admin(actor):
        return _ASSIGNABLE_BY_TENANT_ADMIN
    return frozenset()


def user_admin_org_scope(actor: AuthUserRead) -> str | None:
    """Organization a user administrator is confined to; ``None`` = all tenants."""
    if is_system_admin(actor):
        return None
    return actor.organizationId


def can_view_user(actor: AuthUserRead, target: User) -> Decision:
    if is_system_admin(actor):
        return "allow"
    if not is_tenant_admin(actor):
        return "forbidden"
    # Superadmins and other tenants' users are invisible to company admins.
    if is_protected_account(target) or target.organization_id != actor.organizationId:
        return "not_found"
    return "allow"


def can_manage_user(actor: AuthUserRead, target: User, *, sensitive: bool) -> Decision:
    """Whether ``actor`` may modify ``target``.

    ``sensitive`` covers role, activation and password changes. Those are never
    allowed on one's own account here (self-service password change goes through
    ``POST /auth/change-password`` with re-authentication) and a company admin may
    not apply them to another company admin.
    """
    visibility = can_view_user(actor, target)
    if visibility != "allow":
        return visibility
    if is_protected_account(target):
        return "forbidden"
    if target.id == actor.id:
        return "forbidden" if sensitive else "allow"
    if is_tenant_admin(actor) and target.role == TENANT_ADMIN_ROLE:
        return "forbidden"
    return "allow"


def can_soft_delete_photo(actor: AuthUserRead, photo: ProjectPhoto) -> Decision:
    """Soft delete / restore / see in trash. Tenant scope is checked by the caller.

    Managers and company admins handle every photo of their tenant. A technician
    only handles photos the server recorded as uploaded by them; photos with an
    unknown author (NULL) are never a technician's.
    """
    if is_tenant_operator(actor):
        return "allow"
    if photo.uploaded_by_user_id is not None and photo.uploaded_by_user_id == actor.id:
        return "allow"
    return "forbidden"


def can_purge_photo_in_tenant(actor: AuthUserRead) -> Decision:
    """Permanent deletion through the tenant API: company admins only.

    Superadmins must use the system administration endpoint, which audits the
    cross-tenant action separately; managers and technicians are refused.
    """
    return "allow" if is_tenant_admin(actor) else "forbidden"


def can_manage_company(actor: AuthUserRead, company_id: str) -> Decision:
    if is_system_admin(actor):
        return "allow"
    if is_tenant_admin(actor):
        return "allow" if company_id == actor.organizationId else "not_found"
    return "forbidden"
