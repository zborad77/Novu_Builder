"""Tělo požadavku pro proxy: průběžný SHA-256, limit a dočasný soubor (review M2).

Podpis pro core potřebuje SHA-256 těla už v hlavičkách, takže tělo musí být
celé přijaté dřív, než se odešle. Aby upload až 25 MiB nebyl v paměti (dříve
``b"".join`` ≈ 2× velikost), čte se po blocích do ``SpooledTemporaryFile``:
do ``max_memory`` (1 MiB) v paměti, nad ní na disk. Do core se pak streamuje
ze souboru po blocích s explicitním ``Content-Length``. Čte se až po kontrole
session a CSRF.
"""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import AsyncIterator
from typing import Final

from starlette.types import Receive

from nc_gateway.web import BodyTooLargeError, ClientDisconnectedError

DEFAULT_MAX_MEMORY: Final = 1024 * 1024
CHUNK_SIZE: Final = 64 * 1024


class RequestBody:
    def __init__(self, max_memory: int = DEFAULT_MAX_MEMORY) -> None:
        # zavírá close() (volá proxy ve finally)
        spooled = tempfile.SpooledTemporaryFile(max_size=max_memory)  # noqa: SIM115
        self._file: tempfile.SpooledTemporaryFile[bytes] = spooled
        self._hash = hashlib.sha256()
        self.length = 0

    @property
    def sha256(self) -> str:
        return self._hash.hexdigest()

    @property
    def on_disk(self) -> bool:
        """``True``, když tělo přerostlo limit paměti a leží v dočasném souboru."""
        return bool(getattr(self._file, "_rolled", False))

    def write(self, chunk: bytes) -> None:
        self._file.write(chunk)
        self._hash.update(chunk)
        self.length += len(chunk)

    async def chunks(self) -> AsyncIterator[bytes]:
        """Tělo po blocích od začátku (lze volat opakovaně – opakování po obnově tokenu)."""
        self._file.seek(0)
        while True:
            chunk = self._file.read(CHUNK_SIZE)
            if not chunk:
                return
            yield chunk

    def close(self) -> None:
        self._file.close()


async def read_request_body(receive: Receive, limit: int, *, max_memory: int = DEFAULT_MAX_MEMORY) -> RequestBody:
    """Načte tělo s průběžným limitem (i pro chunked bez ``Content-Length``)."""
    body = RequestBody(max_memory)
    try:
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                raise ClientDisconnectedError
            chunk = message.get("body", b"")
            if body.length + len(chunk) > limit:
                raise BodyTooLargeError
            if chunk:
                body.write(chunk)
            if not message.get("more_body", False):
                return body
    except BaseException:
        body.close()
        raise
