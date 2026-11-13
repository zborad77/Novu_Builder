# Copyright (c) 2026 Novusion
# Website: https://novusion.com
# Contact: info@novusion.com
#
# Author: Pavel Dostál
# Project: NovuConstruct
# Module: src/backend/tests
# Description: F9.1/F9.3 – plánovaná záloha mimo server a alerty na výpadek API,
#              workeru, zastaralý heartbeat, selhání zálohy a WG jsou nasazené.
# Created: 2026-11-13
"""F9.1/F9.3: noční šifrovaná záloha mimo server (nc-backup) a monitoring.

Alerty musí číst přesně ty metriky, které zapisují nasazené skripty; jinak by
pravidlo existovalo, ale nikdy by se nespustilo.
"""

import os
import re
import shutil
import subprocess

import pytest
import yaml

from app.platform.paths import repo_root

DEPLOY = repo_root() / "deploy" / "linux"
ALERTS = repo_root() / "ops" / "alerting" / "alerts.yml"


def _rules() -> dict[str, dict]:
    data = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))
    return {r["alert"]: r for g in data["groups"] for r in g["rules"] if "alert" in r}


def test_backup_and_wg_metrics_run_from_installed_timers():
    provision = (DEPLOY / "provision" / "nc-provision").read_text(encoding="utf-8")
    for unit in ("nc-backup.service", "nc-backup.timer", "nc-wg-metrics.service", "nc-wg-metrics.timer"):
        assert (DEPLOY / "systemd" / unit).is_file(), unit
        assert unit in provision, f"{unit} se neinstaluje"
    assert "enable --now nc-backup.timer nc-wg-metrics.timer" in provision
    timer = (DEPLOY / "systemd" / "nc-backup.timer").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 02:30:00" in timer and "Persistent=true" in timer
    service = (DEPLOY / "systemd" / "nc-backup.service").read_text(encoding="utf-8")
    assert "ExecStart=/opt/novuconstruct/deploy/linux/bin/nc-backup" in service


def test_backup_is_off_host_encrypted_and_pinned():
    script = (DEPLOY / "bin" / "nc-backup").read_text(encoding="utf-8")
    assert "umask 077" in script
    assert "sftp:*) ;;" in script  # jen repozitář mimo server
    assert "StrictHostKeyChecking=yes" in script and "UserKnownHostsFile=" in script
    assert "RESTIC_PASSWORD_FILE missing" in script  # bez hesla se nezálohuje
    assert "pg_dump -Fc" in script and "pg_restore --list" in script


def test_alerts_cover_api_worker_heartbeat_backup_and_wg():
    rules = _rules()
    required = {
        "BackendDown", "BackendTargetMissing", "WorkerDown", "WorkerHeartbeatUnknown", "WorkerHeartbeatStale",
        "NcBackupFailed", "NcBackupStale", "NcBackupMissing",
        "WireGuardInterfaceDown", "WireGuardInterfaceNotMonitored", "WireGuardNoHandshake",
        "WireGuardRequiredPeerStale", "WireGuardMetricsStale",
    }
    missing = required - rules.keys()
    assert not missing, f"chybí alerty: {sorted(missing)}"
    for name in required:
        assert rules[name]["labels"]["severity"] in {"critical", "warning"}


def test_alert_metrics_are_the_ones_the_scripts_write():
    emitted = set()
    for script in ("nc-backup", "nc-wg-metrics"):
        text = (DEPLOY / "bin" / script).read_text(encoding="utf-8")
        emitted |= set(re.findall(r"# TYPE (nc_[a-z_]+) gauge", text))
    rules = _rules()
    used = set()
    for name in ("NcBackupFailed", "NcBackupStale", "NcBackupMissing",
                 "WireGuardInterfaceDown", "WireGuardInterfaceNotMonitored",
                 "WireGuardNoHandshake", "WireGuardRequiredPeerStale"):
        used |= set(re.findall(r"\bnc_[a-z_]+", rules[name]["expr"]))
    assert used and used <= emitted, f"alert čte metriku, kterou nikdo nezapisuje: {sorted(used - emitted)}"


