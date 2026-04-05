# Verification Scripts

Prakticky verification balik je ted postaveny nad temito skripty:

- `python scripts/verify_import_startup.py`
  - lokalni pre-deploy smoke
  - overi import hlavnich backend modulu a reprezentativni production fail-fast config guardy
- `python scripts/verify_http_probes.py --base-url http://127.0.0.1:8000`
  - overi liveness `/api/v1/health` a readiness `/api/v1/ready`
  - pri `503 not_ready` vraci non-zero exit code
  - pro kontrolu behem rollout okna lze pouzit `--allow-not-ready`
- `python scripts/verify_auth_smoke.py --base-url http://127.0.0.1:8000 --email <user> --password <pass>`
  - minimalni auth smoke bez business write flow
  - pokud nejsou credentials predane, vraci `2` a chova se jako explicitni `SKIP`
- `python scripts/verify_core_api_smoke.py --base-url http://127.0.0.1:8000 --email <user> --password <pass>`
  - read-only smoke nejdulezitejsich tenant-scoped API flow
  - overi `GET /api/v1/cases`, detail prvniho existujiciho pripadu, `GET /api/v1/pricebooks` a `GET /api/v1/material-catalog`
  - pokud nejsou credentials predane, vraci `2` a chova se jako explicitni `SKIP`
- `python scripts/verify_deploy.py --base-url http://127.0.0.1:8000`
  - autoritativni post-deploy / post-change kontrola jednim prikazem
  - vzdy spusti health/readiness
  - auth smoke a core API smoke spusti jen pokud dostane `--auth-email` a `--auth-password`
  - s `--require-auth` selze, pokud credentials chybi
- `python scripts/verify_release_gate.py --base-url https://api.example.com --apply-migrations`
  - bezpecny operator wrapper pro preflight + explicitni migraci + post-deploy verification
  - nejdriv spusti import/startup preflight
  - migraci provede jen pri explicitnim `--apply-migrations`
  - potom spusti deploy verification bundle nad danym `--base-url`
- `python scripts/report_slo.py --prometheus-url http://127.0.0.1:9090 --window 30d`
  - vygeneruje production SLO report z Prometheus API
  - vypocita observed SLI, error budget remaining a budget exhaustion flag
  - umi zapsat JSON i Markdown report do `artifacts/`

Kompatibilni aliasy pro existujici workflow zustaly zachovane:

- `python scripts/test-import-startup.py`
- `python scripts/test-backend-startup.py`
- `python scripts/smoke_check_live.py [BASE_URL] [EMAIL] [PASSWORD]`

Typicke pouziti:

```bash
python scripts/verify_import_startup.py
python scripts/verify_deploy.py --base-url http://127.0.0.1:8000
python scripts/verify_core_api_smoke.py --base-url http://127.0.0.1:8000 --email ops@example.com --password '***'
python scripts/verify_deploy.py --base-url https://api.example.com --auth-email ops@example.com --auth-password '***'
python scripts/verify_release_gate.py --base-url https://api.example.com --apply-migrations --auth-email ops@example.com --auth-password '***'
python scripts/report_slo.py --prometheus-url http://127.0.0.1:9090 --window 30d --json-out artifacts/slo-report.json --markdown-out artifacts/slo-report.md
```

Exit codes:

- `0` = verification uspela
- `1` = verification selhala
- `2` = explicitni `SKIP` pouze u `verify_auth_smoke.py`, kdyz chybi credentials
