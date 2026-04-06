# Monitoring & Alerting Audit - 2026-04-06

Rozsah: `python-backend`, `ops/alerting`, `scripts`, provozni docs.

Metoda: staticka analyza konfigurace a kodu plus cileny beh:
`pytest python-backend/tests/test_r38_metrics.py python-backend/tests/test_health_readiness_semantics.py python-backend/tests/test_verification_scripts.py -q`

Poznamka k limitum: nevidel jsem bezici Prometheus, Alertmanager, Grafana ani centralni log sink, takze audit hodnoti to, co je skutecne zadratovane v repu. Live routing, silence policy a dashboard adoption nelze z tohoto repa definitivne potvrdit.

## A) Aktualni Observability Coverage

### 1. Metriky

Coverage je siroka a pro pilot realne pouzitelna:

- API/HTTP: `http_requests_total`, `http_request_duration_seconds`, `http_requests_in_progress`
- DB/runtime: `novu_db_alive`, `novu_db_pool_exhausted_total`
- Worker/queue: `novu_worker_alive`, `novu_worker_alive_instances`, `novu_worker_seen_instances`, `novu_worker_monitoring_available`, `novu_queue_length`, `novu_heavy_queue_length`, `novu_processing_jobs`, `novu_heavy_processing_jobs`
- Retry/DLQ/backpressure: `novu_queue_scheduled_retry`, `novu_queue_scheduled_retry_due_now`, `novu_queue_dead_letter_active`, `novu_backpressure_*`
- Auth/safety: `novu_auth_failures_total`, `novu_auth_protection_enforced`
- Redis/storage: `novu_redis_runtime_available`, `novu_redis_runtime_degraded`, `novu_storage_ready`, `novu_storage_operations_total`, `novu_storage_operation_duration_seconds`
- Audit: `novu_audit_write_failed_total`
- Job quality: `novu_job_outcomes_total`, `novu_job_duration_seconds`, `novu_job_fail_rate`, `novu_job_stuck_max_age_seconds`

Tenant-level rozliseni uz existuje aspon tam, kde je nejdulezitejsi:

- `novu_job_outcomes_total{status,tenant_id}`
- `novu_job_duration_seconds{status,tenant_id}`
- `novu_auth_failures_total{endpoint,reason,tenant_id}`

Naopak queue depth, worker heartbeat, storage health a HTTP latency zustavaji globalni.

### 2. Health/ready/probes

Probe vrstva je navrzena rozumne:

- `GET /api/v1/health` vraci pravdivy public runtime summary
- `GET /api/v1/ready` vraci ready jen kdyz se ma traffic obsluhovat bezpecne
- `GET /api/v1/ready/processing?strict=1` je autoritativni probe pro background processing
- `GET /api/v1/health/internal` dava operatorovi queue, worker, auth-protection, storage a backpressure detail

Silna stranka je oddeleni `apiState` a processing path. To je spravny zaklad pro degraded rezim i incident response.

### 3. Alerting a SLO

V `ops/alerting/alerts.yml` je dnes 15 alertu:

- hard down: `BackendDown`, `WorkerDown`, `DatabaseUnreachable`
- API quality: `High5xxRate`, `High429Rate`, `SlowResponses`
- queue/job path: `JobQueueBacklog`, `HighJobFailRate`, `StuckRunningJobs`, `DeadLetterQueueGrowing`, `RetryQueueSurge`, `HeavyQueueBacklog`
- auth/runtime/platform: `AuthFailureSpike`, `RedisRuntimeDegraded`, `DiskSpaceLow`

Navic existuji burn-rate SLO rules v `ops/alerting/slo-rules.yml` pro:

- API availability
- job completion success
- auth success
- API latency

### 4. Logy a auditovatelnost

Logging je nadstandardni proti beznemu pilot stacku:

- `structlog`
- `request_id` propagation
- redakce bearer tokenu, JWT, URL credentials a secret-like hodnot
- normalizace `SECURITY_EVENT`
- rotating file handlers

To je dostatecny zaklad pro incident analysis na jedne instanci.

## B) Co Uz Je Provozne Pouzitelne

