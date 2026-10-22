"""Konfigurace gateway – výhradně z proměnných prostředí, fail-fast.

Kontrakt: docs/security/NC-007_STAGE1_CONTRACT.md kap. 3, 5 a 8.

Zásady:

* Žádné skryté fallbacky. Klíče, URL core, Redis, veřejný origin i cesta
  k allowlistu jsou povinné ve **všech** prostředích (i v developmentu).
  Výchozí hodnoty mají jen ne-tajné provozní parametry, které kontrakt
  sám definuje (timeouty session, limity).
* Tajné hodnoty (``NC_GATEWAY_HMAC_KEY``, ``NC_BFF_SESSION_KEYS``) jdou předat
  i přes systemd ``LoadCredential``: když proměnná chybí a existuje soubor
  ``$CREDENTIALS_DIRECTORY/<JMÉNO>``, načte se z něj. Nic jiného se nezkouší.
* Mimo ``NC_ENV=development`` musí být ``NC_BFF_PUBLIC_ORIGIN`` ``https://``
  a volba ``NC_BFF_DEV_INSECURE_COOKIE`` je zakázaná.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final
from urllib.parse import unquote, urlsplit

DEVELOPMENT: Final = "development"
KNOWN_ENVS: Final = frozenset({"development", "test", "staging", "production"})

_KID_RE: Final = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
_MIN_HMAC_SECRET_BYTES: Final = 32
_SESSION_KEY_BYTES: Final = 32  # AES-256
TRUSTED_PROXY_UNIX: Final = "unix"


class ConfigError(ValueError):
    """Neplatná nebo chybějící konfigurace – proces nesmí nastartovat."""


@dataclass(frozen=True)
class RateLimit:
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class Settings:
    env: str
    public_origin: str
    core_url: str
    core_uds: str | None
    hmac_key_id: str
    hmac_secret: bytes = field(repr=False)
    # (kid, 32 B klíč); první položka šifruje, ostatní jen dešifrují
    session_keys: tuple[tuple[str, bytes], ...] = field(repr=False)
    redis_url: str = field(repr=False)
    allowlist_path: Path
    trusted_proxy: str | None = None
    dev_insecure_cookie: bool = False
    idle_timeout_seconds: int = 30 * 60
    absolute_timeout_seconds: int = 12 * 60 * 60
    listen_host: str = "127.0.0.1"
    listen_port: int = 8090
    core_timeout_seconds: float = 30.0
    # SSE (text/event-stream): místo krátkého read timeoutu jen idle limit spojení
    sse_idle_timeout_seconds: float = 300.0
    upload_routes: tuple[tuple[str, str], ...] | None = None
    json_body_limit: int = 256 * 1024
    multipart_body_limit: int = 25 * 1024 * 1024
    login_body_limit: int = 16 * 1024
    refresh_leeway_seconds: int = 60
    rate_session: RateLimit = RateLimit(300, 60)
    rate_ip: RateLimit = RateLimit(600, 60)
    rate_login_ip: RateLimit = RateLimit(20, 5 * 60)
    rate_login_email_failures: RateLimit = RateLimit(10, 15 * 60)
    events_flush_seconds: float = 2.0
    events_batch_size: int = 50

    @property
    def is_development(self) -> bool:
        return self.env == DEVELOPMENT

    @property
    def cookie_name(self) -> str:
        return "nc_sid_dev" if self.dev_insecure_cookie else "__Host-nc_sid"

    @property
    def cookie_secure(self) -> bool:
        return not self.dev_insecure_cookie


def _read(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if value is not None and value.strip() != "":
        return value.strip()
    cred_dir = env.get("CREDENTIALS_DIRECTORY")
    if cred_dir:
        candidate = Path(cred_dir) / name
        if candidate.is_file():
            content = candidate.read_text(encoding="utf-8").strip()
            return content or None
    return None


def _required(env: Mapping[str, str], name: str) -> str:
    value = _read(env, name)
    if value is None:
        raise ConfigError(f"Chybí povinná proměnná {name}.")
    return value


def _int(env: Mapping[str, str], name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = _read(env, name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} musí být celé číslo.") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} musí být v rozsahu {minimum}–{maximum}.")
    return value


def parse_hmac_key(raw: str) -> tuple[str, bytes]:
    """``NC_GATEWAY_HMAC_KEY``: ``kid:secret``, secret ≥ 32 B (UTF-8)."""
    if "," in raw:
        raise ConfigError("NC_GATEWAY_HMAC_KEY obsahuje právě jeden klíč 'kid:secret'.")
    kid, sep, secret = raw.partition(":")
    kid, secret = kid.strip(), secret.strip()
    if not sep or not _KID_RE.match(kid):
        raise ConfigError("NC_GATEWAY_HMAC_KEY musí mít tvar 'kid:secret' s kid [A-Za-z0-9._-]{1,32}.")
    secret_bytes = secret.encode("utf-8")
    if len(secret_bytes) < _MIN_HMAC_SECRET_BYTES:
        raise ConfigError(f"NC_GATEWAY_HMAC_KEY: secret je kratší než {_MIN_HMAC_SECRET_BYTES} B.")
    return kid, secret_bytes


def parse_session_keys(raw: str) -> tuple[tuple[str, bytes], ...]:
    """``NC_BFF_SESSION_KEYS``: ``kid:base64(32 B)[,kid:base64(32 B)]``."""
    keys: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    for entry in (part.strip() for part in raw.split(",")):
        if not entry:
            continue
        kid, sep, b64 = entry.partition(":")
        kid, b64 = kid.strip(), b64.strip()
        if not sep or not _KID_RE.match(kid):
            raise ConfigError("NC_BFF_SESSION_KEYS: položky musí mít tvar 'kid:base64(32 B)'.")
        if kid in seen:
            raise ConfigError(f"NC_BFF_SESSION_KEYS: kid {kid!r} je uveden dvakrát.")
        try:
            # standardní i URL-safe abeceda, doplnění '=' je volitelné
            normalized = b64.replace("-", "+").replace("_", "/").rstrip("=")
            key = base64.b64decode(normalized + "=" * (-len(normalized) % 4), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ConfigError(f"NC_BFF_SESSION_KEYS: klíč {kid!r} není platné base64.") from exc
        if len(key) != _SESSION_KEY_BYTES:
            raise ConfigError(
                f"NC_BFF_SESSION_KEYS: klíč {kid!r} má {len(key)} B, musí mít přesně {_SESSION_KEY_BYTES} B."
            )
        seen.add(kid)
        keys.append((kid, key))
    if not keys:
        raise ConfigError("NC_BFF_SESSION_KEYS neobsahuje žádný klíč.")
    return tuple(keys)


def _parse_origin(raw: str, *, development: bool) -> str:
    parts = urlsplit(raw)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise ConfigError("NC_BFF_PUBLIC_ORIGIN musí být origin ve tvaru https://host[:port].")
    if parts.path not in ("", "/") or parts.query or parts.fragment or parts.username or parts.password:
        raise ConfigError("NC_BFF_PUBLIC_ORIGIN nesmí obsahovat cestu, query ani přihlašovací údaje.")
    if parts.scheme != "https" and not development:
        raise ConfigError("NC_BFF_PUBLIC_ORIGIN musí mimo development začínat https://.")
    return f"{parts.scheme}://{parts.netloc}".lower()


def _parse_core_url(raw: str) -> tuple[str, str | None]:
    parts = urlsplit(raw)
    if parts.scheme == "http+unix":
        # http+unix:///run/nc/api.sock  nebo  http+unix://%2Frun%2Fnc%2Fapi.sock
        socket_path = unquote(parts.netloc) if parts.netloc else parts.path
        if not socket_path.startswith("/"):
            raise ConfigError("NC_BFF_CORE_URL http+unix:// musí obsahovat absolutní cestu k socketu.")
        return "http://core.internal", socket_path
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ConfigError("NC_BFF_CORE_URL musí být http://, https:// nebo http+unix://.")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ConfigError("NC_BFF_CORE_URL nesmí obsahovat cestu ani query (gateway posílá /api/v1/...).")
    return f"{parts.scheme}://{parts.netloc}", None


def _parse_trusted_proxy(raw: str | None) -> str | None:
    if raw is None:
        return None
    if raw == TRUSTED_PROXY_UNIX:
        return raw
    if "," in raw:
        raise ConfigError("NC_BFF_TRUSTED_PROXY je právě jedna adresa (lokální nginx).")
    try:
        address = ipaddress.ip_address(raw)
    except ValueError as exc:
        raise ConfigError("NC_BFF_TRUSTED_PROXY musí být IP adresa nebo 'unix'.") from exc
    mapped = getattr(address, "ipv4_mapped", None)
    return str(mapped or address)


def _parse_upload_routes(raw: str | None) -> tuple[tuple[str, str], ...] | None:
    if raw is None:
        return None
    routes: list[tuple[str, str]] = []
    for entry in (part.strip() for part in raw.split(",")):
        if not entry:
            continue
        method, _, path = entry.partition(" ")
        if method.upper() not in ("POST", "PUT", "PATCH") or not path.strip().startswith("/api/v1/"):
            raise ConfigError("NC_BFF_UPLOAD_ROUTES: položky 'POST /api/v1/...'.")
        routes.append((method.upper(), path.strip()))
    return tuple(routes)


def _flag(env: Mapping[str, str], name: str) -> bool:
    raw = _read(env, name)
    if raw is None or raw in ("0", "false", "False"):
        return False
    if raw in ("1", "true", "True"):
        return True
    raise ConfigError(f"{name} musí být 0 nebo 1.")


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Načte a zvaliduje konfiguraci. Při jakékoli chybě vyhodí :class:`ConfigError`."""
    source: Mapping[str, str] = os.environ if env is None else env

    nc_env = _required(source, "NC_ENV").lower()
    if nc_env not in KNOWN_ENVS:
        raise ConfigError(f"NC_ENV musí být jedno z: {', '.join(sorted(KNOWN_ENVS))}.")
    development = nc_env == DEVELOPMENT

    dev_insecure_cookie = _flag(source, "NC_BFF_DEV_INSECURE_COOKIE")
    if dev_insecure_cookie and not development:
        raise ConfigError("NC_BFF_DEV_INSECURE_COOKIE je povolené jen pro NC_ENV=development.")

    public_origin = _parse_origin(_required(source, "NC_BFF_PUBLIC_ORIGIN"), development=development)
    if public_origin.startswith("http://") and not dev_insecure_cookie:
        # Prohlížeč přes http neuloží cookie s atributem Secure – vývoj přes Vite proxy
        # (http://localhost:5173) jde jen s explicitní NC_BFF_DEV_INSECURE_COOKIE=1.
        raise ConfigError("NC_BFF_PUBLIC_ORIGIN http:// vyžaduje NC_ENV=development a NC_BFF_DEV_INSECURE_COOKIE=1.")
    core_url, core_uds = _parse_core_url(_required(source, "NC_BFF_CORE_URL"))
    hmac_key_id, hmac_secret = parse_hmac_key(_required(source, "NC_GATEWAY_HMAC_KEY"))
    session_keys = parse_session_keys(_required(source, "NC_BFF_SESSION_KEYS"))
    redis_url = _required(source, "NC_BFF_REDIS_URL")
    if not redis_url.startswith(("redis://", "rediss://", "unix://")):
        raise ConfigError("NC_BFF_REDIS_URL musí být redis://, rediss:// nebo unix://.")

    allowlist_path = Path(_required(source, "NC_BFF_ALLOWLIST_PATH"))
    if not allowlist_path.is_file():
        raise ConfigError(f"NC_BFF_ALLOWLIST_PATH: soubor {allowlist_path} neexistuje.")

    idle = _int(source, "NC_BFF_IDLE_TIMEOUT_SECONDS", 30 * 60, minimum=60, maximum=24 * 3600)
    absolute = _int(source, "NC_BFF_ABSOLUTE_TIMEOUT_SECONDS", 12 * 3600, minimum=300, maximum=7 * 24 * 3600)
    if idle > absolute:
        raise ConfigError("NC_BFF_IDLE_TIMEOUT_SECONDS nesmí být delší než NC_BFF_ABSOLUTE_TIMEOUT_SECONDS.")

    return Settings(
        env=nc_env,
        public_origin=public_origin,
        core_url=core_url,
        core_uds=core_uds,
        hmac_key_id=hmac_key_id,
        hmac_secret=hmac_secret,
        session_keys=session_keys,
        redis_url=redis_url,
        allowlist_path=allowlist_path,
        trusted_proxy=_parse_trusted_proxy(_read(source, "NC_BFF_TRUSTED_PROXY")),
        dev_insecure_cookie=dev_insecure_cookie,
        idle_timeout_seconds=idle,
        absolute_timeout_seconds=absolute,
        listen_host=_read(source, "NC_BFF_LISTEN_HOST") or "127.0.0.1",
        listen_port=_int(source, "NC_BFF_LISTEN_PORT", 8090, minimum=1, maximum=65535),
        core_timeout_seconds=float(_int(source, "NC_BFF_CORE_TIMEOUT_SECONDS", 30, minimum=1, maximum=600)),
        sse_idle_timeout_seconds=float(_int(source, "NC_BFF_SSE_IDLE_TIMEOUT_SECONDS", 300, minimum=10, maximum=3600)),
        upload_routes=_parse_upload_routes(_read(source, "NC_BFF_UPLOAD_ROUTES")),
    )