def test_backup_and_wg_scripts_behaviour_against_stubs(tmp_path):
    sh = shutil.which("sh")
    if sh is None:
        pytest.skip("POSIX sh není k dispozici")
    result = subprocess.run(  # noqa: S603 - pevný skript z repozitáře
        [sh, str(DEPLOY / "tests" / "backup_monitoring_test.sh")],
        env={"PATH": os.environ["PATH"], "NC_BACKUP_TEST_DIR": str(tmp_path)},
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# PromQL řetězec v "" smí obsahovat jen escape sekvence Go (strconv.Unquote);
# např. "\." Prometheus odmítne a nenačte celý soubor pravidel.
_PROMQL_DQ_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')
_PROMQL_VALID_ESCAPE = re.compile(r"""\\(?:[abfnrtv\\'"]|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|[0-7]{3})""")


def test_alert_expressions_use_only_valid_promql_string_escapes():
    bad = []
    for name, rule in _rules().items():
        for literal in _PROMQL_DQ_STRING.findall(rule["expr"]):
            rest = _PROMQL_VALID_ESCAPE.sub("", literal)
            if "\\" in rest:
                bad.append(f"{name}: \"{literal}\"")
    assert not bad, f"neplatný escape v PromQL řetězci (použij \\\\): {bad}"


def test_provisioning_installs_backup_and_textfile_collector_packages():
    # Bez restic nc-backup neuloží nic a bez prometheus-node-exporter chybí
    # /var/lib/prometheus/node-exporter: ReadWritePaths pak shodí nc-backup.service
    # i nc-wg-metrics.service (226/NAMESPACE) a metriky alertů nevzniknou.
    text = (DEPLOY / "provision" / "nc-provision").read_text(encoding="utf-8")
    body = text.split("install_packages() {", 1)[1].split("\n}\n", 1)[0]
    for unit in ("nc-backup.service", "nc-wg-metrics.service"):
        unit_text = (DEPLOY / "systemd" / unit).read_text(encoding="utf-8")
        assert "ReadWritePaths=/var/lib/prometheus/node-exporter" in unit_text
    for pkg in ("restic", "prometheus-node-exporter"):
        assert re.search(rf"pkgs\+=\([^)]*\b{re.escape(pkg)}\b", body), f"install_packages neinstaluje {pkg}"


def test_worker_alerts_read_metrics_the_backend_exports():
    # T7.2: WorkerDown/WorkerHeartbeatStale musí číst gauge, které API skutečně vystavuje.
    exported = set(re.findall(
        r'Gauge\(\s*"(novu_[a-z_]+)"',
        (repo_root() / "src" / "backend" / "app" / "platform" / "metrics.py").read_text(encoding="utf-8"),
    ))
    rules = _rules()
    used = set()
    for name in ("WorkerDown", "WorkerHeartbeatUnknown", "WorkerHeartbeatStale"):
        used |= set(re.findall(r"\bnovu_[a-z_]+", rules[name]["expr"]))
    assert used and used <= exported, f"alert čte neexistující metriku: {sorted(used - exported)}"


def test_wg_handshake_alert_uses_the_configured_limit():
    # Limit se nastavuje v monitoring.env (NC_WG_HANDSHAKE_MAX_AGE), ne natvrdo v pravidle.
    expr = _rules()["WireGuardNoHandshake"]["expr"]
    assert "nc_wg_interface_up == 1" in expr
    assert "nc_wg_interface_latest_handshake_timestamp_seconds" in expr
    assert "nc_wg_handshake_max_age_seconds > 0" in expr
    not_monitored = _rules()["WireGuardInterfaceNotMonitored"]["expr"]
    for iface in ("wg-nc", "wg-nc-admin"):
        assert f'absent(nc_wg_interface_up{{interface="{iface}"}})' in not_monitored


def test_promtool_unit_tests_fire_every_acceptance_alert():
    # ops/alerting/alerts_test.yml (spouští validate-configs.sh přes promtool) musí
    # u každého alertu z kritérií T7.2 očekávat skutečně vystřelený alert.
    data = yaml.safe_load((ALERTS.parent / "alerts_test.yml").read_text(encoding="utf-8"))
    assert data["rule_files"] == ["alerts.yml"]
    fired = {
        case["alertname"]
        for test in data["tests"]
        for case in test.get("alert_rule_test", [])
        if case.get("exp_alerts")
    }
    required = {"BackendDown", "WorkerDown", "WorkerHeartbeatStale", "WireGuardInterfaceDown",
                "WireGuardInterfaceNotMonitored", "WireGuardNoHandshake"}
    assert required <= fired, f"bez testu vystřelení: {sorted(required - fired)}"
    assert set(fired) <= _rules().keys()
