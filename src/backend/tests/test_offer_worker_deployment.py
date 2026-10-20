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


def test_offer_worker_is_installed_but_enabled_only_after_backlog_review():
    target = (DEPLOY / "systemd" / "nc-core.target").read_text(encoding="utf-8")
    provision = (DEPLOY / "provision" / "nc-provision").read_text(encoding="utf-8")
    wants = [line for line in target.splitlines() if line.startswith("Wants=")]
    assert wants and all("nc-offer-worker" not in line for line in wants)  # žádný automatický start
    assert "nc-worker.service nc-offer-worker.service nc-core.target" in provision  # install_units
    assert "enable --now nc-worker.service nc-api@desktop.service" in provision  # start bez offer workeru
    assert "nc-offer-backlog\" --require-no-ai-work" in provision
    assert 'NC_CONFIRM_OFFER_BACKLOG:-0}" = 1' in provision
    assert "enable --now nc-offer-worker.service" in provision
    assert (DEPLOY / "bin" / "nc-offer-backlog").is_file()


def test_compose_offer_worker_is_opt_in_and_template_defaults_to_mock():
    compose = (repo_root() / "docker-compose.yml").read_text(encoding="utf-8")
    block = compose[compose.index("  offer-worker:"):compose.index("\nnetworks:")]
    assert 'entrypoint: ["python", "-m", "app.worker.offer_runner"]' in block
    assert 'profiles: ["offers"]' in block
    assert "AI_OFFER_PROVIDER: ${AI_OFFER_PROVIDER}" in block
    template = (BACKEND_ROOT / ".env.production.example").read_text(encoding="utf-8")
    assert "AI_OFFER_PROVIDER=mock" in template
