"""Průchozí allowlist ``/bff/api`` (kontrakt NC-007 kap. 2.1).

Zdroj je ``docs/security/gateway-allowlist.json`` (jediný soubor sdílený
s core). Průchozí množina = allowlist **minus** cesty pod ``/api/v1/auth/``
a ``/api/v1/internal/``. Shoda je (METODA, šablona) po segmentech; parametr
šablony odpovídá právě jednomu segmentu ``[A-Za-z0-9._~-]{1,128}``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

API_PREFIX: Final = "/api/v1/"
BFF_API_PREFIX: Final = "/bff/api/"
EXCLUDED_PREFIXES: Final = ("/api/v1/auth/", "/api/v1/internal/")
FORBIDDEN_METHODS: Final = frozenset({"HEAD", "OPTIONS", "TRACE", "CONNECT"})
ALLOWED_METHODS: Final = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})

SEGMENT_RE: Final = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")
_PARAM_RE: Final = re.compile(r"^\{[A-Za-z_][A-Za-z0-9_]*\}$")
_LITERAL_RE: Final = re.compile(r"^[A-Za-z0-9._~-]+$")
_FORBIDDEN_ENCODINGS: Final = ("%2f", "%5c", "%00", "%2e")


class AllowlistError(ValueError):
    """Allowlist chybí, je nečitelný, prázdný nebo neplatný – gateway nenastartuje."""


@dataclass(frozen=True)
class RouteTemplate:
    method: str
    path: str
    segments: tuple[str | None, ...]  # None = parametr šablony

    def matches(self, segments: list[str]) -> bool:
        if len(segments) != len(self.segments):
            return False
        for expected, actual in zip(self.segments, segments, strict=True):
            if expected is None:
                if not SEGMENT_RE.match(actual):
                    return False
            elif expected != actual:
                return False
        return True


def _compile(method: str, path: str) -> RouteTemplate:
    if method not in ALLOWED_METHODS:
        raise AllowlistError(f"Allowlist obsahuje nepodporovanou metodu {method!r}.")
    if not path.startswith(API_PREFIX):
        raise AllowlistError(f"Cesta allowlistu {path!r} nezačíná {API_PREFIX}.")
    segments: list[str | None] = []
    for part in path[1:].split("/"):
        if _PARAM_RE.match(part):
            segments.append(None)
        elif _LITERAL_RE.match(part) and part not in (".", ".."):
            segments.append(part)
        else:
            raise AllowlistError(f"Cesta allowlistu {path!r} obsahuje neplatný segment {part!r}.")
    return RouteTemplate(method=method, path=path, segments=tuple(segments))


class Allowlist:
    def __init__(self, routes: Iterable[tuple[str, str]], upload_routes: Iterable[tuple[str, str]] | None = None):
        compiled: list[RouteTemplate] = []
        for method, path in routes:
            if path.startswith(EXCLUDED_PREFIXES):
                continue  # volá jen gateway ze svých handlerů
            compiled.append(_compile(method.upper(), path))
        if not compiled:
            raise AllowlistError("Průchozí allowlist je prázdný.")
        self.routes: tuple[RouteTemplate, ...] = tuple(compiled)
        if upload_routes is None:
            # výchozí: POST …/images a POST …/upload*
            self.upload_routes: frozenset[tuple[str, str]] = frozenset(
                (route.method, route.path)
                for route in self.routes
                if route.method == "POST"
                and (route.path.endswith("/images") or route.path.rsplit("/", 1)[-1].startswith("upload"))
            )
        else:
            self.upload_routes = frozenset((m.upper(), p) for m, p in upload_routes)

    @classmethod
    def load(cls, path: Path, upload_routes: Iterable[tuple[str, str]] | None = None) -> Allowlist:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise AllowlistError(f"Allowlist {path} nejde načíst: {type(exc).__name__}.") from exc
        if not isinstance(data, dict) or not isinstance(data.get("routes"), list) or not data["routes"]:
            raise AllowlistError(f"Allowlist {path} neobsahuje neprázdný seznam 'routes'.")
        if data.get("zone") not in (None, "gateway"):
            raise AllowlistError(f"Allowlist {path} není pro zónu gateway.")
        routes: list[tuple[str, str]] = []
        for item in data["routes"]:
            if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ("method", "path")):
                raise AllowlistError(f"Allowlist {path} obsahuje neplatnou položku.")
            routes.append((item["method"], item["path"]))
        return cls(routes, upload_routes)

    def match(self, method: str, core_path: str) -> RouteTemplate | None:
        """Najde šablonu pro (metoda, cesta na core). Cesta musí projít :func:`split_safe_path`."""
        if method in FORBIDDEN_METHODS or method not in ALLOWED_METHODS:
            return None
        segments = split_safe_path(core_path)
        if segments is None:
            return None
        for route in self.routes:
            if route.method == method and route.matches(segments):
                return route
        return None

    def is_upload(self, route: RouteTemplate) -> bool:
        return (route.method, route.path) in self.upload_routes


def split_safe_path(raw_path: str) -> list[str] | None:
    """Rozdělí surovou cestu na segmenty, nebo vrátí ``None`` (→ 404).

    Odmítá: zpětné lomítko, ``%2F``, ``%5C``, ``%00``, ``%2E`` (v libovolné
    velikosti písmen), jakékoli jiné percent-encoding, prázdné segmenty
    (``//``, koncové ``/``), segmenty ``.`` a ``..`` a znaky mimo
    ``[A-Za-z0-9._~-]``.
    """
    if not raw_path.startswith("/") or "\\" in raw_path:
        return None
    lowered = raw_path.lower()
    if any(token in lowered for token in _FORBIDDEN_ENCODINGS) or "%" in raw_path:
        return None
    segments = raw_path[1:].split("/")
    for segment in segments:
        if segment in ("", ".", "..") or not SEGMENT_RE.match(segment):
            return None
    return segments
