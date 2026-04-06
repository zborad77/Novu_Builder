# Load / Saturation Audit 2026-04-05

## Verdikt

`not-ready`

Kód už obsahuje několik důležitých load guardrailů, takže architektura je částečně `scale-aware`. Aktuální běžící runtime ale není zátěžově bezpečný:

- `worker_concurrency=1`
- `worker_heavy_concurrency=0`
- `effective_worker_db_pool_size=1`
- v runtime chybí worker heartbeat
- analysis backlog už teď driftuje mezi DB a Redis

Pod tlakem tedy systém nepadne hned kvůli úplně chybějícím guardrailům, ale velmi rychle narazí na úzká hrdla a začne degradowat způsobem, který není dost bezpečný pro pilotní provoz.

## A) Reálné load bottlenecks

### 1. Analysis processing je fakticky single-slot

V runtime je potvrzeno:

- `worker_concurrency=1`
- `effective_worker_db_pool_size=1`
- `effective_backpressure_max_concurrent_jobs=1`

To znamená:

- pouze jeden analysis job může být aktivně zpracovávaný
- jakýkoli pomalý provider call nebo retry blokuje celý analysis throughput
- při růstu tenantů se backlog bude řadit sériově, nikoli paralelně

### 2. Heavy path je v runtime vypnutý, takže těžké operace běží inline v API

V runtime je potvrzeno:

- `worker_heavy_concurrency=0`
- `redis_heavy_queue=0`
- `redis_heavy_processing=0`

V kódu to znamená:

- exporty běží inline, pokud `worker_heavy_concurrency <= 0`
- photo variant processing běží inline, pokud `worker_heavy_concurrency <= 0`

Praktický dopad:

- PDF/DOCX/ZIP generování blokuje request lifecycle
- resize a derivace obrázků blokují API worker vlákna a CPU
- heavy path může poškozovat lehké requesty, protože není oddělený bulkheadem

To je dnes největší reálný load blocker.

### 3. Upload cesta čte celý soubor do paměti

Upload validace používá `await file.read(max_bytes + 1)` a celý payload drží jako `bytes`.

Praktický dopad:

- 20 MB soubor je načtený celý do paměti
- více souborů v jednom requestu znamená opakované whole-file alokace
- následná image validace + dimension probe + resize dělá další CPU/memory tlak

Limit `20 MB` pomáhá, ale není to stream-safe cesta.

### 4. Per-tenant fairness je silná jen pro analysis jobs

Dobře omezené je pouze:

- `analysis_jobs_per_tenant_limit=10`

Není omezené per-tenant:

- export intake
- photo upload / heavy lane intake
- heavy queue occupancy

Takže noisy neighbor ochrana je jen částečná. Jeden tenant dnes nemůže nekonečně plnit analysis lane, ale může vytvářet disproporční tlak v heavy/API cestách.

### 5. Rate limiting je per-IP, ne per-tenant

Rate limit profil je definovaný jako requests/window per IP:

- login `10/minute`
- upload `30/minute`
- analysis jobs `20/minute`
- read list `120/minute`
- read detail `60/minute`

To chrání veřejný vstup, ale neřeší tenant fairness dobře:

- shared NAT může trestat více tenantů najednou
- silný tenant rozložený přes více IP může obejít tenantovou férovost

### 6. API DB pool je konzervativní, ale pod 50 tenanty může být rychle plný

Backend pool:

- `DB_POOL_SIZE=10`
- `DB_MAX_OVERFLOW=10`
- `DB_POOL_TIMEOUT=30`

To je rozumné pro malý provoz, ale při burstu:

- API má max cca 20 aktivních DB connection slotů
- další requesty čekají až `30s`
- timeout failne až poměrně pozdě

Pro 50 tenantů s paralelním trafficem je to bez dalších guardrailů spíš hraniční než komfortní.

### 7. Duplicate create_job je pod skutečnou souběžností stále možné

Kód dělá:

- check `get_active_job_for_project_by_type()`
- teprve pak `create_queued_job()`

Testy výslovně říkají, že bez DB locku/constraintu je tam TOCTOU okno. Pod burstem paralelních requestů pro stejný project tedy může vzniknout duplicitní job creation.

### 8. Observability pro load je v kódu slušná, ale runtime neúplný

Kód umí reportovat:

- queue depth
- retry queued
- retry due now
- DLQ active
- oldest queued age
- running age

Ale aktuální runtime běží:

- bez worker heartbeat
- bez worker metrics endpointu
- bez metrics tokenu

Takže latence a saturation signály nejsou dnes dostatečně operativně využitelné.

## B) Co už systém chrání dobře

