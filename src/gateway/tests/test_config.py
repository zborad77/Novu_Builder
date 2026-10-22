"""Fail-fast konfigurace (kontrakt NC-007 kap. 3 a 8)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from nc_gateway.allowlist import Allowlist, AllowlistError
from nc_gateway.config import ConfigError, load_settings
from tests.conftest import HMAC_SECRET, base_env

REPO_ALLOWLIST = Path(__file__).resolve().parents[3] / "docs" / "security" / "gateway-allowlist.json"


def test_valid_production_config_loads(allowlist_file: Path) -> None:
    settings = load_settings(base_env(allowlist_file))
    assert settings.cookie_name == "__Host-nc_sid"
    assert settings.cookie_secure
    assert settings.idle_timeout_seconds == 1800
    assert settings.absolute_timeout_seconds == 43200
    assert HMAC_SECRET not in repr(settings)  # tajné hodnoty se nevypisují


@pytest.mark.parametrize(
    "missing",
    [
        "NC_ENV",
        "NC_BFF_PUBLIC_ORIGIN",
        "NC_BFF_CORE_URL",
        "NC_GATEWAY_HMAC_KEY",
        "NC_BFF_SESSION_KEYS",
        "NC_BFF_REDIS_URL",
        "NC_BFF_ALLOWLIST_PATH",
    ],
)
@pytest.mark.parametrize("env_name", ["production", "development"])
def test_missing_required_variable_fails(allowlist_file: Path, missing: str, env_name: str) -> None:
    env = base_env(allowlist_file, NC_ENV=env_name)
    env.pop(missing)
    with pytest.raises(ConfigError):
        load_settings(env)


def test_short_hmac_key_fails(allowlist_file: Path) -> None:
    with pytest.raises(ConfigError, match="32"):
        load_settings(base_env(allowlist_file, NC_GATEWAY_HMAC_KEY="gw:" + "x" * 31))


def test_hmac_key_without_kid_fails(allowlist_file: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(base_env(allowlist_file, NC_GATEWAY_HMAC_KEY="x" * 40))


@pytest.mark.parametrize("length", [16, 31, 33])
def test_session_key_must_be_exactly_32_bytes(allowlist_file: Path, length: int) -> None:
    key = base64.b64encode(b"k" * length).decode()
    with pytest.raises(ConfigError):
        load_settings(base_env(allowlist_file, NC_BFF_SESSION_KEYS=f"k1:{key}"))


def test_session_key_invalid_base64_fails(allowlist_file: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(base_env(allowlist_file, NC_BFF_SESSION_KEYS="k1:@@@not-base64@@@"))


def test_duplicate_session_kid_fails(allowlist_file: Path) -> None:
    key = base64.b64encode(b"k" * 32).decode()
    with pytest.raises(ConfigError):
        load_settings(base_env(allowlist_file, NC_BFF_SESSION_KEYS=f"k1:{key},k1:{key}"))


@pytest.mark.parametrize("env_name", ["production", "staging", "test"])
def test_http_origin_outside_development_fails(allowlist_file: Path, env_name: str) -> None:
    with pytest.raises(ConfigError, match="https"):
        load_settings(base_env(allowlist_file, NC_ENV=env_name, NC_BFF_PUBLIC_ORIGIN="http://nc.example.test"))


def test_http_origin_allowed_in_development_with_insecure_dev_cookie(allowlist_file: Path) -> None:
    settings = load_settings(
        base_env(
            allowlist_file,
            NC_ENV="development",
            NC_BFF_PUBLIC_ORIGIN="http://localhost:5173",
            NC_BFF_DEV_INSECURE_COOKIE="1",
        )
    )
    assert settings.public_origin == "http://localhost:5173"
    assert settings.cookie_name == "nc_sid_dev"


def test_http_origin_in_development_without_insecure_cookie_fails(allowlist_file: Path) -> None:
    with pytest.raises(ConfigError, match="NC_BFF_DEV_INSECURE_COOKIE"):
        load_settings(base_env(allowlist_file, NC_ENV="development", NC_BFF_PUBLIC_ORIGIN="http://localhost:5173"))


def test_https_origin_in_development_keeps_secure_host_cookie(allowlist_file: Path) -> None:
    settings = load_settings(base_env(allowlist_file, NC_ENV="development"))
    assert settings.cookie_name == "__Host-nc_sid" and settings.cookie_secure


def test_origin_with_path_fails(allowlist_file: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(base_env(allowlist_file, NC_BFF_PUBLIC_ORIGIN="https://nc.example.test/app"))


@pytest.mark.parametrize("env_name", ["production", "staging", "test"])
def test_dev_insecure_cookie_outside_development_fails(allowlist_file: Path, env_name: str) -> None:
    with pytest.raises(ConfigError, match="development"):
        load_settings(base_env(allowlist_file, NC_ENV=env_name, NC_BFF_DEV_INSECURE_COOKIE="1"))


def test_dev_insecure_cookie_in_development(allowlist_file: Path) -> None:
    settings = load_settings(
        base_env(
            allowlist_file,
            NC_ENV="development",
            NC_BFF_DEV_INSECURE_COOKIE="1",
            NC_BFF_PUBLIC_ORIGIN="http://localhost:5173",
        )
    )
    assert settings.cookie_name == "nc_sid_dev"
    assert not settings.cookie_secure


def test_unknown_env_fails(allowlist_file: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(base_env(allowlist_file, NC_ENV="prod"))


def test_missing_allowlist_file_fails(allowlist_file: Path, tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(base_env(allowlist_file, NC_BFF_ALLOWLIST_PATH=str(tmp_path / "missing.json")))


def test_trusted_proxy_must_be_single_ip(allowlist_file: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(base_env(allowlist_file, NC_BFF_TRUSTED_PROXY="10.0.0.1,10.0.0.2"))
    with pytest.raises(ConfigError):
        load_settings(base_env(allowlist_file, NC_BFF_TRUSTED_PROXY="nginx"))


def test_core_url_variants(allowlist_file: Path) -> None:
    uds = load_settings(base_env(allowlist_file, NC_BFF_CORE_URL="http+unix:///run/nc/api-gateway.sock"))
    assert uds.core_uds == "/run/nc/api-gateway.sock"
    with pytest.raises(ConfigError):
        load_settings(base_env(allowlist_file, NC_BFF_CORE_URL="http://core.test/api/v1"))
    with pytest.raises(ConfigError):
        load_settings(base_env(allowlist_file, NC_BFF_CORE_URL="ftp://core.test"))


def test_secret_from_systemd_credentials_directory(allowlist_file: Path, tmp_path: Path) -> None:
    creds = tmp_path / "creds"
    creds.mkdir()
    (creds / "NC_GATEWAY_HMAC_KEY").write_text("gw-cred:" + "c" * 40 + "\n", encoding="utf-8")
    env = base_env(allowlist_file, CREDENTIALS_DIRECTORY=str(creds))
    env.pop("NC_GATEWAY_HMAC_KEY")
    assert load_settings(env).hmac_key_id == "gw-cred"


# ── allowlist při startu ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not json",
        json.dumps({"routes": []}),
        json.dumps({"zone": "desktop", "routes": [{"method": "GET", "path": "/api/v1/x"}]}),
    ],
)
def test_unusable_allowlist_fails(tmp_path: Path, content: str) -> None:
    path = tmp_path / "allowlist.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(AllowlistError):
        Allowlist.load(path)


def test_allowlist_only_auth_and_internal_is_empty(tmp_path: Path) -> None:
    path = tmp_path / "allowlist.json"
    path.write_text(
        json.dumps(
            {
                "routes": [
                    {"method": "POST", "path": "/api/v1/auth/login"},
                    {"method": "POST", "path": "/api/v1/internal/security-events"},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AllowlistError):
        Allowlist.load(path)


@pytest.mark.skipif(not REPO_ALLOWLIST.is_file(), reason="docs/security/gateway-allowlist.json v repozitáři chybí")
def test_repository_allowlist_loads_and_excludes_auth_internal_admin() -> None:
    allowlist = Allowlist.load(REPO_ALLOWLIST)
    paths = {route.path for route in allowlist.routes}
    assert paths
    assert not any(p.startswith(("/api/v1/auth/", "/api/v1/internal/", "/api/v1/admin/")) for p in paths)
    assert allowlist.match("GET", "/api/v1/cases") is not None
    assert allowlist.match("POST", "/api/v1/auth/login") is None