- Hard-down detection existuje a je rozumna.
- Queue/worker path je viditelny: backlog, stale worker, retry queue, dead-letter, backpressure.
- `/health/internal` a `/ready/processing?strict=1` uz umi odlisit API plane od processing plane.
- Redis degraded stav je exportovan jako first-class signal, ne jen jako log.
- Auth failures, audit write failures a storage operation metrics jsou vubec zmerene, coz byva casta slepa skvrna.
- Job/auth problemy umi byt castecne tenant-specific, protoze tyto metriky uz nesou `tenant_id`.
- Metrics endpoint ma auth guard a volitelny IP allowlist, takze observability vrstva sama o sobe neni otevrena verejne.

Prakticky zaver: system neni "slepy od zakladu". Operator umi videt, ze backend/DB/worker/queue/auth ochrana/Redis nejsou v poradku.

## C) Kde Jsou Blind Spots

### C1 [P0] Alert math a alert semantics maji drift od reality

Nejvetsi problem neni chybejici metrika, ale chybne nebo matouci alert logika:

- `High5xxRate` a `High429Rate` nepocitaji pomer, ale absolutni `rate(counter)`; anotace tvrdi procenta, expression meri requests/sec
- `RetryQueueSurge` pouziva `rate(novu_queue_scheduled_retry[10m])`, ale `novu_queue_scheduled_retry` je gauge, ne counter

Dusledek: alert muze byt bud hlucny, nebo naopak slepy, a on-call vidi jinou semantiku v anotaci nez v realnem PromQL.

### C2 [P0] Monitoring blindness a skutecny worker outage nejsou odlisene

`WorkerDown` dnes sleduje jen `novu_worker_alive == 0`.

To nestaci, protoze pri ztrate Redis scan/read cesty system umi priznat `novu_worker_monitoring_available == 0`. V tu chvili operator nevi, jestli:

- worker opravdu spadl
- heartbeat scan je slepy
- nebo je problem v Redis monitoring path

Chybi samostatny alert typu `WorkerMonitoringBlind` a chybi guard, ktery by `WorkerDown` vazal jen na pripady, kdy monitoring opravdu funguje.

### C3 [P0] Dulezite partial failures jsou zmerene, ale bez alertu

V metrikach existuji signaly, ktere dnes nemaji odpovidajici alert:

- `novu_audit_write_failed_total`
- `novu_auth_protection_enforced`
- `novu_storage_ready`
- `novu_storage_operations_total{outcome="error"}`
- `novu_storage_operation_duration_seconds`
- `novu_db_pool_exhausted_total`
- `novu_backpressure_rejections_total`

To je presne kategorie "tiche selhani", kterou uzivatel zadal proverit.

### C4 [P1] Probe a operations docs jsou castecne zastarale

`OPERATIONS.md` a `scripts/verify_http_probes.py` stale popisuji starsi probe kontrakt jako:

- `/health` minimalni payload
- `/ready` jen startup + DB ready

Aktualni implementace je bohatsi a truthier. Dokumentace a verifikacni skript ted neodpovidaji realite.

To je operational risk, protoze pri releasu nebo incidentu muze operator verit spatnemu kontraktu.

### C5 [P1] Tenant-specific viditelnost je jen castecna

Tenant-level troubleshooting funguje pro:

- auth failures
- job outcomes
- job duration

Ale nefunguje pro:

- queue backlog
- heavy queue backlog
- worker heartbeat
- storage errors/latency
- HTTP latency/5xx/429

Operator tedy umi rict "tenant X ma auth/job problem", ale neumi spolehlive rict "tenant X zaplnuje queue" nebo "tenant X trpi storage timeouty".

### C6 [P1] Runbook vazba je neuplna

Jen cast alertu ma `runbook_url`, a jedna z vazeb ukazuje na auditni markdown misto na operacni runbook.

To neni fatalni technicka chyba, ale v ostrym incidentu to prodluzuje MTTR.

### C7 [P1] Internal health payload ma jedno matoucí pole

`/health/internal` vraci `apiReady`, ale momentalne ho plni z overall `snapshot.ready`.

To znamena, ze worker/queue problem muze vypnout `apiReady`, i kdyz API plane sam o sobe jeste servable je. Public payload ma `apiState` korektne, ale operator-friendly internal payload tady neni uplne cisty.

