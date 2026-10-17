# Recovery / Restart Audit 2026-04-05

## Verdikt

Aktuální stav je `blocked`, nikoli `recovery-safe`.

Důvod není jen teoretický. V živém runtime je prokazatelný drift mezi DB a Redis transportem:

- `analysis_jobs`: `22` jobů v DB je ve stavu `queued`
- Redis `analysis:jobs`: jen `5` položek
- `analysis:processing`: `0`
- `analysis:retry`: `0`
- `worker:heartbeat*`: `0` klíčů
- v DB není žádný `running` job, ale queued backlog je starý od `2026-04-01 17:29:27+00:00`
- heavy lane je v běžícím runtime vypnutý: `worker_heavy_concurrency=0`

To znamená, že recovery kontrakt je v kódu částečně navržený dobře, ale v běžícím systému není aktuálně dotažený do bezpečného provozního stavu.

## A) Aktuální restart/recovery kontrakt

### Analysis lane

- Autoritativním zdrojem pravdy je DB, konkrétně `analysis_jobs.status`, `lease_token`, `worker_id`, `leased_at`, `heartbeat_at`.
- Redis `analysis:*` je transportní vrstva, ne autoritativní business stav.
- Dequeue je atomický Lua krok: položka se přesune `analysis:jobs -> analysis:processing` a současně dostane lease.
- Lease renewal obnovuje Redis lease i DB heartbeat.
- Expired lease reaper vrací job zpět do `queued` pouze tehdy, když DB stále potvrzuje stejný lease a heartbeat je skutečně stale.
- Worker startup spouští reconciliation:
  - purge orphan Redis transportů bez aktivního DB jobu
  - reset stale `running -> queued`
  - requeue DB `queued` jobů, které v Redis transportu chybí
- Backend startup tohle nedělá. Backend jen ověří DB/schema/storage a připojí Redis queue klienta.
- Backend read path umí částečný self-healing při `get_job` a `list_jobs`, ale jen při čtení těchto endpointů.

### Heavy lane

- Heavy práce běží v odděleném Redis namespace `heavy:*`.
- V aktuálním runtime je heavy lane vypnutý: `worker_heavy_concurrency=0`.
- V kódu worker startup reconciliuje incomplete exporty (`pending` / `generating`) chybějící v `heavy:*`.
- Ekvivalentní startup reconciliation pro incomplete photo variant joby neexistuje.
- Heavy expired lease reaper je Redis-transport orientovaný, ne DB-authoritative jako analysis lane.

### Backend / Redis / DB restart kontrakt

- Backend restart zachová auth flow a API readiness, což je pokryto testem.
- Redis outage shodí strict processing readiness na `503`, po obnově se vrátí na `200`.
- Postgres outage shodí API readiness a po návratu se readiness obnoví.
- `/api/v1/ready` ale umí vracet `200` i při degraded processing stavu, takže návrat do provozu není dostatečně tvrdě gateovaný.

## B) Co je robustní

- Analysis queue má silný lease model: dequeue, ack, renew, retry scheduling i expired requeue používají atomické Redis skripty.
- Expired finalize kontroluje `leased_at_ms`, takže starý reaper nepřepíše nově obnovený lease.
- DB lease ownership je při recovery chyb workeru vynucená před finalizací stavu.
- `reconcile_expired_lease()` správně:
  - dropne final job
  - dropne stale lease po renew
  - dropne lease s čerstvým heartbeat
  - resetne stale `running` zpět do `queued`
- Worker startup reconciliation pro analysis lane je poměrně silná a umí purge i requeue.
- Exporty fail-closed:
  - `completed` se nastaví až po zápisu artefaktu a jeho ověření
  - missing artefact u `completed` exportu je degradován na `failed`
- Photo variant processing fail-closed:
  - chybějící source photo znamená `failed`
  - terminální stavy `ready` a `failed` jsou idempotentní
- Konfigurace vynucuje deterministické vztahy timeoutů:
  - `WORKER_JOB_REAP_INTERVAL_SECONDS < WORKER_JOB_LEASE_TIMEOUT_SECONDS`
  - lease timeout musí být alespoň `60s`
  - readiness grace nesmí být delší než lease timeout

### Prokázané testy spuštěné 2026-04-05

