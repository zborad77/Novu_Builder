"""Veřejné rozhraní modulu app.modules.analysis.

Ostatní moduly, composition a worker smějí z tohoto modulu importovat
výhradně odsud (vynucuje tests/architecture/test_module_boundaries.py).
Vygenerováno tools/refactor/make_public.py; ruční doplňky patří mezi značky
`# --- ručně ---` a `# --- konec ---`.
"""
from app.modules.analysis.analysis_repository import (  # noqa: F401
    ANALYSIS_JOB_STATUS_QUEUED,
    ANALYSIS_JOB_STATUS_RUNNING,
    ANALYSIS_JOB_TYPE_MANUAL_TRIGGER,
    AnalysisJobLeaseOwnershipError,
    AnalysisRepository,
)
from app.modules.analysis.analysis_service import (  # noqa: F401
    AnalysisService,
    to_job_read,
)
from app.modules.analysis.api.analysis_jobs import (  # noqa: F401
    router as analysis_jobs_router,
)
from app.modules.analysis.api.deps import (  # noqa: F401
    get_analysis_service,
)
from app.modules.analysis.api.measurements import (  # noqa: F401
    router as measurements_router,
)
from app.modules.analysis.models import (  # noqa: F401
    AnalysisJob,
    AnalysisResult,
)
from app.modules.analysis.ports import (  # noqa: F401
    QuoteRecalculationUnavailableError,
    register_proposal_ready_notifier,
    register_quote_recalculator,
)

# --- ručně ---
# Registrace ORM modelů modulu (app.composition.models.import_all_models).
import app.modules.analysis.models as orm_models  # noqa: E402
# --- konec ---

__all__ = [
    "orm_models",
    "ANALYSIS_JOB_STATUS_QUEUED",
    "ANALYSIS_JOB_STATUS_RUNNING",
    "ANALYSIS_JOB_TYPE_MANUAL_TRIGGER",
    "AnalysisJob",
    "AnalysisJobLeaseOwnershipError",
    "AnalysisRepository",
    "AnalysisResult",
    "AnalysisService",
    "QuoteRecalculationUnavailableError",
    "analysis_jobs_router",
    "get_analysis_service",
    "measurements_router",
    "register_proposal_ready_notifier",
    "register_quote_recalculator",
    "to_job_read",
]
