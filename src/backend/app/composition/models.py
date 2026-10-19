"""Registr ORM modelů všech modulů.

SQLAlchemy resolvuje relace mezi modely (deklarované stringem) až při konfiguraci
mapperů, proto musí být před prvním dotazem, `create_all`/`drop_all` i Alembic
autogenerate naimportované VŠECHNY modely. Dřív to dělal vedlejší efekt
`import app.models`; nově to výslovně zajišťuje tato funkce, kterou volají všechny
vstupní body (API, worker, Alembic, testy, skripty).
"""
from __future__ import annotations


def import_all_models() -> None:
    # Import veřejného rozhraní modulu registruje jeho ORM modely (orm_models).
    from app.modules.analysis.public import orm_models as _analysis  # noqa: F401
    from app.modules.audit.public import orm_models as _audit  # noqa: F401
    from app.modules.cases.public import orm_models as _cases  # noqa: F401
    from app.modules.catalog.public import orm_models as _catalog  # noqa: F401
    from app.modules.catalog.public import work_catalog_orm_models as _work_catalog  # noqa: F401
    from app.modules.exports.public import orm_models as _exports  # noqa: F401
    from app.modules.identity.public import orm_models as _identity  # noqa: F401
    from app.modules.media.public import orm_models as _media  # noqa: F401
    from app.modules.offers.public import orm_models as _offers  # noqa: F401
    from app.modules.quoting.public import orm_models as _quoting  # noqa: F401
    import app.platform.events.models  # noqa: F401
