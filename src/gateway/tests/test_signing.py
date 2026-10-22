"""HMAC podpis gateway → core (GATEWAY_CORE_CONTRACT kap. 3 a 5)."""

from __future__ import annotations

import hashlib

import httpx

from nc_gateway.core_client import CoreClient
from nc_gateway.signing import canonical_string, new_nonce, sign
from tests.conftest import HMAC_KID, HMAC_SECRET, contract_signature, verify_contract_signature

VECTOR_SIGNATURE = "834a1b955a9ac25a806c4c77dc4eeda33381fa89c2633ca6d9791251d80ef91f"


def test_signature_matches_published_test_vector() -> None:
    headers = sign(
        key_id="gw-test",
        secret=b"0123456789abcdef0123456789abcdef",
        method="POST",
        raw_path="/api/v1/org/users",
        query_string="",
        client_ip="203.0.113.10",
        body=b'{"email":"novak@firma.cz"}',
        authorization="Bearer eyJ.test.token",
        timestamp=1792224000,
        nonce="AAAAAAAAAAAAAAAAAAAAAAAA",
    )
    assert headers["X-NC-Gateway-Sig"] == VECTOR_SIGNATURE
    assert headers["X-NC-Gateway-Key"] == "gw-test"
    assert headers["X-NC-Gateway-Ts"] == "1792224000"
    assert headers["X-NC-Gateway-Nonce"] == "AAAAAAAAAAAAAAAAAAAAAAAA"
    assert headers["X-NC-Client-IP"] == "203.0.113.10"


def test_independent_contract_implementation_agrees_with_vector() -> None:
    """Testovací ověřovač (fake core) musí sám dát vektor – jinak by testy nic nedokazovaly."""
    fields = [
        "NC-GW-1",
        "gw-test",
        "1792224000",
        "AAAAAAAAAAAAAAAAAAAAAAAA",
        "POST",
        "/api/v1/org/users",
        "",
        "203.0.113.10",
        hashlib.sha256(b'{"email":"novak@firma.cz"}').hexdigest(),
        hashlib.sha256(b"Bearer eyJ.test.token").hexdigest(),
    ]
    assert contract_signature(b"0123456789abcdef0123456789abcdef", fields) == VECTOR_SIGNATURE


def test_canonical_string_has_ten_fields_without_trailing_newline() -> None:
    canonical = canonical_string(
        key_id="k",
        timestamp="1",
        nonce="n" * 16,
        method="get",
        raw_path="/api/v1/cases",
        query_string="a=1",
        client_ip="192.0.2.1",
        body=b"",
        authorization=None,
    )
    parts = canonical.split(b"\n")
    assert len(parts) == 10
    assert parts[4] == b"GET"
    assert not canonical.endswith(b"\n")
    empty = hashlib.sha256(b"").hexdigest().encode()
    assert parts[8] == empty and parts[9] == empty


def test_nonce_is_unique_and_matches_contract_format() -> None:
    nonces = {new_nonce() for _ in range(1000)}
    assert len(nonces) == 1000
    assert all(16 <= len(n) <= 128 and all(c.isalnum() or c in "-_" for c in n) for n in nonces)


def test_core_client_signs_final_url_and_each_request_gets_fresh_nonce(settings) -> None:  # type: ignore[no-untyped-def]
    client = CoreClient(settings, httpx.MockTransport(lambda r: httpx.Response(200)))
    keys = {HMAC_KID: HMAC_SECRET.encode()}
    seen: set[str] = set()
    for _ in range(3):
        request = client.build(
            "GET",
            "/api/v1/cases",
            query="q=a%20b&x=|",  # httpx může query překódovat – podpis musí krýt finální bajty
            access_token="tok",
            client_ip="203.0.113.7",
            request_id="rid",
        )
        assert verify_contract_signature(request, keys, seen) is None
    assert len(seen) == 3
