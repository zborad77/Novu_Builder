# Incident Rehearsal Scénáře

Platí pro aktuální architekturu `v0.7.001`: FastAPI backend, PostgreSQL, Redis-backed queue, samostatný worker, backpressure, readiness `/api/v1/ready` a processing readiness `/api/v1/ready/processing?strict=1`.

## Cíl

Ověřit, že systém reaguje správně i pod tlakem:

- incident je rychle detekovaný
- readiness a processing readiness nelžou
- joby se neztrácí
- fronta degraduje kontrolovaně
- recovery je deterministická a bez ručních zásahů do DB

## Autoritativní signály

Při každém rehearsal sleduj primárně:

- `GET /api/v1/health`
- `GET /api/v1/ready`
- `GET /api/v1/ready/processing?strict=1`
- `GET /api/v1/health/internal`
- `GET /api/v1/metrics`

Klíčové fieldy a metriky:

- `jobProcessingReady`
- `workerState`
- `queueState`
- `jobs.running`
- `jobs.queued`
- `jobs.retryQueued`
- `jobs.retryInflight`
- `jobs.deadLetter`
- `jobs.queueLength`
- `jobs.backpressure.currentQueued`
- `jobs.backpressure.maxQueued`
- `novu_worker_alive`
- `novu_db_alive`
- `novu_queue_length`
- `novu_processing_jobs`
- `novu_jobs_running`
- `novu_jobs_queued`
- `novu_queue_scheduled_retry`
- `novu_queue_scheduled_retry_due_now`
- `novu_queue_dead_letter_active`
- `novu_job_fail_rate`
- `novu_job_stuck_max_age_seconds`
- `novu_reaper_requeues_total`
- `novu_backpressure_current_queued_jobs`
- `novu_backpressure_current_retry_inflight`
- `novu_backpressure_rejections_total`
- `http_request_duration_seconds`
- `http_requests_total`

Poznámka:
Backend HTTP diagnostika dobře pokrývá queue, retry a readiness. Nepokrývá ale přímo host-level tlak na PostgreSQL a Redis; pro DB latency spike a Redis pressure je vhodné paralelně sledovat i node/Postgres telemetry.

## Výchozí setup

Používej mock provider, aby šlo bezpečně vyvolat retry/failure scénáře:

```powershell
docker compose up -d db redis backend worker
Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/v1/health
Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/v1/ready
Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/v1/ready/processing?strict=1
```

Pro souběžný load měj připravený rehearsal driver:

```powershell
& .\python-backend\.venv\Scripts\python.exe .\scripts\run-operational-load-rehearsal.py `
  --base-url http://127.0.0.1:8000 `
  --tenant-file .\artifacts\load-tenants.json `
  --observer-email admin@novu.cz `
  --observer-password NovuAdmin2024! `
  --json-out .\artifacts\operational-load-rehearsal.json
```

## Alerty v aktuálním stacku

Existující alerty v `ops/alerting/alerts.yml`:

- `BackendDown`
- `WorkerDown`
- `High5xxRate`
- `High429Rate`
- `SlowResponses`
- `DatabaseUnreachable`
- `JobQueueBacklog`
- `HighJobFailRate`
- `StuckRunningJobs`
- `DiskSpaceLow`

Doporučené doplnění před ostrým pilotem:

- alert na `novu_redis_runtime_available == 0`
- alert na `novu_auth_protection_enforced == 0`
- alert na `novu_queue_scheduled_retry_due_now` nad dlouhodobý threshold
- alert na `novu_queue_dead_letter_active > 0`
- alert na rychlý růst `novu_backpressure_rejections_total`

## 1. Redis restart během loadu

### Jak simulovat

- Spusť souběžný load přes `run-operational-load-rehearsal.py`.
- Ve chvíli, kdy běží enqueue/polling fáze, proveď:

```powershell
docker compose restart redis
```

- Bezpečnější varianta pro opakování: drž outage krátký, typicky 10-30 s.

### Očekávané chování systému

- API proces nesmí spadnout.
- `jobProcessingReady` musí přejít na `false`.
- `queueState` musí přejít na `unavailable` nebo `degraded`, ne zůstat falešně zelený.
- Worker nesmí “potichu” ztratit leased joby; po obnově Redis musí znovu navázat processing.
- Queue throughput se může krátce zastavit, ale po recovery se má znovu rozběhnout.
- Auth/runtime enforcement nesmí předstírat plnou readiness bez Redis.