### 1. Queue growth je bounded

- analysis lane má `analysis_queue_max_depth`
- heavy lane má `heavy_queue_max_depth`
- existuje i globální cap `effective_backpressure_max_queued_jobs`
- queue intake vrací `429`, ne nekonečný růst

Aktuální runtime:

- `analysis_queue_max_depth=1000`
- `heavy_queue_max_depth=250`
- `effective_backpressure_max_queued_jobs=1250`

### 2. Retry není unbounded

- `analysis_job_max_attempts=3`
- backoff base `30s`
- backoff max `300s`
- retry budget je navíc omezen `effective_backpressure_max_retry_inflight`

Aktuální runtime:

- `effective_backpressure_max_retry_inflight=1`

To je přísné, ale safety-first.

### 3. Worker DB pool je oddělený od API poolu

- worker používá separátní engine
- worker pool je přesně sized
- `max_overflow=0`

To je dobrý bulkhead proti domino efektu mezi API a worker vrstvou.

### 4. Heavy lane má separátní semaphore a queue namespace

Když je heavy lane zapnutá:

- heavy workload nesdílí analysis semaphore
- heavy queue má vlastní `heavy:*` namespace
- analysis a heavy tasks mohou běžet paralelně

To je správný základ pro oddělení light vs heavy práce.

### 5. Velké analysis payloady se offloadují

- inline payload cap je `32768` bytes
- větší payload se ukládá mimo DB inline pole

To snižuje DB row bloat a chrání čtení job recordů.

### 6. Redis klient je konzervativní

- krátké connect/read timeouty pro backend
- read failover umí přepnout endpoint
- write operace se po transportní chybě nereplayují potichu

To je správné pro safety queue semantics.

### 7. Load guardrails jsou testované

Dnes jsem ověřil:

- `python-backend/tests/test_db_pool_config.py`
- `python-backend/tests/test_concurrency_guards.py`
- `python-backend/tests/test_operational_load_rehearsal.py`

Výsledek: `61 passed`

To potvrzuje, že pool/backpressure/concurrency guardrails nejsou jen deklarace bez testů.

## C) Co způsobí nestabilitu při růstu

### 1. Heavy inline execution při `worker_heavy_concurrency=0`

To je nejkritičtější. Jakmile přibudou exporty nebo uploady, API latence poroste přímo s objemem CPU/I/O heavy práce.

### 2. Single analysis slot

Jeden pomalý tenant nebo upstream AI problém efektivně pozdrží všechny ostatní tenanty v analysis lane.

### 3. Chybějící tenant fairness mimo analysis jobs

Bez per-tenant heavy caps může jeden tenant:

- zaplavit uploady
- zaplavit export requesty
- vytlačit ostatní z globální queue kapacity

### 4. Whole-file-in-memory upload processing

Při sérii více uploadů se tlak projeví:

- vyšší RSS
- vyšší CPU při validaci a resize
- delší request latency

### 5. Chybějící provider-wide circuit breaker

Claude provider má:

- `120s` request timeout
- 2 retry delaye (`2s`, `4s`)

Co chybí:

- circuit breaker na upstream incident
- temporary open state po sérii rate limit / connection failure

Při scale-out workerů by upstream degradace mohla držet více slotů současně.

### 6. Duplicate job creation okno

Bez DB constraintu nebo locku se při burstu paralelních `create_job` volání může rozbít idempotence na stejném projektu.

### 7. N+1-ish read repair v job listingu

`list_jobs()` pro každý queued/running job znovu dohledává project organization a reconciliation stav. Není to katastrofický pattern, ale při větších historiích jobů je to zbytečný per-item overhead.

### 8. Runtime load observability není dost tvrdě vynucená

Kód má metriky, ale runtime je dnes bez worker observability. To znamená, že latency a saturation mohou růst dřív, než se to provozně odhalí.

## D) Priority fixů P0-P3

### P0

- Zapnout heavy lane v runtime a oddělit export/photo heavy práci od API request cesty.
- Nasadit skutečný worker heartbeat + worker metrics, jinak nebude saturation provozně vidět.
- Odstranit aktuální analysis drift mezi DB a Redis, protože zátěžové testy na rozbitém runtime jsou zavádějící.

### P1

- Zvýšit analysis throughput minimálně na malý pilot-safe profil:
  - `worker_concurrency >= 2`
  - `effective_worker_db_pool_size >= worker_total_concurrency`
- Přidat per-tenant caps pro heavy/export/photo lane.
- Přidat DB-level ochranu proti duplicitnímu active job creation na stejném projektu.

### P2