### C8 [P2] Chybi dukaz o dashboard-as-code a centralnim log sinku

Repo obsahuje alert rules a docs, ale neobsahuje autoritativni Grafana dashboard definitions ani jednoznacnou konfiguraci centralniho log aggregation stacku.

Z toho plyne, ze:

- alerting vrstva existuje
- dashboard adoption nelze potvrdit
- log analysis mimo jednu instanci nelze z repa garantovat

### C9 [P2] Verifikacni sada sama vykazuje drift

Cileny beh testu skoncil:

- `59 passed`
- `3 failed`

Failnute testy ukazuji drift kolem:

- tenant labels v metrikach
- auth metric expectations
- health internal mocking contract

To neni primy dukaz produkcni vady, ale je to dukaz, ze observability contract neni konzistentne udrzovany napric implementaci, docs a verification.

## D) Priority Fixu P0-P3

### P0

1. Opravit alert matematiku:
   `High5xxRate`, `High429Rate`, `RetryQueueSurge`.
2. Pridat alerty na:
   `novu_worker_monitoring_available == 0`,
   `increase(novu_audit_write_failed_total[5m]) > 0`,
   `novu_auth_protection_enforced == 0`,
   `novu_storage_ready == 0`,
   storage error spike,
   `increase(novu_db_pool_exhausted_total[5m]) > 0`,
   backpressure rejection spike.
3. Udelat `runbook_url` povinne alespon pro vsechny `warning` a `critical` alerty.
4. Srovnat `OPERATIONS.md` a `scripts/verify_http_probes.py` s realnou probe semantikou.

### P1

1. Opravit `/health/internal` tak, aby `apiReady` reflektovalo API plane, ne overall ready.
2. Pridat tenant-oriented dashboard slices a recording rules pro top failing tenants.
3. Zviditelnit queue age/operator-facing backlog pressure stejne dobre jako queue depth.
4. Pridat storage latency/error dashboards nad existujicimi storage metrics.

### P2

1. Zavest dashboard-as-code nebo aspon committed dashboard definitions.
2. Zavest centralni log sink nebo explicitne zdokumentovat, kde se provozne sbiraji logy.
3. Rozlisit "worker dead", "worker stale" a "monitoring blind" i v dashboard UX, ne jen v low-level metrikach.

### P3

1. Dodelat jemnejsi anomaly detection:
   auth by reason,
   retry storm by failure classification,
   tenant-specific saturation patterns.
2. Vyladit noise budget alertu podle realneho trafficu po pilotu.

## E) Minimalni Bezpecny Alert Set

Pokud bychom meli nechat jen minimum, ale neslepnout na partial failure a tiche chyby, musi zustat nebo pribyt toto:

1. `BackendDown`
   `up{job="novu-backend"} == 0`
2. `DatabaseUnreachable`
   `novu_db_alive == 0`
3. `WorkerMonitoringBlind`
   `novu_worker_monitoring_available == 0`
4. `WorkerDown`
   `novu_worker_monitoring_available == 1 and novu_worker_alive == 0`
5. `Api5xxRatioHigh`
   error ratio, ne absolutni req/s
6. `ApiLatencyP95High`
   p95 latency nad agregovanym HTTP histogramem
7. `QueueBacklogSustained`
   `novu_queue_length > threshold`
8. `RetryPressureHigh`
   `novu_queue_scheduled_retry_due_now` nebo jina korektni retry-pressure metrika
9. `DeadLetterActive`
   `novu_queue_dead_letter_active > 0`
10. `RedisRuntimeDegraded`
    `novu_redis_runtime_degraded == 1`
11. `AuthProtectionDisabled`
    `novu_auth_protection_enforced == 0`
12. `AuthFailureSpike`
    agregovane nad `novu_auth_failures_total`
13. `StorageUnavailableOrErrorSpike`
    `novu_storage_ready == 0` plus storage error rate/latency
14. `AuditWriteFailed`
    `increase(novu_audit_write_failed_total[5m]) > 0`
15. `DbPoolExhausted`
    `increase(novu_db_pool_exhausted_total[5m]) > 0`
16. `BackpressureRejectSpike`
    `increase(novu_backpressure_rejections_total[5m]) > 0`

