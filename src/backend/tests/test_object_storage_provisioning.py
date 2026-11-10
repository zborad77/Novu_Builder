#
# Copyright (c) 2026 Novusion
# Website: https://novusion.com
# Contact: info@novusion.com
#
# Author: Pavel Dostál
# Project: NovuBuilder
# Module: backend tests / deploy
# Description: TK-00046 - object store (Garage) is installed and started by nc-provision
# Created: 2026-11-08
#
"""TK-00046 (T6.1): objektové úložiště běží na serveru a instaluje ho nc-provision.

Statické kontroly deploy/linux (běží i na Windows v test.bat). Chování na
skutečném systému ověřuje deploy/linux/tests/validate-configs.sh a VM (T6.2).
"""

import re
import sys
import types
from unittest.mock import patch

from app.platform.paths import repo_root
from app.platform.storage import s3_photo_storage as s3_storage_mod

DEPLOY = repo_root() / "deploy" / "linux"
PROVISION = DEPLOY / "provision" / "nc-provision"


def _read(path):
    return path.read_text(encoding="utf-8")


def _bash_function(source: str, name: str) -> str:
    start = source.index(f"\n{name}() {{")
    end = source.index("\n}\n", start)
    return source[start:end]


def test_start_no_longer_needs_manual_object_storage_flag():
    provision = _read(PROVISION)
    start = _bash_function(provision, "cmd_start")
    assert "NC_OBJECT_STORAGE_READY" not in start
    assert "start_object_storage" in start
    # úložiště se spouští a ověřuje (health) před API
    assert start.index("start_object_storage") < start.index("nc-api@desktop.service")
    gate = _bash_function(provision, "start_object_storage")
    assert "systemctl enable --now --quiet nc-garage.service" in gate
    assert "garage_healthy" in gate
    assert re.search(r"^NC_OBJECT_STORAGE=garage$", provision, re.M)


def test_install_installs_object_store_with_verified_binary_bucket_and_key():
    provision = _read(PROVISION)
    install = _bash_function(provision, "cmd_install")
    assert "\n  install_object_storage\n" in install
    assert install.index("install_secrets") < install.index("install_object_storage") < install.index("install_app")
    binary = _bash_function(provision, "install_garage_binary")
    assert "sha256sum" in binary and "NC_GARAGE_SHA256" in binary
    assert "--proto '=https'" in binary
    storage = _bash_function(provision, "install_object_storage")
    for step in ("nc-gen-secrets\" --garage", "garage_layout", "garage_healthy", "garage_bucket_and_key",
                 "/etc/systemd/system/nc-garage.service", "$GARAGE_CONF"):
        assert step in storage, step
    keys = _bash_function(provision, "garage_bucket_and_key")
    # klíč generuje Garage (secret nikdy v argv), práva read/write jen na bucket, bez owner
    assert 'key create "$GARAGE_KEY_NAME"' in keys
    assert "key import" not in keys
    assert 'bucket allow --read --write --key "$id" "$NC_S3_BUCKET"' in keys
    assert "--owner" not in keys
    assert "put_core_secret S3_ACCESS_KEY_ID" in keys and "put_core_secret S3_SECRET_ACCESS_KEY" in keys


def test_garage_unit_is_loopback_only_and_takes_secrets_via_load_credential():
    unit = _read(DEPLOY / "systemd" / "nc-garage.service")
    lines = unit.splitlines()
    for expected in (
        "User=nc-garage",
        "ExecStart=/usr/local/bin/garage -c /etc/nc-garage/garage.toml server",
        "LoadCredential=GARAGE_RPC_SECRET:/etc/nc-garage/secrets/GARAGE_RPC_SECRET",
        "LoadCredential=GARAGE_ADMIN_TOKEN:/etc/nc-garage/secrets/GARAGE_ADMIN_TOKEN",
        "Environment=GARAGE_RPC_SECRET_FILE=%d/GARAGE_RPC_SECRET",
        "IPAddressDeny=any",
        "IPAddressAllow=localhost",
        "ProtectSystem=strict",
        "ReadWritePaths=/srv/novuconstruct/garage",
        "NoNewPrivileges=yes",
    ):
        assert expected in lines, expected
    assert not any(line.startswith(("EnvironmentFile=", "Environment=GARAGE_RPC_SECRET=")) for line in lines)
    assert "/etc/novuconstruct/secrets" not in unit
    for name in ("nc-api@.service", "nc-worker.service", "nc-offer-worker.service"):
        after = next(line for line in _read(DEPLOY / "systemd" / name).splitlines() if line.startswith("After="))
        assert "nc-garage.service" in after and "minio" not in after, name


def test_garage_config_binds_loopback_and_holds_no_secret():
    config = _read(DEPLOY / "garage" / "garage.toml")
    binds = re.findall(r'^\s*(?:rpc_bind_addr|rpc_public_addr|api_bind_addr)\s*=\s*"([^"]+)"', config, re.M)
    assert sorted(binds) == ["127.0.0.1:3900", "127.0.0.1:3901", "127.0.0.1:3901", "127.0.0.1:3903"]
    assert not re.search(r"^\s*(rpc_secret|admin_token|metrics_token)\s*=", config, re.M)
    assert re.search(r"^replication_factor = 1$", config, re.M)
    assert re.search(r"^metadata_fsync = true$", config, re.M)
    assert 's3_region = "garage"' in config


def test_core_env_points_at_local_garage_and_secrets_generator_knows_it():
    overrides = _read(DEPLOY / "env" / "core.env.overrides")
    assert re.search(r"^S3_ENDPOINT_URL=http://127\.0\.0\.1:3900$", overrides, re.M)
    assert re.search(r"^S3_REGION=garage$", overrides, re.M)
    gen = _read(DEPLOY / "bin" / "nc-gen-secrets")
    assert "--garage) MODE=garage ;;" in gen
    garage_block = gen[gen.index('if [ "$MODE" = garage ]; then'):gen.index("# ═════════════════════════════ Web Gateway")]
    assert "install -d -m 0700 -o root -g root /etc/nc-garage/secrets" in garage_block
    assert "GARAGE_RPC_SECRET GARAGE_ADMIN_TOKEN" in garage_block
    assert '"$(rand 32)" root:root 0600' in garage_block


def _client_config(monkeypatch, endpoint):
    monkeypatch.setenv("S3_REGION", "garage")
    if endpoint:
        monkeypatch.setenv("S3_ENDPOINT_URL", endpoint)
    else:
        monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    fake_botocore = types.ModuleType("botocore")
    fake_botocore_config = types.ModuleType("botocore.config")

    class FakeConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_botocore_config.Config = FakeConfig
    with patch.dict(sys.modules, {"botocore": fake_botocore, "botocore.config": fake_botocore_config}):
        return s3_storage_mod._build_s3_client_kwargs()["config"].kwargs


def test_s3_client_uses_path_style_and_required_checksums_for_self_hosted_store(monkeypatch):
    config = _client_config(monkeypatch, "http://127.0.0.1:3900")
    assert config["s3"] == {"addressing_style": "path"}
    assert config["request_checksum_calculation"] == "when_required"
    assert config["response_checksum_validation"] == "when_required"


def test_s3_client_keeps_sdk_defaults_without_custom_endpoint(monkeypatch):
    config = _client_config(monkeypatch, "")
    assert "s3" not in config
    assert "request_checksum_calculation" not in config
