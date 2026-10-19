"""Veřejné rozhraní modulu app.modules.quoting.

Ostatní moduly, composition a worker smějí z tohoto modulu importovat
výhradně odsud (vynucuje tests/architecture/test_module_boundaries.py).
Vygenerováno tools/refactor/make_public.py; ruční doplňky patří mezi značky
`# --- ručně ---` a `# --- konec ---`.
"""
from app.modules.quoting.api.estimates import (  # noqa: F401
    router as estimates_router,
)
from app.modules.quoting.final_proposal_repository import (  # noqa: F401
    FinalProposalRepository,
)
from app.modules.quoting.models import (  # noqa: F401
    ProjectFinalProposal,
    ProjectProposalDraft,
    QuoteItem,
    QuoteVariant,
)
from app.modules.quoting.proposal_draft_repository import (  # noqa: F401
    ProposalDraftRepository,
    ProposalVersionConflictError,
)
from app.modules.quoting.proposal_draft_service import (  # noqa: F401
    build_final_proposal_from_record,
    build_final_proposal_snapshot_payload,
    build_project_proposal_draft,
    normalize_proposal_patch_payload,
)
from app.modules.quoting.quote_variant_service import (  # noqa: F401
    to_variant_read,
)
from app.modules.quoting.recalculation import (  # noqa: F401
    QuoteVariantRecalculator,
)
from app.modules.quoting.schemas.proposal import (  # noqa: F401
    ProjectFinalProposal as ProjectFinalProposalSchema,
    ProjectProposalDraft as ProjectProposalDraftSchema,
    ProjectProposalDraftPatch,
    ProposalDraftField,
    ProposalDraftItem,
    ProposalDraftSection,
)

# --- ručně ---
# Registrace ORM modelů modulu (app.composition.models.import_all_models).
import app.modules.quoting.models as orm_models  # noqa: E402
# --- konec ---

__all__ = [
    "orm_models",
    "FinalProposalRepository",
    "ProjectFinalProposal",
    "ProjectFinalProposalSchema",
    "ProjectProposalDraft",
    "ProjectProposalDraftPatch",
    "ProjectProposalDraftSchema",
    "ProposalDraftField",
    "ProposalDraftItem",
    "ProposalDraftRepository",
    "ProposalDraftSection",
    "ProposalVersionConflictError",
    "QuoteItem",
    "QuoteVariant",
    "QuoteVariantRecalculator",
    "build_final_proposal_from_record",
    "build_final_proposal_snapshot_payload",
    "build_project_proposal_draft",
    "estimates_router",
    "normalize_proposal_patch_payload",
    "to_variant_read",
]
