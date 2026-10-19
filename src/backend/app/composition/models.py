"""Registr ORM modelů všech modulů.

SQLAlchemy resolvuje relace mezi modely (deklarované stringem) až při konfiguraci
mapperů, proto musí být před prvním dotazem, `create_all`/`drop_all` i Alembic
autogenerate naimportované VŠECHNY modely. Dřív to dělal vedlejší efekt
`import app.models`; nově to výslovně zajišťuje tato funkce, kterou volají všechny
vstupní body (API, worker, Alembic, testy, skripty).
"""
from __future__ import annotations


def import_all_models() -> None:
    import app.models  # noqa: F401  (modely, které ještě nebyly přesunuty do modulů)
    import app.modules.analysis.models  # noqa: F401
    import app.modules.audit.models  # noqa: F401
    import app.modules.catalog.models  # noqa: F401
    import app.modules.catalog.work_catalog.models  # noqa: F401
    import app.modules.cases.models  # noqa: F401
    import app.modules.exports.models  # noqa: F401
    import app.modules.identity.models  # noqa: F401
    import app.modules.media.models  # noqa: F401
    import app.modules.quoting.models  # noqa: F401
