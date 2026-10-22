"""Klient gateway → core: každý požadavek podepsaný HMAC (unikátní nonce, ts).

* Požadavek se staví ručně (``httpx.Request``), takže neobsahuje žádné
  výchozí hlavičky klienta (User-Agent, cookies, Accept-Encoding).
* Podpis se počítá z **finální** URL (``request.url.raw_path``), tedy přesně
  z bajtů, které odejdou na core (httpx může některé znaky query
  percent-enkódovat).
* Cookie jar klienta odmítá všechny cookies – nic z core se mezi požadavky
  různých uživatelů nepřenese.
* ``trust_env=False``: žádné systémové proxy, žádné ``.netrc``.
"""

from __future__ import annotations

from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Final

import httpx

from nc_gateway.body import RequestBody
from nc_gateway.config import Settings
from nc_gateway.signing import sign

_ACCEPT_ENCODING: Final = "identity"  # tělo se předává beze změny, bez Content-Encoding


class CoreUnavailableError(RuntimeError):
    """Core neodpověděl (spojení, timeout, protokol) – gateway odpoví 502."""


def _blocking_cookie_jar() -> CookieJar:
    return CookieJar(policy=DefaultCookiePolicy(allowed_domains=[]))


class CoreClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        if transport is None and settings.core_uds is not None:
            transport = httpx.AsyncHTTPTransport(uds=settings.core_uds)
        self._base = httpx.URL(settings.core_url)
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(settings.core_timeout_seconds, connect=5.0),
            follow_redirects=False,
            trust_env=False,
            cookies=_blocking_cookie_jar(),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def build(
        self,
        method: str,
        path: str,
        *,
        query: str = "",
        body: bytes = b"",
        headers: dict[str, str] | None = None,
        access_token: str | None = None,
        client_ip: str,
        request_id: str,
        read_timeout: float | None = None,
        stream_body: RequestBody | None = None,
    ) -> httpx.Request:
        target = path + (f"?{query}" if query else "")
        url = self._base.copy_with(raw_path=target.encode("ascii"))
        out_headers: dict[str, str] = dict(headers or {})
        out_headers["Accept-Encoding"] = _ACCEPT_ENCODING
        out_headers["X-Request-Id"] = request_id
        authorization = f"Bearer {access_token}" if access_token else None
        if authorization:
            out_headers["Authorization"] = authorization
        if stream_body is not None:
            # streamovaný upload: tělo jde ze (spooled) souboru, hash je spočítaný při příjmu
            out_headers["Content-Length"] = str(stream_body.length)
            request = httpx.Request(method.upper(), url, content=stream_body.chunks(), headers=out_headers)
        else:
            request = httpx.Request(method.upper(), url, content=body, headers=out_headers)
        if read_timeout is not None:
            # např. SSE: read timeout = idle limit (mezera mezi bloky), ne délka celé odpovědi
            timeout = httpx.Timeout(self._settings.core_timeout_seconds, connect=5.0, read=read_timeout)
            request.extensions["timeout"] = timeout.as_dict()
        raw_path, _, raw_query = request.url.raw_path.decode("ascii").partition("?")
        request.headers.update(
            sign(
                key_id=self._settings.hmac_key_id,
                secret=self._settings.hmac_secret,
                method=request.method,
                raw_path=raw_path,
                query_string=raw_query,
                client_ip=client_ip,
                body=body,
                authorization=authorization,
                body_sha256=stream_body.sha256 if stream_body is not None else None,
            )
        )
        return request

    async def send(self, request: httpx.Request, *, stream: bool = False) -> httpx.Response:
        try:
            return await self._client.send(request, stream=stream)
        except httpx.TransportError as exc:
            raise CoreUnavailableError(type(exc).__name__) from exc

    async def call(
        self,
        method: str,
        path: str,
        *,
        json_body: bytes | None = None,
        access_token: str | None = None,
        client_ip: str,
        request_id: str,
    ) -> httpx.Response:
        """Interní volání gateway (auth, bezpečnostní události) – tělo se načte celé."""
        headers = {"Accept": "application/json"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        request = self.build(
            method,
            path,
            body=json_body or b"",
            headers=headers,
            access_token=access_token,
            client_ip=client_ip,
            request_id=request_id,
        )
        response = await self.send(request)
        return response