### Jaké alerty se spustí

Pravděpodobně:

- `WorkerDown`, pokud outage nebo stale heartbeat překročí 3 minuty
- `High5xxRate`, pokud outage zasáhne requesty
- `SlowResponses`, pokud requesty čekají na timeouty

Doporučené doplnit:

- `RedisRuntimeUnavailable` nad `novu_redis_runtime_available == 0`

### Co ukáže dashboard

- `/ready/processing?strict=1`: `jobProcessingReady=false`, `queueState=unavailable`
- `/health/internal`: `status=degraded` nebo `ready=false`, `queue.state=unavailable`
- `novu_queue_length`: může krátce stagnovat
- `novu_processing_jobs`: pokles nebo freeze
- `novu_worker_monitoring_available`: může spadnout na `0`
- `http_request_duration_seconds`: krátký spike

### Správný runbook postup

- Potvrď incident přes `/ready/processing?strict=1` a `/health/internal`.
- Ověř Redis:

```powershell
docker compose ps redis
docker compose logs --tail=50 redis
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" ping
```

- Pokud se Redis sám nevrátí, restartuj jej.
- Po recovery ověř:
  `queueState=ready`, `jobProcessingReady=true`, fronta znovu drainuje.
- Pokud processing po návratu Redis neběží, zkontroluj worker heartbeat a případně restartuj worker.

## 2. Worker crash během jobu

### Jak simulovat

- Připrav 3-10 analysis jobů a počkej, až alespoň jeden přejde do `running`.
- Pak proveď tvrdý kill workeru:

```powershell
docker compose kill worker
docker compose up -d worker
```

- Měkčí varianta pro méně agresivní rehearsal:

```powershell
docker compose restart worker
```

### Očekávané chování systému

- Rozpracovaný job se nesmí ztratit.
- Po lease timeoutu a reap cyklu se job musí vrátit do `queued`, nebo čistě dokončit, pokud lease ještě platil.
- Startup reconciliation po startu workeru musí odstranit orphaned queue state.
- Queue depth může krátce narůst, ale musí se opět vyprázdnit.

### Jaké alerty se spustí

Pravděpodobně:

- `WorkerDown`
- `StuckRunningJobs`, pokud recovery trvá příliš dlouho
- `JobQueueBacklog`, pokud backlog přetrvá

### Co ukáže dashboard

- `/health/internal`: `worker.state=missing|stale`, `jobs.running` zamrzne, později klesne
- `novu_worker_alive`: spadne na `0`
- `novu_reaper_requeues_total`: po reapnutí naroste
- `novu_job_stuck_max_age_seconds`: může krátce růst
- `novu_jobs_queued`: po requeue dočasně vzroste

### Správný runbook postup

- Potvrď stale/missing worker přes `/health/internal`.
- Ověř heartbeat a logy:

```powershell
docker compose ps worker
docker compose logs --tail=100 worker
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" GET worker:heartbeat
```

- Pokud worker nenaběhne sám, proveď `docker compose up -d worker`.
- Sleduj, zda `novu_reaper_requeues_total` a `jobs.queued` potvrzují recovery.
- Pokud job visí bez requeue, eskaluj jako bug lease/reaper logiky; ruční DB zásah nemá být standardní postup.

## 3. DB latency spike

### Jak simulovat

Preferovaná bezpečná varianta ve stagingu:

- spusť load script
- paralelně vytvoř krátkodobý PostgreSQL pressure spike více dlouhými session:

```powershell
1..20 | ForEach-Object {
  Start-Job {
    docker compose exec db psql -U novu -d novu_builder -c "SELECT pg_sleep(30);"
  } | Out-Null
}
```

Agresivnější Linux-only varianta:

- injektuj síťovou latenci mezi backend/worker a PostgreSQL přes `tc` nebo Toxiproxy

Poznámka:
aktuální repo má lepší signály pro DB outage než pro čistou DB latenci. U tohoto rehearsal proto sleduj hlavně symptomatické metriky, ne jen boolean `novu_db_alive`.

### Očekávané chování systému

- API může zpomalit, ale nemá se nekontrolovaně rozsypat.
- Při tvrdém překročení timeoutů může `ready` přejít do `503`.
- Worker a API mají oddělené DB pooly, takže se problém může projevit asymetricky, ale obě cesty musí zůstat diagnostikovatelné.
- Background jobs se mohou zpomalit; nesmí se ztratit ani přeskakovat stavový automat.

