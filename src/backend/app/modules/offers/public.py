"""Veřejné rozhraní modulu app.modules.offers.

Ostatní moduly, composition a worker smějí z tohoto modulu importovat
výhradně odsud (vynucuje tests/architecture/test_module_boundaries.py).
Vygenerováno tools/refactor/make_public.py; ruční doplňky patří mezi značky
`# --- ručně ---` a `# --- konec ---`.
"""
from app.modules.offers.api.offer_events import (  # noqa: F401
    router as offer_events_router,
)
from app.modules.offers.api.offer_requests import (  # noqa: F401
    router as offer_requests_router,
)
from app.modules.offers.budget import (  # noqa: F401
    BudgetExhaustedError,
    BudgetService,
    DEFAULT_TOKEN_ESTIMATE,
    estimate_cost_usd,
)
from app.modules.offers.budget_sweeper import (  # noqa: F401
    BudgetSweeper,
)
from app.modules.offers.domain import (  # noqa: F401
    AGENT_OUTCOME_INSUFFICIENT_DATA,
    AGENT_OUTCOME_OFFER_GENERATED,
    ERROR_BUDGET_EXHAUSTED,
    ERROR_PROVIDER_RATE_LIMITED,
    ERROR_PROVIDER_UNAVAILABLE,
    ERROR_SNAPSHOT_BUILD_FAILED,
    ERROR_UNKNOWN,
    ERROR_VALIDATION_FAILED,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    OFFER_STATUS_FAILED,
    OFFER_STATUS_NEEDS_MORE_INFO,
    OFFER_STATUS_NEEDS_REVIEW,
    OFFER_STATUS_PROCESSING,
    OFFER_STATUS_QUEUED,
    POISON_THRESHOLD,
    RETRY_BACKOFF_SECONDS,
)
from app.modules.offers.provider import (  # noqa: F401
    AgentRuntime,
    ProviderError,
    ProviderRateLimitedError,
    ProviderRequest,
    ProviderUnavailableError,
    build_agent_runtime,
)
from app.modules.offers.reconciler import (  # noqa: F401
    OfferReconciler,
)
from app.modules.offers.repository import (  # noqa: F401
    OfferRepository,
)
from app.modules.offers.snapshot import (  # noqa: F401
    build_input_snapshot,
)
from app.modules.offers.validation import (  # noqa: F401
    InsufficientDataResult,
    OfferOutputValidator,
    OfferValidationError,
)
from app.modules.offers.readiness import (  # noqa: F401
    OfferBacklog,
    OfferWorkerNotReadyError,
    check_offer_provider_ready,
    collect_offer_backlog,
)

# --- ručně ---
# Registrace ORM modelů modulu (app.composition.models.import_all_models).
import app.modules.offers.models as orm_models  # noqa: E402
# --- konec ---

__all__ = [
    "OfferBacklog",
    "OfferWorkerNotReadyError",
    "check_offer_provider_ready",
    "collect_offer_backlog",
    "orm_models",
    "AGENT_OUTCOME_INSUFFICIENT_DATA",
    "AGENT_OUTCOME_OFFER_GENERATED",
    "AgentRuntime",
    "BudgetExhaustedError",
    "BudgetService",
    "BudgetSweeper",
    "DEFAULT_TOKEN_ESTIMATE",
    "ERROR_BUDGET_EXHAUSTED",
    "ERROR_PROVIDER_RATE_LIMITED",
    "ERROR_PROVIDER_UNAVAILABLE",
    "ERROR_SNAPSHOT_BUILD_FAILED",
    "ERROR_UNKNOWN",
    "ERROR_VALIDATION_FAILED",
    "InsufficientDataResult",
    "JOB_STATUS_COMPLETED",
    "JOB_STATUS_FAILED",
    "OFFER_STATUS_FAILED",
    "OFFER_STATUS_NEEDS_MORE_INFO",
    "OFFER_STATUS_NEEDS_REVIEW",
    "OFFER_STATUS_PROCESSING",
    "OFFER_STATUS_QUEUED",
    "OfferOutputValidator",
    "OfferReconciler",
    "OfferRepository",
    "OfferValidationError",
    "POISON_THRESHOLD",
    "ProviderError",
    "ProviderRateLimitedError",
    "ProviderRequest",
    "ProviderUnavailableError",
    "RETRY_BACKOFF_SECONDS",
    "build_agent_runtime",
    "build_input_snapshot",
    "estimate_cost_usd",
    "offer_events_router",
    "offer_requests_router",
]
