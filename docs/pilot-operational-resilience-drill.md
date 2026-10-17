# Pilot Operational Resilience Drill

Krátký, cílený operational drill pro single-node nebo malý pilot stack.

Nejde o chaos engineering. Cílem je ověřit, že typické restart a outage scénáře:

- neztratí joby
- nerozbijí queue orchestration
- nenechají API/auth v tichém polorozbitém stavu
- mají deterministickou recovery cestu

## Authoritative Signals

Sleduj vždy tyto zdroje:

- `GET /api/v1/health`
- `GET /api/v1/ready`
- `GET /api/v1/ready/processing?strict=1`
- `GET /api/v1/health/internal` jako superadmin
- `GET /metrics` s bearer tokenem
- worker lokální heartbeat soubor přes `python -m app.worker.healthcheck`

Klíčové signály:

- `jobProcessingReady`
- `workerState`
- `queueState`
- `jobs.running`
- `jobs.queued`
- `jobs.processing`
- `jobs.queueLength`
- `jobs.maxRunningAgeSeconds`
- `novu_queue_length`
- `novu_processing_jobs`
- `novu_jobs_running`
- `novu_jobs_queued`
- `novu_reaper_requeues_total`

## Deterministic Drill Command

Tento repozitář teď obsahuje opakovatelný deterministic rehearsal:

```powershell
& .\python-backend\.venv\Scripts\python.exe -m pytest python-backend\tests\test_operational_resilience_drill.py -q
```

Pokrývá:

1. backend restart
2. worker restart během leased jobu
3. Redis outage/recovery
4. PostgreSQL outage/recovery
5. storage dependency outage/recovery

## Live Pilot Drill Setup

Před živým drillem:

1. spusť stack
2. ověř `health`
3. ověř `ready`
4. ověř `ready/processing?strict=1`
5. přihlas managera a superadmina
6. připrav 1-3 test case flowy a několik analysis jobů

Příklad:

```powershell
docker compose up -d db redis backend worker
Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/v1/health
Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/v1/ready
Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/v1/ready/processing?strict=1
```

## Scenario 1: Backend Restart During Normal API/Auth Traffic

Setup:

- běžící backend
- funkční login
- alespoň jeden aktivní uživatel

Kroky:

```powershell
docker compose restart backend
```

Paralelně opakuj:

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/v1/health
Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/v1/ready
```

Očekávané chování:

- `health` může krátce spadnout během procesu restartu
- po náběhu se vrátí `200`
- `ready` se vrátí do `200`
- refresh token vydaný před restartem zůstane použitelný
- `auth/me` po refreshi funguje bez manuálního zásahu

Co sledovat:

- backend log: startup checks, schema check, storage check
- žádné tiché `500` po restartu
- žádný neplatný session state jen kvůli restartu procesu

PASS:

- restart nepoškodí auth flow a API se vrátí do `ready`

PASS WITH RISK:

- recovery funguje, ale restart okno je delší nebo vznikají přechodné `5xx`

FAIL:

- refresh token po restartu nefunguje
- `ready` se nevrátí do zelené
- API zůstane v nekonzistentním stavu

## Scenario 2: Worker Restart During In-Flight Job

Setup:

- worker běží
- `ready/processing?strict=1` je zelené
- enqueue 3-10 analysis jobů

Kroky:

1. enqueue joby
2. počkej, až aspoň jeden přejde do `running`
3. restartuj worker

```powershell
docker compose restart worker
```

Očekávané chování:

- rozpracovaný job nesmí zmizet
- lease expirovaného jobu se po reap intervalu deterministicky zreconciluje
- job se vrátí do `queued` nebo korektně dokončí podle stavu lease/DB
- queue depth může krátce poskočit, ale musí znovu drainovat

Co sledovat:

- worker log: `worker.lease_reaper_processed`
- `/health/internal`: `jobs.running`, `jobs.queued`, `jobs.processing`, `maxRunningAgeSeconds`
- `/metrics`: `novu_reaper_requeues_total`

PASS:

- žádný job nezmizí a queue se po restartu znovu rozběhne

PASS WITH RISK:

- recovery proběhne, ale jen po dlouhém lease timeoutu nebo s výrazným backlogem

FAIL:

- job visí bez recovery
- job je ztracený
- queue přestane drainovat

## Scenario 3: Redis Restart

Setup:

- backend i worker běží
- processing readiness je zelená

Kroky:

```powershell
docker compose restart redis
```

Očekávané chování:

- `health` může zůstat `200`, protože je to liveness
- `ready/processing?strict=1` musí spadnout do `503`
- `queueState` musí přejít do `unavailable` nebo degradovaného stavu, ne tvářit se zeleně
- po obnově Redis se processing readiness vrátí deterministicky zpět

Co sledovat:

- backend log: Redis queue unavailable
- `/ready/processing?strict=1`: `jobProcessingReady=false`
- `/health/internal`: queue state, worker state

PASS:

- outage je transparentně detekovaný a recovery se vrátí bez ručního zásahu do DB

PASS WITH RISK:

- recovery funguje, ale přechodové stavy jsou dlouhé nebo matoucí

FAIL:

- queue je rozbitá potichu
- readiness zůstává falešně zelená během outage

## Scenario 4: PostgreSQL Restart

Setup:

- běžící API
- aktivní auth/API traffic

Kroky:

```powershell
docker compose restart db
```

Očekávané chování:

- `health` může zůstat `200`
- `ready` musí spadnout do `503`
- po návratu DB se `ready` vrátí do `200`
- auth/API nesmí předstírat readiness bez DB

Co sledovat:

- backend log: database connectivity/schema probe errors
- `/ready`
- `/health/internal`: `db`

PASS:

- readiness korektně spadne a po návratu DB se sama obnoví

PASS WITH RISK:

- obnova funguje, ale vyžaduje delší warm-up

FAIL:

- API vrací `ready` bez DB
- po návratu DB zůstane stuck not-ready

## Scenario 5: Storage / External Dependency Outage

Setup:

- storage backend je používaný běžným flow

Bezpečná varianta:

- simuluj outage přes zablokovaný bucket endpoint, odpojení storage proxy, nebo dočasný deny pravidlem

Očekávané chování:

- `health` může zůstat `200`
- `ready` musí jít do `503`
- upload/preview flow musí failnout explicitně, ne tiše
- po návratu storage se readiness vrátí

Co sledovat:

- backend log: storage availability check failed
- `/ready`
- `/health/internal`: `storage`

PASS:

- readiness korektně odráží outage a po obnově se vrátí bez manuální opravy

PASS WITH RISK:

- recovery funguje, ale flow má dlouhé timeouty

FAIL:

- storage outage je skrytý
- upload flow zůstane nekonzistentní

## Minimal Acceptance For Pilot

Pilot-ready operational profile:

- backend restart je recoverable bez ztráty auth flow
- worker restart nepřijde o leased joby
- Redis outage shodí processing readiness, ne health
- PostgreSQL outage shodí API readiness, ne health
- storage outage se projeví v readiness a recovery je deterministická

Neakceptovatelné i pro malý pilot:

- ztracené joby
- stuck `running` joby bez reaper recovery
- falešně zelené readiness endpointy během outage
- nutnost ručních DB zásahů po restart scénáři