### Jaké alerty se spustí

Pravděpodobně:

- `SlowResponses`
- `High5xxRate`, pokud latency přejde do timeoutů
- `DatabaseUnreachable`, pokud spike přeroste do praktické nedostupnosti
- `StuckRunningJobs`, pokud dlouhé DB commity prodlouží running jobs

Doporučené doplnit mimo backend:

- Postgres exporter alert na query latency / active sessions / lock waits

### Co ukáže dashboard

- `http_request_duration_seconds` p95/p99 výrazně poroste
- `/ready`: může padat do `503`
- `/health/internal`: `db` může zůstat `ok` u mírnějšího spike, ale `jobs.maxRunningAgeSeconds` poroste
- `novu_job_stuck_max_age_seconds`: růst
- `novu_jobs_running`: vyšší plateau, pomalejší odtok

### Správný runbook postup

- Nejprve potvrď, zda jde o latenci, nebo plný DB outage.
- Ověř:

```powershell
docker compose ps db
docker compose logs --tail=50 db
docker compose exec db pg_isready -U novu -d novu_builder
```

- Pokud DB běží, ale je pomalá, sleduj aktivní session a zvaž ukončení rehearsal loadu.
- Pokud backlog roste rychleji než worker drainuje, dočasně zastav nové enqueue requesty.
- Po odeznění spike ověř návrat `ready`, pokles `http_request_duration_seconds` a postupné odtečení `jobs.running`.

## 4. External API failure storm

### Jak simulovat

Bezpečná a levná varianta s mock providerem:

- vytvoř sadu case záznamů s markerem v popisu:
  `[rehearsal:fail-always]`
- enqueue desítky analysis jobů nad těmito case

Marker je podporovaný přímo v `mock_vision_provider.py` a vyvolá perzistentní provider failure.

Přibližný pattern:

- `title`: libovolný
- `description`: `External API storm [rehearsal:fail-always]`

Reálná integrační varianta:

- dočasně zablokuj egress na AI provider nebo použij neplatný API key ve stagingu

### Očekávané chování systému

- Joby mají selhávat kontrolovaně, ne mizet.
- Retry logika má respektovat budget a backoff.
- Po vyčerpání retry budgetu mají joby přejít do `dead_letter`, ne zůstat věčně v `running`.
- API pro běžné CRUD operace má zůstat použitelné; problém je izolovaný hlavně do background processing.

### Jaké alerty se spustí

Pravděpodobně:

- `HighJobFailRate`
- `JobQueueBacklog`, pokud enqueue pokračuje rychleji než failure/retry drain
- `StuckRunningJobs`, pokud provider timeouty drží jobs příliš dlouho

Doporučené doplnit:

- alert na `novu_queue_dead_letter_active > 0`

### Co ukáže dashboard

- `/health/internal`: růst `jobs.retryQueued`, `jobs.retryInflight`, později `jobs.deadLetter`
- `novu_job_fail_rate`: výrazný nárůst
- `novu_queue_scheduled_retry` a `novu_queue_scheduled_retry_due_now`: nárůst
- `novu_queue_dead_letter_active`: nárůst při exhausted budgetu
- `novu_jobs_running`: oscilace, ale bez “black hole”

### Správný runbook postup

- Potvrď, že jde o provider incident, ne o Redis/worker problém.
- Ověř, zda CRUD a auth stále fungují; tím potvrdíš izolaci blast radius.
- Pokud incident trvá, zastav nové enqueue nebo přepni pilot do degradovaného režimu bez AI analýz.
- Sleduj DLQ a retry backlog.
- Po návratu providera ověř, že nové joby dokončují a staré DLQ položky lze řízeně reprocessnout.

## 5. Massive retry storm

### Jak simulovat

Použij mock provider marker, který selže jen na prvních pokusech:

- `description`: `Retry storm [rehearsal:fail-until-attempt=2]`

Pak paralelně enqueue vyšší dávku jobů, typicky 30-100 podle staging capacity.

Pro tvrdší rehearsal můžeš ve stagingu dočasně snížit:

- `BACKPRESSURE_MAX_RETRY_INFLIGHT`
- `ANALYSIS_RETRY_BACKOFF_BASE_SECONDS`

Tím se storm zrychlí a lépe se ověří retry budget enforcement.

### Očekávané chování systému