- `python-backend/tests/test_operational_resilience_drill.py`: `5 passed`
- cílené recovery testy z `python-backend/tests/test_worker_runner.py`: `7 passed`
- cílené export recovery testy z `python-backend/tests/test_export_ttl_management.py`: `3 passed`
- retry/lease testy `python-backend/tests/test_r19_job_queue.py` a `python-backend/tests/test_retry_system.py` s recovery filtrem: `26 passed`

## C) Kde hrozí nekonzistence nebo ztráta stavu

### 1. Live runtime je už teď v driftu

- V DB je `22` queued analysis jobů, ale v Redis queue jen `5` položek.
- Redis navíc drží orphan transportní položky, které v DB vůbec neexistují.
- Worker heartbeat chybí úplně.
- To je přímý důkaz, že recovery dnes závisí na worker startup reconciliation nebo na read-time self-healing, ne na průběžně konzistentním runtime.

### 2. Backend restart sám o sobě stav nesrovná

- Backend startup nespouští reconciliation analysis/export/photo transportu.
- Pokud worker neběží, backend se může vrátit do servable stavu, ale queue realita zůstane rozbitá.
- To je problém pro kontrolovaný návrat do provozu po backend-only restartu.

### 3. Worker startup reconciliation není fail-fast

- `worker.startup_reconciliation_failed` je jen logovaná chyba.
- Worker po ní pokračuje dál do `worker.started`.
- To dovolí green-ish návrat workeru i po neúspěšné recovery inicializaci.

### 4. Heavy lane nemá stejně silný recovery kontrakt jako analysis lane

- Heavy reaper nereferencuje DB autoritativně.
- Startup reconciliation existuje pro exporty, ale ne pro incomplete photo variant processing.
- Pokud se při heavy lane ztratí Redis transport a DB foto zůstane v `uploaded` nebo `processing`, neexistuje ekvivalent analysis self-healing při startu.

### 5. Queue finalize chyby spoléhají na pozdější reconciliation

- Když analysis worker po DB finalizaci selže při `schedule_retry` nebo `move_to_dlq`, chyba se jen zaloguje.
- Stav je sice většinou později rekoncilovatelný, ale není to okamžitě atomické ani auditně uzavřené.
- U heavy lane je to slabší: worker job se v `finally` ackuje vždy a recovery spoléhá hlavně na idempotenci export/photo service.

### 6. Exporty a uploady při intake failure spíš fail-closed než recover

- Export enqueue failure převádí pending export rovnou na `failed`.
- Photo enqueue failure převádí photo `processing_status` rovnou na `failed`.
- To je safe z pohledu double processing, ale není to self-healing recovery model.

### 7. `/ready` může hlásit green při degraded processing realitě

- Strict processing readiness je správně tvrdší.
- Standardní `/ready` ale může vracet `200`, i když worker chybí nebo processing readiness není skutečně ready.
- To je riziko při restart storm scénářích a automatickém návratu trafficu.

### 8. Aktuální runtime neprokazuje recovery heavy lane

- `worker_heavy_concurrency=0`
- `redis_heavy_queue=0`
- `redis_heavy_processing=0`
- `incomplete_exports=0`
- `incomplete_photos=0`

To znamená, že restart backendu/workeru/Redis/DB pro async exporty a async photo processing je v běžícím runtime neověřený. Je jen deklarovaný v kódu a částečně krytý testy.

## D) Priority fixů P0-P3

### P0

- Nasadit skutečný worker a vynutit, aby processing readiness byl hard gate pro návrat trafficu. V pilot/prod nesmí `/ready` vracet `200`, pokud worker chybí nebo queue/processing není ready.
- Zrušit log-only startup reconciliation failure v workeru. V strict prostředí musí neúspěšná startup reconciliation blokovat start.
- Vyčistit aktuální drift DB vs Redis a potvrdit nulový orphan/stuck stav po restartu workeru.

### P1

- Přidat startup reconciliation pro photo variant lane obdobně jako pro exporty.
- Přidat explicitní recovery audit metriky:
  - DB queued without Redis transport
  - orphan Redis transport without DB row
  - stale running jobs recovered
  - startup reconciliation success/failure counts
- Zpevnit analysis finalize flow tak, aby retry/DLQ write failure vytvořila auditně dohledatelný recovery task, ne jen log.

### P2

