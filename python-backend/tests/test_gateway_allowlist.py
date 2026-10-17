"""F3.5: the committed gateway allowlist matches app/core/exposure.py."""

import json

from scripts.export_gateway_allowlist import TARGET, gateway_routes, render


def test_committed_allowlist_is_current():
    assert TARGET.exists(), "run: python -m scripts.export_gateway_allowlist"
    assert TARGET.read_text(encoding="utf-8") == render()


def test_allowlist_contains_no_admin_or_system_routes():
    document = json.loads(TARGET.read_text(encoding="utf-8"))
    assert document["zone"] == "gateway"
    assert document["count"] == len(document["routes"]) == len(gateway_routes())
    for route in document["routes"]:
        path = route["path"]
        assert path.startswith("/api/v1/"), route
        assert not path.startswith(("/api/v1/admin", "/api/v1/metrics", "/api/v1/health", "/api/v1/ready")), route
        assert path not in ("/api/v1/", "/api/v1/alive"), route
