"""N2: offer pipeline musí v produkci běžet (offer queue, AI budget sweeper,
offer reconciler, outbox publisher) – bare-metal i compose ji spouštějí."""

from app.platform.paths import BACKEND_ROOT, repo_root

DEPLOY = repo_root() / "deploy" / "linux"


def test_systemd_unit_runs_offer_runner_like_the_worker():
    unit = (DEPLOY / "systemd" / "nc-offer-worker.service").read_text(encoding="utf-8")
    worker = (DEPLOY / "systemd" / "nc-worker.service").read_text(encoding="utf-8")
    assert "/opt/novuconstruct/src/backend/.venv/bin/python -m app.worker.offer_runner" in unit
    assert "WorkingDirectory=/opt/novuconstruct/src/backend" in unit
    # stejný sandbox a stejné tajné údaje jako hlavní worker
    for line in worker.splitlines():
        if line.startswith(("LoadCredential=", "ProtectSystem=", "NoNewPrivileges=", "CapabilityBoundingSet=", "User=")):
            assert line in unit, line


def test_offer_worker_is_wanted_installed_started_and_checked():
    target = (DEPLOY / "systemd" / "nc-core.target").read_text(encoding="utf-8")
    provision = (DEPLOY / "provision" / "nc-provision").read_text(encoding="utf-8")
    assert "nc-offer-worker.service" in target
    assert "nc-worker.service nc-offer-worker.service nc-core.target" in provision  # install_units
    assert "enable --now nc-worker.service nc-offer-worker.service" in provision  # start
    assert provision.count("redis-server nc-worker nc-offer-worker") == 2  # smoke + status


def test_compose_runs_offer_worker_with_explicit_provider():
    compose = (repo_root() / "docker-compose.yml").read_text(encoding="utf-8")
    block = compose[compose.index("  offer-worker:"):compose.index("\nnetworks:")]
    assert 'entrypoint: ["python", "-m", "app.worker.offer_runner"]' in block
    assert "AI_OFFER_PROVIDER: ${AI_OFFER_PROVIDER}" in block
    template = (BACKEND_ROOT / ".env.production.example").read_text(encoding="utf-8")
    assert "AI_OFFER_PROVIDER=claude" in template
