"""Veřejné rozhraní modulu app.modules.audit.

Ostatní moduly, composition a worker smějí z tohoto modulu importovat
výhradně odsud (vynucuje tests/architecture/test_module_boundaries.py).
Vygenerováno tools/refactor/make_public.py; ruční doplňky patří mezi značky
`# --- ručně ---` a `# --- konec ---`.
"""
from app.modules.audit.audit_log import (  # noqa: F401
    AUDIT_POLICY_OPERATIONAL,
    AUDIT_POLICY_SECURITY_CRITICAL,
    AuditEntry,
    AuditMiddleware,
    SecurityAuditWriteError,
    bind_request_audit_actor,
    commit_security_critical_audit,
    log_cross_tenant_denied,
    mark_request_audited,
    record_audit_entries,
    register_actor_lookup,
    write_audit_log,
)
from app.modules.audit.models import (  # noqa: F401
    AuditLog,
)

# --- ručně ---
# Registrace ORM modelů modulu (app.composition.models.import_all_models).
import app.modules.audit.models as orm_models  # noqa: E402
# --- konec ---

__all__ = [
    "orm_models",
    "AUDIT_POLICY_OPERATIONAL",
    "AUDIT_POLICY_SECURITY_CRITICAL",
    "AuditEntry",
    "AuditLog",
    "AuditMiddleware",
    "SecurityAuditWriteError",
    "bind_request_audit_actor",
    "commit_security_critical_audit",
    "log_cross_tenant_denied",
    "mark_request_audited",
    "record_audit_entries",
    "register_actor_lookup",
    "write_audit_log",
]
