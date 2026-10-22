"""Allowlist a validace segmentů (kontrakt NC-007 kap. 2.1) – bez Redisu."""

from __future__ import annotations

import pytest

from nc_gateway.allowlist import Allowlist, split_safe_path
from tests.conftest import TEST_ALLOWLIST


@pytest.fixture
def allowlist() -> Allowlist:
    return Allowlist((r["method"], r["path"]) for r in TEST_ALLOWLIST["routes"])


def test_known_route_matches(allowlist: Allowlist) -> None:
    route = allowlist.match("GET", "/api/v1/cases/abc-123")
    assert route is not None and route.path == "/api/v1/cases/{case_id}"


def test_method_must_match(allowlist: Allowlist) -> None:
    assert allowlist.match("DELETE", "/api/v1/cases/abc") is None


@pytest.mark.parametrize("method", ["HEAD", "OPTIONS", "TRACE", "CONNECT", "PROPFIND"])
def test_forbidden_methods(allowlist: Allowlist, method: str) -> None:
    assert allowlist.match(method, "/api/v1/cases") is None


@pytest.mark.parametrize(
    "path",
    ["/api/v1/auth/login", "/api/v1/auth/me", "/api/v1/internal/security-events", "/api/v1/auth/sessions/x"],
)
def test_auth_and_internal_are_excluded(allowlist: Allowlist, path: str) -> None:
    for method in ("GET", "POST", "DELETE"):
        assert allowlist.match(method, path) is None


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/cases/..",
        "/api/v1/cases/.",
        "/api/v1/cases/a%2Fb",
        "/api/v1/cases/a%2fb",
        "/api/v1/cases/a%5Cb",
        "/api/v1/cases/a%00",
        "/api/v1/cases/a\\b",
        "/api/v1/cases//",
        "/api/v1/cases/",
        "/api/v1//cases",
        "/api/v1/cases/%2e%2e",
        "/api/v1/cases/a%20b",
        "/api/v1/cases/" + "a" * 129,
        "/api/v1/cases/a b",
    ],
)
def test_unsafe_segments_rejected(allowlist: Allowlist, path: str) -> None:
    assert allowlist.match("GET", path) is None


def test_parameter_is_exactly_one_segment(allowlist: Allowlist) -> None:
    assert allowlist.match("GET", "/api/v1/cases/a/b") is None
    assert allowlist.match("GET", "/api/v1/cases/" + "a" * 128) is not None


def test_split_safe_path_accepts_unreserved() -> None:
    assert split_safe_path("/api/v1/x-y_z.~1") == ["api", "v1", "x-y_z.~1"]


def test_default_upload_routes(allowlist: Allowlist) -> None:
    images = allowlist.match("POST", "/api/v1/cases/c1/images")
    assert images is not None and allowlist.is_upload(images)
    cases = allowlist.match("POST", "/api/v1/cases")
    assert cases is not None and not allowlist.is_upload(cases)