Bez bodu 3, 11 a 14 zustava system slepy presne v kategoriich "partial failure", "security degradation" a "audit gap".

## F) Seznam Autoritativnich Dashboard Signalu

Tohle jsou signaly, ktere by mely byt na primarnim ops dashboardu a brat se jako source of truth:

### 1. API plane

- request rate
- 5xx ratio
- 429 ratio
- p95/p99 latency
- `http_requests_in_progress`
- `novu_db_alive`
- `novu_db_pool_exhausted_total`

### 2. Processing plane

- `novu_worker_alive`
- `novu_worker_alive_instances`
- `novu_worker_seen_instances`
- `novu_worker_monitoring_available`
- `novu_queue_length`
- `novu_heavy_queue_length`
- `novu_processing_jobs`
- `novu_heavy_processing_jobs`
- `novu_jobs_queued`
- `novu_jobs_running`
- `novu_job_stuck_max_age_seconds`
- `novu_queue_scheduled_retry`
- `novu_queue_scheduled_retry_due_now`
- `novu_queue_dead_letter_active`
- `novu_backpressure_current_*`
- `novu_backpressure_max_*`
- `novu_backpressure_rejections_total`

### 3. Safety plane

- `novu_auth_protection_enforced`
- `novu_auth_failures_total` by `endpoint`, `reason`, `tenant_id`
- `novu_redis_runtime_available`
- `novu_redis_runtime_degraded`
- `novu_storage_ready`
- `novu_storage_operations_total` by `operation`, `backend`, `outcome`
- `novu_storage_operation_duration_seconds`
- `novu_audit_write_failed_total`

### 4. Probe plane

Vedle Prom metrik musi operator sledovat i probe payloady:

- `GET /api/v1/health`
- `GET /api/v1/ready`
- `GET /api/v1/ready/processing?strict=1`
- `GET /api/v1/health/internal`

Autoritativni fieldy:

- `status`
- `ready`
- `apiState`
- `processingState`
- `jobProcessingReady`
- `worker.state`
- `queue.state`
- `security.authProtection.state`
- `security.authProtection.enforced`
- `jobs.retryQueued`
- `jobs.retryInflight`
- `jobs.deadLetter`
- `jobs.maxRunningAgeSeconds`
- `jobs.backpressure.*`

### 5. Tenant slice

Minimalne musi jit rychle otevrit i tenant-focused pohled:

- top tenants by `novu_job_outcomes_total{status="failed"}`
- top tenants by `novu_job_duration_seconds`
- top tenants by `novu_auth_failures_total`

Tato cast je zatim jen castecne mozne postavit z existujicich labels.

## G) Verdikt

`partially blind`

Duvod:

- system ma solidni zaklad a neni observability-empty
- hard-down, worker/queue, Redis degraded a cast auth/job problemu jsou viditelne
- ale stale chybi alert coverage pro nekolik skutecne nebezpecnych tichych failure modes
- cast alertu ma spatnou matematiku nebo nepresnou semantiku
- docs, scripts a dashboard/runbook vrstva nejsou plne srovnane s implementaci

Jinymi slovy:
pro pilot je stack operacne pouzitelny, ale pro stav "nejsme slepi pri degradaci, partial failure nebo tichém selhani" jeste chybi posledni vrstva discipliny okolo alert kvality, monitoring-blind detection a safety-specific signalu.

## Ověření

Pouzite dukazy:

- `ops/alerting/alerts.yml`
- `ops/alerting/slo-rules.yml`
- `python-backend/app/core/metrics.py`
- `python-backend/app/api/routes/system.py`
- `python-backend/app/core/logging.py`
- `python-backend/app/core/audit.py`
- `python-backend/app/main.py`
- `scripts/verify_http_probes.py`
- `OPERATIONS.md`

Beh overeni:

```text
pytest python-backend/tests/test_r38_metrics.py python-backend/tests/test_health_readiness_semantics.py python-backend/tests/test_verification_scripts.py -q
```

Vysledek:

- `59 passed`
- `3 failed`

Selhani potvrzuji drift v observability contractu mezi implementaci, testy a operacnimi skripty. To samo o sobe podporuje verdikt `partially blind`.
