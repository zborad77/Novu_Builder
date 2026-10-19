#!/usr/bin/env python3
"""Export API contracts and internal architecture baselines (modular refactor B0).

Sdílené API kontrakty (src/contracts/, čtou je klienti):
    openapi/openapi.json          – OpenAPI dokument FastAPI aplikace
    openapi/routes.snapshot.json  – routy v PŘESNÉM pořadí registrace (exposure
                                    guard bere první shodu šablony)

Interní baseline backendu (tests/architecture/baseline/, nesdílí se):
    middleware.json        – pořadí a parametry middlewarů (F3.4 → SA-05 → F3 …)
    security_surface.json  – per routa: zóny exposure, závislosti (RBAC/tenant
                             guardy) a rate limity slowapi
    metadata.json          – SQLAlchemy metadata (tabulky, sloupce, FK, indexy)
    migrations.json        – Alembic řetězec + otisk obsahu každé revize

Refaktor nesmí žádný z těchto souborů změnit (kromě explicitně schválených změn).

    python -m scripts.export_contracts            # přepíše soubory
    python -m scripts.export_contracts --check    # exit 1, pokud se liší
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.platform.paths import repo_root as _repo_root  # noqa: E402

CONTRACTS_DIR = _repo_root() / "src" / "contracts" / "openapi"
BASELINE_DIR = BACKEND_ROOT / "tests" / "architecture" / "baseline"


def _pinned_env() -> None:
    # Kontrakty se generují vždy ve stejném profilu, nezávisle na lokálním .env.
    os.environ["NOVU_IGNORE_ENV_FILES"] = "1"
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("JWT_SECRET", "contract-export-not-a-secret-0123456789abcdef")
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./contract-export.db")
    os.environ.setdefault("AI_ANALYSIS_PROVIDER", "mock")


def _dumps(document: Any) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def _callable_name(obj: Any) -> str:
    name = getattr(obj, "__name__", None)
    if name is None:
        name = type(obj).__name__
    return str(name)


def _dependency_names(dependant: Any) -> list[str]:
    names: list[str] = []

    def walk(dep: Any) -> None:
        for sub in dep.dependencies:
            if sub.call is not None:
                names.append(_callable_name(sub.call))
            walk(sub)

    walk(dependant)
    return names


def _api_routes(app: Any) -> list[Any]:
    from fastapi.routing import APIRoute
    from starlette.routing import Mount, Route, WebSocketRoute

    return [r for r in app.router.routes if isinstance(r, (APIRoute, Route, WebSocketRoute, Mount))]


def build_openapi(app: Any) -> str:
    return _dumps(app.openapi())


def build_routes_snapshot(app: Any) -> str:
    routes = []
    for index, route in enumerate(_api_routes(app)):
        methods = sorted(getattr(route, "methods", None) or [])
        routes.append(
            {
                "order": index,
                "methods": methods,
                "path": route.path,
                "name": getattr(route, "name", None),
                "kind": type(route).__name__,
                "inSchema": bool(getattr(route, "include_in_schema", False)),
            }
        )
    return _dumps({"count": len(routes), "routes": routes})


def build_middleware_snapshot(app: Any) -> str:
    stack = []
    # app.user_middleware: index 0 = nejvnějšnější (poslední add_middleware).
    for position, middleware in enumerate(app.user_middleware):
        cls = middleware.cls
        kwargs = dict(getattr(middleware, "kwargs", {}) or {})
        entry: dict[str, Any] = {"position": position, "class": cls.__name__}
        dispatch = kwargs.pop("dispatch", None)
        if dispatch is not None:
            entry["dispatch"] = _callable_name(dispatch)
        entry["kwargs"] = sorted(kwargs)
        stack.append(entry)
    handlers = sorted(
        (key.__name__ if isinstance(key, type) else str(key)) for key in app.exception_handlers
    )
    return _dumps({"outermostFirst": stack, "exceptionHandlers": handlers})


def build_security_surface(app: Any) -> str:
    from fastapi.routing import APIRoute

    from app.platform.http.exposure import EXPOSURE

    limiter = app.state.limiter
    route_limits = getattr(limiter, "_route_limits", {})
    exempt = getattr(limiter, "_exempt_routes", set())
    out = []
    for route in _api_routes(app):
        if not isinstance(route, APIRoute):
            continue
        endpoint = route.endpoint
        key = f"{endpoint.__module__}.{endpoint.__name__}"
        for method in sorted(route.methods or []):
            zones = EXPOSURE.get((method, route.path))
            out.append(
                {
                    "method": method,
                    "path": route.path,
                    "zones": sorted(zones) if zones is not None else None,
                    "dependencies": _dependency_names(route.dependant),
                    "rateLimits": [str(limit.limit) for limit in route_limits.get(key, [])],
                    "rateLimitExempt": key in exempt,
                }
            )
    exposure = [
        {"method": method, "path": path, "zones": sorted(zones)}
        for (method, path), zones in sorted(EXPOSURE.items(), key=lambda kv: (kv[0][1], kv[0][0]))
    ]
    return _dumps({"routes": out, "exposureTable": exposure})


def build_metadata_snapshot() -> str:
    from app.platform.db.base import Base
    from app.composition.models import import_all_models

    import_all_models()

    tables = []
    for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
        columns = []
        for column in table.columns:
            columns.append(
                {
                    "name": column.name,
                    "type": str(column.type.compile(dialect=_pg_dialect())),
                    "nullable": column.nullable,
                    "primaryKey": column.primary_key,
                    "serverDefault": _server_default(column),
                    "foreignKeys": sorted(
                        f"{fk.target_fullname}|ondelete={fk.ondelete}" for fk in column.foreign_keys
                    ),
                    "unique": bool(column.unique),
                    "index": bool(column.index),
                }
            )
        constraints = sorted(
            f"{type(c).__name__}:{c.name}:{getattr(c, 'sqltext', '')}" for c in table.constraints
        )
        indexes = sorted(
            f"{ix.name}:{','.join(str(col) for col in ix.expressions)}:unique={ix.unique}" for ix in table.indexes
        )
        tables.append({"name": table.name, "columns": columns, "constraints": constraints, "indexes": indexes})
    return _dumps({"tableCount": len(tables), "tables": tables})


def _server_default(column: Any) -> str | None:
    default = column.server_default
    if default is None:
        return None
    arg = getattr(default, "arg", None)
    if arg is None:
        return type(default).__name__
    return str(getattr(arg, "text", arg))


def _pg_dialect() -> Any:
    from sqlalchemy.dialects import postgresql

    return postgresql.dialect()


def build_migrations_snapshot() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    revisions = []
    for rev in reversed(list(script.walk_revisions())):
        raw = Path(rev.path).read_bytes().replace(b"\r\n", b"\n")
        revisions.append(
            {
                "revision": rev.revision,
                "downRevision": rev.down_revision,
                "file": Path(rev.path).name,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return _dumps({"heads": sorted(script.get_heads()), "count": len(revisions), "revisions": revisions})


def outputs() -> dict[Path, str]:
    _pinned_env()
    from app.main import app

    return {
        CONTRACTS_DIR / "openapi.json": build_openapi(app),
        CONTRACTS_DIR / "routes.snapshot.json": build_routes_snapshot(app),
        BASELINE_DIR / "middleware.json": build_middleware_snapshot(app),
        BASELINE_DIR / "security_surface.json": build_security_surface(app),
        BASELINE_DIR / "metadata.json": build_metadata_snapshot(),
        BASELINE_DIR / "migrations.json": build_migrations_snapshot(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail if any committed file differs")
    args = parser.parse_args()
    stale = []
    for path, content in outputs().items():
        if args.check:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != content:
                stale.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
        print(f"wrote {path}")
    if stale:
        for path in stale:
            print(f"STALE: {path}", file=sys.stderr)
        print("run: python -m scripts.export_contracts (only for an approved contract change)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

