"""Veřejné rozhraní modulu app.modules.cases.

Ostatní moduly, composition a worker smějí z tohoto modulu importovat
výhradně odsud (vynucuje tests/architecture/test_module_boundaries.py).
Vygenerováno tools/refactor/make_public.py; ruční doplňky patří mezi značky
`# --- ručně ---` a `# --- konec ---`.
"""
from app.modules.cases.api.deps import (  # noqa: F401
    CaseReader,
    get_case_reader,
)
from app.modules.cases.effects import (  # noqa: F401
    EffectContext,
    after_transition,
    before_transition,
    mark_effect_providers_loaded,
    run_after_commit,
    run_before_commit,
)
from app.modules.cases.errors import (  # noqa: F401
    CaseActionError,
)
from app.modules.cases.models import (  # noqa: F401
    Client,
    Project,
    ProjectStatusHistory,
)
from app.modules.cases.repository import (  # noqa: F401
    ProjectRepository,
)
from app.modules.cases.transitions import (  # noqa: F401
    TransitionError,
    VALID_STATUSES,
    apply_transition,
    get_available_transitions,
)

# --- ručně ---
# Registrace ORM modelů modulu (app.composition.models.import_all_models).
import app.modules.cases.models as orm_models  # noqa: E402
# --- konec ---

__all__ = [
    "orm_models",
    "CaseActionError",
    "CaseReader",
    "Client",
    "EffectContext",
    "Project",
    "ProjectRepository",
    "ProjectStatusHistory",
    "TransitionError",
    "VALID_STATUSES",
    "after_transition",
    "apply_transition",
    "before_transition",
    "get_available_transitions",
    "get_case_reader",
    "mark_effect_providers_loaded",
    "run_after_commit",
    "run_before_commit",
]
