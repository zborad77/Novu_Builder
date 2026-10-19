"""Veřejné rozhraní modulu app.modules.catalog.

Ostatní moduly, composition a worker smějí z tohoto modulu importovat
výhradně odsud (vynucuje tests/architecture/test_module_boundaries.py).
Vygenerováno tools/refactor/make_public.py; ruční doplňky patří mezi značky
`# --- ručně ---` a `# --- konec ---`.
"""
from app.modules.catalog.analysis_profile_service import (  # noqa: F401
    AnalysisProfileResolutionError,
    AnalysisProfileService,
)
from app.modules.catalog.api.material_catalog import (  # noqa: F401
    router as material_catalog_router,
)
from app.modules.catalog.api.pricebooks import (  # noqa: F401
    router as pricebooks_router,
)
from app.modules.catalog.api.suppliers import (  # noqa: F401
    router as suppliers_router,
)
from app.modules.catalog.api.work_catalog import (  # noqa: F401
    router as work_catalog_router,
)
from app.modules.catalog.models import (  # noqa: F401
    MaterialCatalog,
    PricingProfile,
    Supplier,
    SupplierMaterialPrice,
)
from app.modules.catalog.pricing_profile_service import (  # noqa: F401
    PricingProfileResolutionError,
    PricingProfileService,
)
from app.modules.catalog.work_catalog.domain import (  # noqa: F401
    CatalogValidationError,
)
from app.modules.catalog.work_catalog.models import (  # noqa: F401
    AnalysisProfile,
    AnalysisProfileConfidenceThreshold,
    AnalysisProfileExtractionRule,
    AnalysisProfileIgnoredObject,
    AnalysisProfileOutputMapping,
    AnalysisProfileTargetObject,
    AnalysisProfileValidationRule,
    CatalogPricingProfile,
    CatalogPricingProfileAdjustmentRule,
    CatalogPricingProfileBaseRule,
    CatalogPricingProfileLaborAssumption,
    CatalogPricingProfileMaterialAssumption,
    CatalogPricingProfileRequiredInput,
    ProjectWorkItem,
    ProjectWorkItemValue,
    TenantWorkTypeParameterOverride,
    TenantWorkTypeSetting,
    VisionDetection,
    WorkCategory,
    WorkType,
    WorkTypeParameter,
    WorkTypeParameterOption,
)
from app.modules.catalog.work_catalog.phase_bindings import (  # noqa: F401
    get_phase_binding,
)
from app.modules.catalog.work_catalog.seeds import (  # noqa: F401
    GLOBAL_WORK_CATALOG_SEED,
)
from app.modules.catalog.work_catalog_repository import (  # noqa: F401
    WorkCatalogRepository,
)

# --- ručně ---
# Registrace ORM modelů modulu (app.composition.models.import_all_models).
import app.modules.catalog.models as orm_models  # noqa: E402
import app.modules.catalog.work_catalog.models as work_catalog_orm_models  # noqa: E402
# --- konec ---

__all__ = [
    "work_catalog_orm_models",
    "orm_models",
    "AnalysisProfile",
    "AnalysisProfileConfidenceThreshold",
    "AnalysisProfileExtractionRule",
    "AnalysisProfileIgnoredObject",
    "AnalysisProfileOutputMapping",
    "AnalysisProfileResolutionError",
    "AnalysisProfileService",
    "AnalysisProfileTargetObject",
    "AnalysisProfileValidationRule",
    "CatalogPricingProfile",
    "CatalogPricingProfileAdjustmentRule",
    "CatalogPricingProfileBaseRule",
    "CatalogPricingProfileLaborAssumption",
    "CatalogPricingProfileMaterialAssumption",
    "CatalogPricingProfileRequiredInput",
    "CatalogValidationError",
    "GLOBAL_WORK_CATALOG_SEED",
    "MaterialCatalog",
    "PricingProfile",
    "PricingProfileResolutionError",
    "PricingProfileService",
    "ProjectWorkItem",
    "ProjectWorkItemValue",
    "Supplier",
    "SupplierMaterialPrice",
    "TenantWorkTypeParameterOverride",
    "TenantWorkTypeSetting",
    "VisionDetection",
    "WorkCatalogRepository",
    "WorkCategory",
    "WorkType",
    "WorkTypeParameter",
    "WorkTypeParameterOption",
    "get_phase_binding",
    "material_catalog_router",
    "pricebooks_router",
    "suppliers_router",
    "work_catalog_router",
]
