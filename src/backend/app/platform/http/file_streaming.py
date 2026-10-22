"""Streamování souborů z úložiště klientům (NC-007 etapa 1, kap. 6.1 a 6.2).

Doménově neutrální pomocník: o oprávnění a o tom, *který* klíč se čte,
rozhoduje volající modul (klíč pochází vždy z DB, nikdy z požadavku). Tady se
jen čte aktivní úložiště po blocích, zpracuje se ``Range`` a nastaví se
bezpečnostní hlavičky. Klient nikdy nedostane URL úložiště ani přesměrování.
"""

from __future__ import annotations

import re
from typing import Final, Literal, Mapping

import structlog
from starlette.responses import Response, StreamingResponse

from app.platform.storage.backend import (
    DEFAULT_STREAM_CHUNK_SIZE,
    get_storage_object_size,
    iter_storage_file,
    validate_storage_key,
)

logger = structlog.get_logger(__name__)

# Odpověď se souborem nesmí v prohlížeči nic spustit ani načíst (SVG/HTML apod.).
FILE_RESPONSE_CSP: Final = "default-src 'none'; sandbox"
FILE_RESPONSE_CACHE_CONTROL: Final = "private, no-store"
GENERIC_CONTENT_TYPE: Final = "application/octet-stream"

# Typy fotek, které smí odejít s vlastním Content-Type; cokoli jiného je octet-stream.
IMAGE_CONTENT_TYPES: Final = frozenset({"image/jpeg", "image/png", "image/webp", "image/heic"})

Disposition = Literal["inline", "attachment"]

_DIGITS = re.compile(r"[0-9]{1,19}")
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_FILENAME_LENGTH = 120


class RangeNotSatisfiableError(ValueError):
    """Hlavička ``Range`` je neplatná nebo mimo velikost objektu (→ 416)."""


def image_content_type(stored_mime_type: str | None) -> str:
    normalized = (stored_mime_type or "").split(";", 1)[0].strip().lower()
    return normalized if normalized in IMAGE_CONTENT_TYPES else GENERIC_CONTENT_TYPE


def safe_download_filename(filename: str | None, *, fallback: str = "download") -> str:
    """Jméno pro ``Content-Disposition``: jen ASCII ``[A-Za-z0-9._-]``, bez uvozovek a lomítek."""
    candidate = _UNSAFE_FILENAME_CHARS.sub("-", (filename or "").strip())
    candidate = re.sub(r"-+", "-", candidate).strip("-.")
    if len(candidate) > _MAX_FILENAME_LENGTH:
        stem, dot, ext = candidate.rpartition(".")
        if dot and 0 < len(ext) <= 10:
            candidate = f"{stem[: _MAX_FILENAME_LENGTH - len(ext) - 1]}.{ext}"
        else:
            candidate = candidate[:_MAX_FILENAME_LENGTH]
    return candidate or fallback


def content_disposition(disposition: Disposition, filename: str | None) -> str:
    return f'{disposition}; filename="{safe_download_filename(filename)}"'


def parse_byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Jediný rozsah ``bytes=a-b`` / ``bytes=a-`` / ``bytes=-n`` → (start, end) včetně.

    ``None`` = hlavička chybí (celý objekt). Víc rozsahů naráz (multipart/byteranges)
    se nepodporuje a stejně jako syntakticky neplatný nebo nesplnitelný rozsah
    vede na 416 (kontrakt kap. 6.1).
    """
    if header is None:
        return None
    value = header.strip()
    if value[:6].lower() != "bytes=":
        raise RangeNotSatisfiableError("unsupported range unit")
    spec = value[6:].strip()
    if "," in spec:
        raise RangeNotSatisfiableError("multiple ranges are not supported")
    first, sep, last = spec.partition("-")
    first, last = first.strip(), last.strip()
    if not sep or size <= 0:
        raise RangeNotSatisfiableError("range not satisfiable")
    if not first:
        if not _DIGITS.fullmatch(last):
            raise RangeNotSatisfiableError("invalid suffix range")
        suffix = int(last)
        if suffix == 0:
            raise RangeNotSatisfiableError("empty suffix range")
        return max(0, size - suffix), size - 1
    if not _DIGITS.fullmatch(first) or (last and not _DIGITS.fullmatch(last)):
        raise RangeNotSatisfiableError("invalid range")
    start = int(first)
    end = int(last) if last else size - 1
    if start >= size or end < start:
        raise RangeNotSatisfiableError("range not satisfiable")
    return start, min(end, size - 1)


def file_response_headers(*, disposition: Disposition, filename: str | None) -> dict[str, str]:
    return {
        "Accept-Ranges": "bytes",
        "Cache-Control": FILE_RESPONSE_CACHE_CONTROL,
        "Content-Disposition": content_disposition(disposition, filename),
        "Content-Security-Policy": FILE_RESPONSE_CSP,
        "X-Content-Type-Options": "nosniff",
    }


async def storage_file_response(
    *,
    request_headers: Mapping[str, str],
    storage_key: str,
    content_type: str,
    filename: str | None,
    disposition: Disposition,
    chunk_size: int = DEFAULT_STREAM_CHUNK_SIZE,
) -> Response | None:
    """Odpověď streamující objekt úložiště; ``None``, když objekt neexistuje.

    ``If-Range`` bez validátorů (ETag/Last-Modified tu nevydáváme) nejde
    ověřit, proto se podle RFC 9110 rozsah ignoruje a vrátí se celý objekt.
    """
    try:
        validate_storage_key(storage_key)
    except ValueError as exc:
        # Klíč z DB s traversalem/absolutní cestou: nikdy nečíst, navenek jen 404.
        logger.error("SECURITY_EVENT: storage_key_rejected", reason=str(exc))
        return None
    size = await get_storage_object_size(relative_storage_key=storage_key)
    if size is None:
        return None
    headers = file_response_headers(disposition=disposition, filename=filename)
    range_header = None if request_headers.get("if-range") is not None else request_headers.get("range")
    try:
        byte_range = parse_byte_range(range_header, size)
    except RangeNotSatisfiableError:
        headers["Content-Range"] = f"bytes */{size}"
        return Response(status_code=416, headers=headers)

    if size == 0:
        return Response(content=b"", status_code=200, headers=headers, media_type=content_type)
    if byte_range is None:
        start, end, status_code = 0, size - 1, 200
    else:
        start, end = byte_range
        status_code = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(end - start + 1)
    return StreamingResponse(
        iter_storage_file(relative_storage_key=storage_key, start=start, end=end, chunk_size=chunk_size),
        status_code=status_code,
        headers=headers,
        media_type=content_type,
    )


def _binary(description: str) -> dict:
    return {
        "description": description,
        "content": {GENERIC_CONTENT_TYPE: {"schema": {"type": "string", "format": "binary"}}},
    }


# Dokumentace odpovědí streamovacích rout v OpenAPI (src/contracts).
FILE_RESPONSES_DOC: Final[dict[int | str, dict]] = {
    200: _binary("Celý soubor (Content-Type podle allowlistu, jinak application/octet-stream)."),
    206: _binary("Část souboru podle hlavičky Range (Content-Range)."),
    404: {"description": "Neexistuje, cizí firma, smazáno, nehotové nebo expirované."},
    416: {"description": "Neplatný nebo nesplnitelný rozsah (Content-Range: bytes */<velikost>)."},
}
