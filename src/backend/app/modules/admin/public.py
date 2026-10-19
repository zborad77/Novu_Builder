"""Veřejné rozhraní modulu app.modules.admin.

Ostatní moduly, composition a worker smějí z tohoto modulu importovat
výhradně odsud (vynucuje tests/architecture/test_module_boundaries.py).
Vygenerováno tools/refactor/make_public.py; ruční doplňky patří mezi značky
`# --- ručně ---` a `# --- konec ---`.
"""
from app.modules.admin.api.admin import (  # noqa: F401
    router as admin_router,
)

__all__ = [
    "admin_router",
]
