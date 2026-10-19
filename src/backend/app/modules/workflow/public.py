"""Veřejné rozhraní modulu app.modules.workflow.

Ostatní moduly, composition a worker smějí z tohoto modulu importovat
výhradně odsud (vynucuje tests/architecture/test_module_boundaries.py).
Vygenerováno tools/refactor/make_public.py; ruční doplňky patří mezi značky
`# --- ručně ---` a `# --- konec ---`.
"""
from app.modules.workflow.api.case_events import (  # noqa: F401
    router as case_events_router,
)
from app.modules.workflow.api.cases import (  # noqa: F401
    router as cases_router,
)
from app.modules.workflow.api.deps import (  # noqa: F401
    get_project_service,
)
from app.modules.workflow.ports import (  # noqa: F401
    register_final_proposal_exporter_factory,
)
from app.modules.workflow.project_service import (  # noqa: F401
    ProjectService,
)
from app.modules.workflow.proposal_ready import (  # noqa: F401
    mark_proposal_ready,
)
from app.modules.workflow.schemas import (  # noqa: F401
    ProjectDetail,
)

# --- ručně ---
# Efekty přechodů zakázky – načítá app.composition.wiring.init_modules().
import app.modules.workflow.action_effects as transition_effects  # noqa: E402
# --- konec ---

__all__ = [
    "transition_effects",
    "ProjectDetail",
    "ProjectService",
    "case_events_router",
    "cases_router",
    "get_project_service",
    "mark_proposal_ready",
    "register_final_proposal_exporter_factory",
]