- Udělat upload cestu memory-safer:
  - menší hard limit pro batch
  - limit počtu souborů na request
  - případně stream/spool-first validace bez držení velkých payloadů najednou
- Přidat provider circuit breaker / incident guard pro AI upstream.
- Omezit inline export generation i v fallback módu.

### P3

- Zmenšit N+1 overhead v `list_jobs()` a podobných read-repair cestách.
- Přidat alert prahy nad queue age, retry inflight, heavy queue depth a DB pool acquire timeouty.
- Doplnit periodické load drills s tenantovou férovostí.

## E) Návrh bezpečných guardrails

### Concurrency limity

- Analysis worker: minimálně `2`, bezpečněji `2-4` pro pilot.
- Heavy worker: minimálně `1`, aby exporty a photo variants neblokovaly API.
- Worker DB pool:
  - držet `WORKER_DB_POOL_SIZE >= WORKER_CONCURRENCY + WORKER_HEAVY_CONCURRENCY`
  - zachovat `max_overflow=0`

### Rate limits

Zachovat stávající IP limity, ale přidat tenant-scoped limity alespoň pro:

- analysis create
- export create
- upload create

Minimální bezpečný návrh:

- analysis create: `10/minute` per tenant
- upload: `10/minute` per tenant
- export: `5/minute` per tenant

### Queue caps

- Zachovat bounded queues.
- Přidat per-tenant heavy queued cap.
- Pro pilot držet:
  - analysis tenant active cap `10`
  - heavy tenant queued cap `5-10`
  - global queued cap raději explicitně, ne jen odvozený default

### Timeouty

- DB acquire timeout `30s` je spíš dlouhý pro API. Pro pilot zvážit `10-15s`.
- Backend Redis timeout `1s` je dobrý.
- AI provider timeout `120s` je použitelný jen při malém concurrency; se scale-outem bude potřeba incident guard.

### Retry caps

- Zachovat `analysis_job_max_attempts=3`
- Zachovat retry backoff bounded
- zvýšit retry inflight budget jen opatrně a jen spolu s vyšší worker concurrency

### Circuit breakers

Minimální bezpečná úprava bez redesignu:

- provider incident breaker:
  - po N transient upstream failures během krátkého okna dočasně rejectovat nové analysis intake `503`
- export engine breaker:
  - při sérii heavy failures krátce zastavit nové export enqueue

## F) Ověřovací load scénáře pro 5 / 10 / 50 tenantů

### 5 tenantů

Scénář:

- každý tenant vytvoří 2 analysis jobs
- 2 tenanti současně uploadují po 3 fotkách
- 1 tenant spustí export burst

Očekávání:

- žádný `503` kromě explicitního backpressure
- queue age zůstane pod `2 min`
- API P95 mimo upload/export pod `1 s`
- žádný tenant nespotřebuje celou queue kapacitu

### 10 tenantů

Scénář:

- každý tenant 3 analysis create requesty
- 5 tenantů dělá souběžné uploady
- 3 tenanti spouští exporty

Očekávání:

- analysis intake vrací kontrolované `429` při tenant cap nebo queue full
- light GET/list endpoints zůstávají responzivní
- žádný stuck retry storm
- DB connection usage se drží pod pool capacity + krátký acquire tail

### 50 tenantů

Scénář:

- burst login + read list traffic
- 20 tenantů spouští analysis
- 10 tenantů spouští upload/export současně

Očekávání:

- bez heavy inline blokování
- bez DB pool starvation
- bez unbounded queue growth
- žádné celosystémové zpomalení způsobené jedním tenantem
- `/health/internal` a metrics ukazují queue age, retry, DLQ a worker liveness v reálném čase

### Pass/fail metriky pro všechny scénáře

- `429` pouze jako očekávaný backpressure, ne jako nekontrolovaný side effect
- `503` pouze při skutečné runtime unavailability
- `oldestQueuedAgeSeconds` nesmí monotonně růst bez recovery
- `retry_inflight_jobs` nesmí růst nad budget
- `worker heartbeat` musí být přítomný
- `heavy lane` nesmí běžet inline na API threadu

## G) Verdikt

`not-ready`

Systém už má dobrý základ:

- bounded queues
- backpressure
- oddělené DB pooly
- bounded retries
- rate limits
- heavy/analysis lane separation v návrhu

Aktuální runtime ale ještě není load-safe:

- analysis processing je single-thread throughput
- heavy path je vypnutý a běží inline v API
- tenant fairness je neúplná
- upload cesta je memory-heavy
- observability pro worker load není v runtime dotažená

Bez těchto minimálních úprav není systém bezpečný ani pro menší pilot se souběžným tlakem více tenantů.
