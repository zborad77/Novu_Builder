"""Propojení modulů: registrace ORM modelů, implementací portů a efektů přechodů.

Moduly smějí importovat jen moduly pod sebou. Kde nižší modul potřebuje službu
vyššího (audit -> identity, media -> exports, analysis -> quoting/workflow,
workflow -> exports, efekty přechodů cases), definuje port a tato funkce do něj
zapojí implementaci. Volá ji každý vstupní bod (API, worker, skripty, testy);
neprovedené propojení se projeví výjimkou, nikdy tichým vynecháním efektu.
"""

from __future__ import annotations

_initialized = False


def modules_initialized() -> bool:
    return _initialized


def init_modules() -> None:
    global _initialized
    if _initialized:
        return

    from app.composition.models import import_all_models

    import_all_models()

    from app.modules.analysis.ports import register_proposal_ready_notifier, register_quote_recalculator
    from app.modules.audit.audit_log import register_actor_lookup
    from app.modules.cases.effects import mark_effect_providers_loaded
    from app.modules.exports.export_repository import ExportRepository
    from app.modules.exports.export_service import ExportService
    from app.modules.identity.audit_actor import lookup_audit_actor
    from app.modules.media.ports import register_export_invalidator
    from app.modules.quoting.recalculation import QuoteVariantRecalculator
    from app.modules.workflow.ports import register_final_proposal_exporter_factory
    from app.modules.workflow.proposal_ready import mark_proposal_ready

    # audit -> identity: e-mail a organizace aktéra audit záznamu
    register_actor_lookup(lookup_audit_actor)
    # media -> exports: purge fotky zneplatní exporty zakázky (F0.3), stejná transakce
    register_export_invalidator(
        lambda session, project_id, now: ExportRepository(session).expire_project_exports(project_id, now=now)
    )
    # analysis -> quoting / workflow: rekalkulace nabídky a posun do proposal_ready
    register_quote_recalculator(QuoteVariantRecalculator())
    register_proposal_ready_notifier(mark_proposal_ready)
    # workflow -> exports: exporty finálního návrhu
    register_final_proposal_exporter_factory(lambda session: ExportService(ExportRepository(session)))

    # Efekty přechodů zakázky: workflow (analýza, outbox, pricing lock) a exports.
    import app.modules.exports.case_effects  # noqa: F401
    import app.modules.workflow.action_effects  # noqa: F401

    mark_effect_providers_loaded()
    _initialized = True
