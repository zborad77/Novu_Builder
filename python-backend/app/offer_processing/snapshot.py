"""Input snapshot builder — freezes offer data before AI invocation.

Security boundary: the agent receives ONLY a frozen, anonymized snapshot.
No customer names, organization IDs, emails, or cross-tenant data are included.

Snapshot versioning ensures every AgentRun records exactly which versions of
prompts, pricing, and catalog were active at computation time. Without this,
"why was this offer different last week?" is unanswerable.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Version context — what was active when this snapshot was built
# ---------------------------------------------------------------------------

CURRENT_PROMPT_VERSION   = "offer-v1"
CURRENT_CATALOG_VERSION  = 1   # increment when work_types seeds change
CURRENT_PRICING_VERSION  = 1   # increment when pricing logic changes


@dataclass(frozen=True)
class SnapshotVersionContext:
    """Immutable record of all versioned inputs used in this computation."""
    prompt_version:   str
    catalog_version:  int
    pricing_version:  int
    model_id:         str
    model_build:      str
    built_at:         str   # ISO-8601

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def current(cls, *, model_id: str, model_build: str) -> "SnapshotVersionContext":
        return cls(
            prompt_version=CURRENT_PROMPT_VERSION,
            catalog_version=CURRENT_CATALOG_VERSION,
            pricing_version=CURRENT_PRICING_VERSION,
            model_id=model_id,
            model_build=model_build,
            built_at=datetime.now(UTC).isoformat(),
        )


# ---------------------------------------------------------------------------
# Snapshot payload — what the agent actually receives
# ---------------------------------------------------------------------------


@dataclass
class OfferInputSnapshot:
    """Anonymized, frozen representation of one offer request.

    Contains NO: organization_id, customer names, emails, phone numbers,
    or any cross-tenant references. Only the data the agent needs to
    produce a pricing estimate.
    """
    work_type_code:       str
    parameters:           dict[str, Any]
    photo_urls:           list[str]         # presigned, short-lived
    work_type_definition: dict[str, Any]    # catalog entry for this work type
    pricing_context:      dict[str, Any]    # material prices, labor rates
    version_context:      SnapshotVersionContext

    def to_json(self) -> str:
        data = {
            "work_type_code": self.work_type_code,
            "parameters": self.parameters,
            "photo_urls": self.photo_urls,
            "work_type_definition": self.work_type_definition,
            "pricing_context": self.pricing_context,
            "version_context": self.version_context.as_dict(),
        }
        return json.dumps(data, ensure_ascii=False, sort_keys=True)

    def sha256(self) -> str:
        return hashlib.sha256(self.to_json().encode()).hexdigest()


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------


async def build_input_snapshot(
    *,
    work_type_code: str,
    parameters: dict[str, Any],
    photo_presigned_urls: list[str],
    work_type_definition: dict[str, Any],
    pricing_context: dict[str, Any],
    model_id: str,
    model_build: str,
) -> OfferInputSnapshot:
    """Build the frozen snapshot sent to the AI agent.

    Callers are responsible for resolving presigned URLs and stripping PII
    BEFORE calling this function. This function performs no DB access.
    """
    version_ctx = SnapshotVersionContext.current(
        model_id=model_id,
        model_build=model_build,
    )
    return OfferInputSnapshot(
        work_type_code=work_type_code,
        parameters=parameters,
        photo_urls=photo_presigned_urls,
        work_type_definition=work_type_definition,
        pricing_context=pricing_context,
        version_context=version_ctx,
    )