- Retry se nesmí změnit v thundering herd.
- Deterministic jitter má rozprostřít retry v čase.
- Jakmile retry inflight dosáhne budgetu, systém má odmítat další retry eskalaci kontrolovaně.
- Část jobů může skončit v `dead_letter`, ale systém se nesmí zahltit ani přestat odpovídat na běžné requesty.

### Jaké alerty se spustí

Pravděpodobně:

- `HighJobFailRate`
- `JobQueueBacklog`
- `High429Rate`, pokud uživatelé dál tlačí nové joby během plného retry budgetu

Doporučené doplnit:

- alert na `novu_backpressure_rejections_total{reason="retry_budget_exhausted"}`
- alert na trvale vysoké `novu_queue_scheduled_retry_due_now`

### Co ukáže dashboard

- `/health/internal`: růst `retryQueued`, `retryInflight`, případně `deadLetter`
- `jobs.backpressure.currentRetryInflight` se blíží `maxRetryInflight`
- `novu_backpressure_current_retry_inflight` roste ke stropu
- `novu_backpressure_rejections_total`: nárůst
- `novu_queue_scheduled_retry`: vysoké hodnoty, ale musí postupně klesat po uklidnění incidentu

### Správný runbook postup

- Potvrď, že se retry budget opravdu vynucuje a nejde o nekonečnou smyčku.
- Pozastav nové enqueue pro postižený typ úloh.
- Neprováděj masové ruční retry, dokud je storm aktivní.
- Po stabilizaci zkontroluj DLQ, backlog a případné ruční reprocess proveď až po návratu kapacity.

## 6. Queue saturation

### Jak simulovat

Nejčitelnější staging varianta:

- dočasně sniž `BACKPRESSURE_MAX_QUEUED_JOBS`
- ponech nízkou worker concurrency
- spusť burst enqueue requestů nad nový limit

Alternativně bez změny configu:

- pusť `run-operational-load-rehearsal.py` s vyšším `--case-count`
- nebo opakovaně vytvářej analysis joby, dokud nezačnou vracet `429`

### Očekávané chování systému

- API musí začít vracet `429`, ne `500`.
- Fronta se nesmí přelévat nad backpressure ceiling.
- Již přijaté joby musí pokračovat normálně a postupně se drainovat.
- Po odeznění burstu musí být možné znovu enqueue bez restartu systému.

### Jaké alerty se spustí

Pravděpodobně:

- `High429Rate`
- `JobQueueBacklog`
- `SlowResponses`, pokud systém jde na hranu kapacity

Doporučené doplnit:

- alert na `novu_backpressure_current_queued_jobs / novu_backpressure_max_queued_jobs > 0.9`
- alert na rychlý růst `novu_backpressure_rejections_total`

### Co ukáže dashboard

- `/health/internal`: `jobs.backpressure.currentQueued` bude blízko `maxQueued`
- `novu_backpressure_current_queued_jobs`: saturace ke stropu
- `novu_queue_length` a `novu_jobs_queued`: nárůst
- `http_requests_total` s `429`: nárůst
- `novu_processing_jobs`: zůstává v mezích concurrency ceiling

### Správný runbook postup

- Potvrď, že jde o backpressure, ne o poruchu queue runtime.
- Ověř, zda requesty dostávají očekávané `429` odpovědi.
- Pokud jde o legitimní provozní špičku, krátkodobě omez nové enqueue nebo navyš kapacitu workerů.
- Po odeznění burstu sleduj, že `currentQueued` klesá a `429` mizí bez restartu.

## PASS kritéria pro celý rehearsal balík

Rehearsal je úspěšný, pokud platí:

- žádný job se neztratí
- žádný `running` job nezůstane viset bez recovery cesty
- `/ready` a `/ready/processing?strict=1` nelžou
- systém pod tlakem degraduje řízeně přes `429` / `503`, ne přes tiché chyby
- po návratu dependency není nutný ruční DB zásah
- dashboard a alerty dávají operátorovi jednoznačný obraz o incidentu

## Minimální follow-up po každém rehearsal

- uložit JSON výstup rehearsal skriptu do `artifacts/`
- zapsat čas začátku a konce incidentu
- zapsat, které alerty se skutečně spustily a které chyběly
- zapsat, jestli recovery proběhla bez ručních SQL zásahů
- zapsat konkrétní backlog peak, retry peak a čas návratu do green stavu