- Přidat jednotný interní recovery command, který udělá inspect + reconcile a vrátí přesná čísla purge/requeue/reset operací.
- Rozšířit integrační testy o backend-only restart bez workeru a o heavy/photo restart scénáře.
- Přidat alarm na backlog stáří queued jobů a na chybějící worker heartbeat.

### P3

- Udržovat pravidelný chaos drill pro:
  - worker kill během lease
  - Redis restart během dequeue/finalize
  - DB short outage během heartbeat renew
- Doplnit runbook pro restart storm a partial recovery.
- Udržovat recovery test suite bez driftu mock kontraktů.

## E) Minimální bezpečné úpravy

- Přepnout load balancer / orchestraci na strict processing readiness, ne na dnešní tolerantní `/ready`.
- Udělat worker startup reconciliation blocking v strict prostředí.
- Přidat `reconcile_startup_photos()` pro `processing_status in ('uploaded','processing')` s missing heavy transportem.
- Přidat jeden interní audit endpoint nebo CLI:
  - `db queued count`
  - `db running count`
  - `redis queued count`
  - `redis processing count`
  - `orphan redis jobs`
  - `db queued missing transport`
  - `stale running jobs`
- V strict prostředí odmítnout green stav, pokud existuje:
  - stale running job
  - queued DB job without transport
  - orphan processing lease

## F) Test matrix

### 1. Backend restart

Setup:
queued job v DB, worker běží i neběží v oddělených variantách.

Očekávání:

- restart backendu nesmí změnit `analysis_jobs.status`
- bez workeru nesmí backend hlásit full ready processing stav
- po startu backendu musí být drift explicitně vidět v readiness / audit metrice
- auth flow zůstane funkční

Pass kritéria:

- žádný job nepřejde `queued -> lost`
- žádný `running` job nevznikne bez workeru
- `/ready/processing?strict=1` odpovídá realitě

### 2. Worker restart

Setup:
analysis job v `running`, worker kill uprostřed běhu.

Očekávání:

- po `lease_timeout + reap_interval` se job vrátí do `queued`
- nový worker ho zpracuje právě jednou
- nevznikne druhý `analysis_result`

Pass kritéria:

- max `1` terminal result row na job
- po recovery `analysis:processing = 0`
- v DB nezůstane stale `running`

### 3. Redis restart

Setup:
queued i running analysis job, worker aktivní.

Očekávání:

- strict processing readiness spadne na `503`
- po obnově Redis a restartu workeru proběhne reconciliation
- DB queued jobs missing transport budou znovu enqueue
- orphan Redis transporty budou purge

Pass kritéria:

- `db queued count == redis queued count + redis retry count + redis processing entries mapped to DB`
- `orphan redis jobs = 0`
- worker heartbeat se obnoví

### 4. DB reconnect / short outage

Setup:
analysis job v běhu, během lease renew krátce odpojit DB.

Očekávání:

- worker ztratí možnost obnovit DB heartbeat
- lease po timeoutu vyexpiruje
- reaper vrátí job do `queued`
- po návratu DB dojde k deterministickému opakování nebo failu, ne k silent loss

Pass kritéria:

- žádný job nezůstane viset v `running` bez čerstvého heartbeat
- nevznikne duplicitní completion

### 5. Restart během běžícího jobu

Setup:
samostatně pro analysis, export a photo variant processing.

Očekávání:

- analysis: recovery přes lease/reaper
- export: po restartu buď doběhne do `completed`, nebo skončí auditně v `failed`, nikdy ne v tichém `generating`
- photo variants: po restartu buď `ready`, nebo `failed`, nikdy trvale `uploaded/processing` bez transportu

Pass kritéria:

- `stale running analysis jobs = 0`
- `incomplete exports without heavy transport = 0`
- `incomplete photos without heavy transport = 0`
- storage artefakty odpovídají DB stavu

## G) Verdikt

`blocked`

Analysis lane má slušně navržené recovery jádro, ale živý runtime už teď prokazuje drift a chybějící worker. Backend-only restart neumí stav srovnat, worker startup reconciliation není fail-fast a heavy/photo lane nemá stejně silný self-healing kontrakt jako analysis lane. Dokud nebude odstraněn aktuální drift, ztvrdne readiness gate a doplní se startup reconciliation alespoň pro photo heavy flow, není systém recovery-safe pro pilotní provoz.
