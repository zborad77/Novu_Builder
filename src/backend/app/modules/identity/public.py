"""Veřejné rozhraní modulu app.modules.identity.

Ostatní moduly, composition a worker smějí z tohoto modulu importovat
výhradně odsud (vynucuje tests/architecture/test_module_boundaries.py).
Vygenerováno tools/refactor/make_public.py; ruční doplňky patří mezi značky
`# --- ručně ---` a `# --- konec ---`.
"""
from app.modules.identity.api.auth import (  # noqa: F401
    router as auth_router,
)
from app.modules.identity.api.deps import (  # noqa: F401
    get_company_service,
    get_current_user,
    require_admin_capability,
    require_manager,
    require_org_id,
    require_superadmin,
    require_user_admin,
    resolve_org_id,
)
from app.modules.identity.api.org_users import (  # noqa: F401
    router as org_users_router,
)
from app.modules.identity.audit_actor import (  # noqa: F401
    lookup_audit_actor,
)
from app.modules.identity.auth_service import (  # noqa: F401
    AuthService,
    hash_password,
    verify_password,
)
from app.modules.identity.authz import (  # noqa: F401
    commit_security_critical_audit_or_503,
    enforce_rbac_decision,
)
from app.modules.identity.company_service import (  # noqa: F401
    CompanyService,
)
from app.modules.identity.models import (  # noqa: F401
    Organization,
    User,
)
from app.modules.identity.rbac import (  # noqa: F401
    Decision,
    assignable_roles,
    can_manage_company,
    can_manage_user,
    can_purge_photo_in_tenant,
    can_soft_delete_photo,
    can_view_user,
    is_tenant_operator,
    may_soft_delete_photo_of,
    user_admin_org_scope,
)
from app.modules.identity.schemas.auth import (  # noqa: F401
    AuthUserRead,
)
from app.modules.identity.schemas.company import (  # noqa: F401
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserPatch,
    AdminUserRead,
    CompanyCreate,
    CompanyListResponse,
    CompanyPatch,
    CompanyRead,
)
from app.modules.identity.security import (  # noqa: F401
    enforce_password_strength,
)
from app.modules.identity.token_repository import (  # noqa: F401
    SessionTokenRevocation,
    TokenRepository,
)

# --- ručně ---
# Registrace ORM modelů modulu (app.composition.models.import_all_models).
import app.modules.identity.models as orm_models  # noqa: E402
# --- konec ---

__all__ = [
    "orm_models",
    "AdminUserCreate",
    "AdminUserListResponse",
    "AdminUserPatch",
    "AdminUserRead",
    "AuthService",
    "AuthUserRead",
    "CompanyCreate",
    "CompanyListResponse",
    "CompanyPatch",
    "CompanyRead",
    "CompanyService",
    "Decision",
    "Organization",
    "SessionTokenRevocation",
    "TokenRepository",
    "User",
    "commit_security_critical_audit_or_503",
    "enforce_rbac_decision",
    "assignable_roles",
    "auth_router",
    "can_manage_company",
    "can_manage_user",
    "can_purge_photo_in_tenant",
    "can_soft_delete_photo",
    "can_view_user",
    "enforce_password_strength",
    "get_company_service",
    "get_current_user",
    "hash_password",
    "is_tenant_operator",
    "lookup_audit_actor",
    "may_soft_delete_photo_of",
    "org_users_router",
    "require_admin_capability",
    "require_manager",
    "require_org_id",
    "require_superadmin",
    "require_user_admin",
    "resolve_org_id",
    "user_admin_org_scope",
    "verify_password",
]
