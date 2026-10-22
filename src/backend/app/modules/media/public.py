"""Veřejné rozhraní modulu app.modules.media.

Ostatní moduly, composition a worker smějí z tohoto modulu importovat
výhradně odsud (vynucuje tests/architecture/test_module_boundaries.py).
Vygenerováno tools/refactor/make_public.py; ruční doplňky patří mezi značky
`# --- ručně ---` a `# --- konec ---`.
"""
from app.modules.media.api.deps import (  # noqa: F401
    get_photo_service,
)
from app.modules.media.api.files import (  # noqa: F401
    router as image_files_router,
)
from app.modules.media.api.images import (  # noqa: F401
    router as images_router,
)
from app.modules.media.api.markers import (  # noqa: F401
    router as markers_router,
)
from app.modules.media.api.storage import (  # noqa: F401
    router as storage_router,
)
from app.modules.media.models import (  # noqa: F401
    ProjectPhoto,
)
from app.modules.media.photo_purge import (  # noqa: F401
    purge_photo_with_audit,
)
from app.modules.media.photo_repository import (  # noqa: F401
    PhotoRepository,
)
from app.modules.media.photo_service import (  # noqa: F401
    PhotoService,
    to_read_model,
)
from app.modules.media.ports import (  # noqa: F401
    register_export_invalidator,
)
from app.modules.media.schemas.photo import (  # noqa: F401
    PurgePhotoRequest,
    PurgePhotoResponse,
)

# --- ručně ---
# Registrace ORM modelů modulu (app.composition.models.import_all_models).
import app.modules.media.models as orm_models  # noqa: E402
# --- konec ---

__all__ = [
    "orm_models",
    "PhotoRepository",
    "PhotoService",
    "ProjectPhoto",
    "PurgePhotoRequest",
    "PurgePhotoResponse",
    "get_photo_service",
    "image_files_router",
    "images_router",
    "markers_router",
    "purge_photo_with_audit",
    "register_export_invalidator",
    "storage_router",
    "to_read_model",
]
