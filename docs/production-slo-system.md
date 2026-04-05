# Production SLO System

Tento dokument definuje produkční SLO vrstvu pro NOVU Builder nad Prometheus metrikami, alertingem a pravidelným reportingem.

## Cíl

Měřit, jestli systém skutečně plní očekávání, a mít:

- jasně definované SLO a SLI
- známý error budget
- alerty na rychlé pálení i vyčerpání rozpočtu
- pravidelný report nad trailing oknem

## Scope

SLO systém je navržen nad existujícími metrikami:

- `http_requests_total`
- `http_request_duration_seconds`
- `novu_job_outcomes_total`
- `novu_auth_failures_total`

User-facing API scope záměrně vylučuje:

- `/api/v1/health`
- `/api/v1/ready`
- `/api/v1/ready/processing`
- `/api/v1/health/internal`
- `/api/v1/metrics`
- `/api/v1/alive`

## Definované SLO

| SLO | Objective | Jak se měří | 30d error budget |
| --- | --- | --- | --- |
| API availability | `99.9%` | podíl public API requestů bez `5xx` | `43.2 min` |
| Job completion success rate | `99.0%` | `completed / (completed + failed + dead_letter)` | `432.0 min` ekvivalent fail budgetu |
| Auth success rate | `99.95%` | login/refresh requesty bez platform-side `5xx` | `21.6 min` |
| API latency p95 | `95% <= 1000 ms` | podíl public non-5xx requestů pod `1.0s` + reportované p95 | `5%` slow-request budget |
| API latency p99 | `99% <= 2000 ms` | podíl public non-5xx requestů pod `2.0s` + reportované p99 | `1%` slow-request budget |

## Důležité upřesnění k auth SLO

Auth SLO měří spolehlivost auth platformy, ne správnost hesla uživatele.

To znamená:

- `401 invalid credentials` nehoří budget, pokud auth odpověděl korektně
- `401 invalid refresh token` nehoří budget, pokud auth odpověděl korektně
- `429` z ochranných guardů nehoří budget, pokud jsou očekávané
- `5xx/503` na login/refresh budget pálí

## Error budget

Pro success/availability SLO je zbývající budget definovaný jako:

- `remaining = 1 - ((1 - observed) / (1 - objective))`

Interpretace:

- `100%` = budget je celý k dispozici
- `0%` = budget je přesně vyčerpaný
- `< 0%` = SLO je porušené

Pro latency SLO se stejný vzorec aplikuje nad podílem requestů, které splnily threshold.

## Alerting

SLO rule file:

- `ops/alerting/slo-rules.yml`

Zahrnuje:

- trailing `30d` compliance recording rules
- short-window burn-rate alerty
- exhausted alerty pro překročení trailing objective

Základní health alerty zůstávají v:

- `ops/alerting/alerts.yml`

## Reporting

Report script:

```powershell
python .\scripts\report_slo.py `
  --prometheus-url http://127.0.0.1:9090 `
  --window 30d `
  --job novu-backend `
  --json-out .\artifacts\slo-report.json `
  --markdown-out .\artifacts\slo-report.md
```

Script:

- načte data z Prometheus HTTP API
- spočítá observed SLI
- spočítá zbývající budget
- označí vyčerpaný budget
- uloží JSON i Markdown výstup

## Doporučený provozní rytmus

- denně: projít fast-burn alerty
- týdně: vygenerovat SLO report a projít trend
- po větším incidentu: zapsat dopad do budgetu
- před pilot expansion nebo go-live gate: vyžadovat čerstvý SLO report
