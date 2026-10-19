"""N1: přechody zakázky, které provádí worker přímo v repozitáři (mimo
CaseActionService a registr efektů cases.effects).

Rozbor (REFACTOR_FINDINGS N1): pro analyzing -> quote_ready nejsou v registru
žádné efekty, takže přímé apply_transition nic nevynechá; analyzing ->
proposal_ready při rekalkulaci nabídky zapisuje outbox proposal.ready ve stejné
transakci a živou publikaci po commitu provádí AnalysisService
(proposal_event_id). Testy toto chování zamykají, aby duplicita s efekty
registru nemohla potichu vést k chybějící nebo dvojí události.
"""

import pytest
from sqlalchemy import select

from app.modules.cases.effects import _AFTER_COMMIT, _BEFORE_COMMIT
from app.modules.cases.models import Project
from app.modules.catalog.models import PricingProfile
from app.modules.quoting.quote_variant_repository import QuoteVariantRepository
from app.platform.events.models import OutboxEvent
from app.platform.events.types import AGGREGATE_CASE, EVENT_PROPOSAL_READY


def test_no_registered_effects_are_skipped_by_worker_quote_ready_transition():
    # analysis_repository přechází analyzing -> quote_ready bez registru efektů.
    assert not _BEFORE_COMMIT.get(("analyzing", "quote_ready"))
    assert not _AFTER_COMMIT.get(("analyzing", "quote_ready"))


@pytest.mark.asyncio
async def test_quote_recalculation_writes_exactly_one_proposal_ready_event(db_session, test_tenants):
    project = Project(
        id="prj_n1_recalc",
        organization_id="org_e2e_a",
        created_by_user_id="usr_e2e_a1",
        title="Case prj_n1_recalc",
        status="analyzing",
    )
    db_session.add(project)
    await db_session.commit()
    pricing_profile = await db_session.get(PricingProfile, "pp_e2e_a1")

    _variants, proposal_event_id = await QuoteVariantRepository(db_session).replace_project_variants(
        project=project,
        analysis=None,
        pricing_profile=pricing_profile,
        variants_payload=[],
    )

    await db_session.refresh(project)
    assert project.status == "proposal_ready"
    events = (
        await db_session.execute(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_type == AGGREGATE_CASE,
                OutboxEvent.aggregate_id == project.id,
                OutboxEvent.event_type == EVENT_PROPOSAL_READY,
            )
        )
    ).scalars().all()
    assert len(events) == 1
    # AnalysisService publikuje živě právě tuto událost (stejné event_id).
    assert proposal_event_id == events[0].id
