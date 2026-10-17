"""Single source of truth for the client address behind trusted reverse proxies (SA-05).

The TCP peer is authoritative. ``X-Forwarded-For`` / ``X-Forwarded-Proto`` are
honoured only when the peer is one of ``TRUSTED_PROXY_IPS`` (explicit addresses or
CIDRs; never ``*``). The forwarded chain is then read right to left and the first
address that is *not* a trusted proxy is the client, so a value a client prepends
itself can never be selected. Anything unparsable falls back to the peer.

Uvicorn's own proxy-header handling must stay off (``--no-proxy-headers``) so the
decision is made here, identically under Docker, systemd and tests.

Future Gateway → Core hop: the gateway will forward the client address in a
signed header and Core will trust it only on the gateway socket. That is a
separate phase (docs/security/SECURITY_ARCHITECTURE.md §4.5/§6) and is not
implemented here.
"""

from __future__ import annotations

from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network
from typing import Iterable

from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send

IPNetwork = IPv4Network | IPv6Network
IPAddress = IPv4Address | IPv6Address

_MAX_FORWARDED_HOPS = 20
_FORWARDED_PROTOS = frozenset({"http", "https"})


class TrustedProxyConfigError(ValueError):
    pass


def parse_trusted_proxies(raw: str) -> tuple[IPNetwork, ...]:
    """Parse ``TRUSTED_PROXY_IPS`` (comma separated IPs/CIDRs). Empty = trust nobody."""
    networks: list[IPNetwork] = []
    for entry in (part.strip() for part in raw.split(",")):
        if not entry:
            continue
        if entry == "*":
            raise TrustedProxyConfigError("TRUSTED_PROXY_IPS must list explicit proxies; '*' is not allowed.")
        try:
            network = ip_network(entry, strict=False)
        except ValueError as exc:
            raise TrustedProxyConfigError(f"TRUSTED_PROXY_IPS entry {entry!r} is not an IP address or CIDR.") from exc
        if network.prefixlen == 0:
            raise TrustedProxyConfigError(
                f"TRUSTED_PROXY_IPS entry {entry!r} would trust every address."
            )
        networks.append(network)
    return tuple(networks)


def parse_ip(value: str | None) -> IPAddress | None:
    """Parse one address as found in a peer tuple or X-Forwarded-For element.

    Accepts ``1.2.3.4``, ``1.2.3.4:5678``, ``2001:db8::1``, ``[2001:db8::1]`` and
    ``[2001:db8::1]:443``; IPv4-mapped IPv6 is normalised to IPv4.
    """
    if not value:
        return None
    candidate = value.strip()
    if candidate.startswith("["):
        end = candidate.find("]")
        if end == -1:
            return None
        candidate = candidate[1:end]
    elif candidate.count(":") == 1:
        candidate = candidate.split(":", 1)[0]
    try:
        address = ip_address(candidate)
    except ValueError:
        return None
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _is_trusted(address: IPAddress, trusted: Iterable[IPNetwork]) -> bool:
    return any(address.version == network.version and address in network for network in trusted)


def resolve_client_ip(
    peer: str | None,
    forwarded_for: list[str],
    trusted: tuple[IPNetwork, ...],
) -> str | None:
    """Return the client address for a request arriving from ``peer``."""
    peer_address = parse_ip(peer)
    if peer_address is None:
        return peer
    if not trusted or not _is_trusted(peer_address, trusted):
        return str(peer_address)

    hops = [hop for header in forwarded_for for hop in header.split(",")]
    if not hops or len(hops) > _MAX_FORWARDED_HOPS:
        return str(peer_address)
    for hop in reversed(hops):
        address = parse_ip(hop)
        if address is None:
            # A malformed element breaks the chain of trust: stop at the proxy.
            return str(peer_address)
        if not _is_trusted(address, trusted):
            return str(address)
    # Every hop is a trusted proxy (e.g. health check from the proxy itself).
    return str(peer_address)


def client_ip(connection: HTTPConnection) -> str | None:
    """Client address for logging, auditing and rate limiting.

    TrustedProxyMiddleware has already rewritten ``scope["client"]``; use this
    helper instead of reading headers anywhere else.
    """
    return connection.client.host if connection.client else None


class TrustedProxyMiddleware:
    """Rewrite ``scope["client"]`` and ``scope["scheme"]`` from trusted proxies only.

    Must be the outermost middleware so every later consumer (rate limiter,
    audit, HTTPS redirect, logging) sees the resolved values.
    """

    def __init__(self, app: ASGIApp, *, trusted_proxies: tuple[IPNetwork, ...]) -> None:
        self.app = app
        self.trusted_proxies = trusted_proxies

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            peer = scope.get("client")
            peer_host = peer[0] if peer else None
            forwarded_for: list[str] = []
            forwarded_proto: str | None = None
            for name, value in scope.get("headers", []):
                if name == b"x-forwarded-for":
                    forwarded_for.append(value.decode("latin-1"))
                elif name == b"x-forwarded-proto":
                    forwarded_proto = value.decode("latin-1").strip().lower()

            peer_address = parse_ip(peer_host)
            from_trusted_proxy = (
                peer_address is not None
                and bool(self.trusted_proxies)
                and _is_trusted(peer_address, self.trusted_proxies)
            )
            resolved = resolve_client_ip(peer_host, forwarded_for, self.trusted_proxies)
            if resolved is not None and peer is not None:
                scope["client"] = (resolved, peer[1])
            if from_trusted_proxy and forwarded_proto in _FORWARDED_PROTOS and scope["type"] == "http":
                scope["scheme"] = forwarded_proto
        await self.app(scope, receive, send)
