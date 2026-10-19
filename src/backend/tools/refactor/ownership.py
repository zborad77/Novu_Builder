"""Vlastnictví kódu podle cílových modulů (zdroj pravdy pro analýzu závislostí a codemod).

FILE_OWNER: starý modul -> cílový modul (pro soubory, které se nedělí).
SYMBOL_OWNER: symboly z dělených souborů (modely, schémata) -> cílový modul.
"""
P, SH = "platform", "shared"

FILE_OWNER = {
    "app.main": "composition", "app.api.router": "composition", "app.api.deps": "composition",
    "app.db.bootstrap": "composition",
    # platform
    **{f"app.core.{m}": P for m in (
        "api_versioning cache client_ip config email events exposure gateway_auth limiter logging "
        "metrics redis_client request_id slo sql_like tenant_timing backpressure "
        "analysis_provider_capabilities").split()},
    "app.db.base": P, "app.db.session": P, "app.db.seed_runtime": P,
    **{f"app.storage.{m}": P for m in "backend local_photo_storage s3_photo_storage".split()},
    **{f"app.worker.{m}": P for m in "queue heavy_queue offer_queue heartbeat healthcheck".split()},
    "app.offer_processing.outbox": P, "app.api.routes.system": P,
    "app.worker.runner": "worker", "app.worker.offer_runner": "worker",
    # audit
    "app.core.audit": "audit",
    # identity
    **{f"app.core.{m}": "identity" for m in "rbac security device_binding account_limiter token_limits".split()},
    "app.api.routes.auth": "identity", "app.api.routes.org_users": "identity",
    "app.services.auth_service": "identity", "app.services.company_service": "identity",
    "app.repositories.token_repository": "identity", "app.schemas.auth": "identity", "app.schemas.company": "identity",
    # catalog
    **{f"app.work_catalog.{m}": "catalog" for m in (
        "__init__ analysis_profile_seed_data cache domain parameter_seed_data phase_bindings "
        "pricing_profile_seed_data seed_ids seeds").split()},
    **{f"app.services.{m}": "catalog" for m in (
        "analysis_profile_service material_catalog_service pricebook_service pricing_profile_service "
        "supplier_service tenant_work_type_resolution_service work_catalog_service").split()},
    **{f"app.repositories.{m}": "catalog" for m in (
        "material_catalog_repository pricebook_repository supplier_repository work_catalog_repository").split()},
    **{f"app.api.routes.{m}": "catalog" for m in "material_catalog pricebooks suppliers work_catalog".split()},
    **{f"app.schemas.{m}": "catalog" for m in "material_catalog pricebook supplier work_catalog".split()},
    # cases
    **{f"app.case_workflow.{m}": "cases" for m in "__init__ effects transitions".split()},
    "app.repositories.project_repository": "cases",
    # workflow = orchestrace zakázky napříč moduly (use-cases, read-model detailu)
    "app.case_workflow.case_actions": "workflow", "app.case_workflow.action_effects": "workflow",
    "app.services.project_service": "workflow", "app.api.routes.cases": "workflow",
    "app.api.routes.case_events": "workflow",
    # media
    "app.api.routes.images": "media", "app.api.routes.markers": "media", "app.api.routes.exports": "exports",
    "app.api.routes.storage": "media", "app.api.photo_purge": "media", "app.core.purge_ledger": "media",
    "app.services.photo_service": "media",
    "app.services.export_service": "exports", "app.services.storage_consistency_service": "exports",
    **{f"app.repositories.{m}": "media" for m in ("photo_repository marker_repository").split()},
    "app.repositories.export_repository": "exports", "app.repositories.storage_consistency_repository": "exports",
    **{f"app.schemas.{m}": "media" for m in "photo marker".split()}, "app.schemas.export": "exports",
    # analysis
    **{f"app.ai.{m}": "analysis" for m in "__init__ analysis_service pipeline pipeline_contracts".split()},
    **{f"app.ai.providers.{m}": "analysis" for m in (
        "__init__ claude_vision_provider mock_vision_provider openai_vision_provider").split()},
    "app.services.analysis_service": "analysis", "app.repositories.analysis_repository": "analysis",
    "app.api.routes.analysis_jobs": "analysis", "app.api.routes.measurements": "analysis",
    "app.schemas.analysis": "analysis", "app.schemas.measurement": "analysis",
    # quoting
    **{f"app.services.{m}": "quoting" for m in "quote_variant_service proposal_draft_service".split()},
    **{f"app.repositories.{m}": "quoting" for m in (
        "quote_variant_repository proposal_draft_repository final_proposal_repository").split()},
    "app.api.routes.estimates": "quoting", "app.schemas.quote_variant": "quoting",
    # offers
    **{f"app.offer_processing.{m}": "offers" for m in (
        "__init__ budget budget_sweeper domain provider reconciler repository service snapshot validation").split()},
    "app.api.routes.offer_requests": "offers", "app.api.routes.offer_events": "offers",
    "app.schemas.offer_requests": "offers",
    # dělené / agregační soubory řeší SYMBOL_OWNER
    "app.api.routes.admin": "admin*",
}

_IDENTITY = "Organization User RevokedToken UserSession RolePermission PasswordResetToken"
_CATALOG = (
    "PricingProfile Supplier MaterialCatalog SupplierMaterialPrice WorkCategory AnalysisProfile "
    "AnalysisProfileTargetObject AnalysisProfileIgnoredObject AnalysisProfileExtractionRule "
    "AnalysisProfileValidationRule AnalysisProfileConfidenceThreshold AnalysisProfileOutputMapping "
    "CatalogPricingProfile CatalogPricingProfileRequiredInput CatalogPricingProfileLaborAssumption "
    "CatalogPricingProfileMaterialAssumption CatalogPricingProfileBaseRule CatalogPricingProfileAdjustmentRule "
    "WorkType WorkTypeParameter WorkTypeParameterOption WorkTypeComponent TenantWorkTypeSetting "
    "TenantWorkTypeParameterOverride TenantWorkTypeExtraParameter TenantWorkTypeExtraParameterOption"
)
MODEL_OWNER = {
    **{n: "identity" for n in _IDENTITY.split()},
    "AuditLog": "audit",
    **{n: "cases" for n in "Client Project ProjectStatusHistory".split()},
    **{n: "media" for n in "ProjectPhoto Marker".split()}, "ProjectExport": "exports",
    **{n: "analysis" for n in "AnalysisJob AnalysisResult".split()},
    **{n: "catalog" for n in "ProjectWorkItem ProjectWorkItemValue VisionDetection".split()},
    **{n: "catalog" for n in _CATALOG.split()},
    **{n: "quoting" for n in (
        "QuoteVariant QuoteItem ProjectProposalDraft ProjectFinalProposal").split()},
    **{n: "offers" for n in "OfferRequest OfferJob AgentRun AiBudgetReservation OrganizationAiBudget".split()},
    "OutboxEvent": P, "TimestampMixin": P,
}
SCHEMA_PROJECT_OWNER = {
    **{n: "quoting" for n in (
        "ProposalDraftWorkItem ProposalDraftMaterial ProposalDraftField ProposalDraftItem ProposalDraftSection "
        "ProjectProposalDraft ProjectFinalProposal ProjectProposalDraftPatch").split()},
}
SCHEMA_QUOTE_OWNER = {"AnalysisJobRead": "analysis"}
SPLIT_FILES = {
    "app.models": MODEL_OWNER, "app.models.domain": MODEL_OWNER, "app.models.work_catalog": MODEL_OWNER,
    "app.models.offer_processing": MODEL_OWNER,
}
