# Redis Persistence / Failure Isolation Audit

**Datum auditu:** 2026-04-06  
**Scope:** stability, safety, recoverability, Redis failure isolation  
**Verdikt:** `fragile`

## Shrnutí

Redis v tomto systému **není primární business source of truth** pro tokeny, audit ani finální stav analysis jobů. Tyto pravdy jsou v DB:

- token truth: `revoked_tokens`, `user_sessions`, `users.tokens_valid_after`, `users.token_version`
- audit truth: `audit_logs`
- job truth: `analysis_jobs` a navázané výsledky v DB

To je správný základ. Současně ale Redis zůstává **kritický runtime dependency** pro:

- auth brute-force ochranu
- queue transport a lease runtime
- retry scheduling / DLQ transport
- část cache a quota guardů

Největší slabina není „Redis jako jediná pravda“, ale spíš:

1. **sdílený failure domain** pro queue, cache a auth fallback  
2. **worker startup reconciliation je best-effort, ne blocking**  
3. **defaultní sdílený Redis wrapper (`FailoverRedisClient`) neumí všechny metody**, které auth/cache kód očekává (`setex`, `incr`, `expire`)  
4. **auth Redis a queue Redis nejsou v runtime skutečně oddělené**

---

## A) Co Redis v systému skutečně nese

### 1. Queue / transport runtime

Redis nese pouze transportní a lease stav, ne autoritativní job lifecycle:

- durable queue: `analysis:jobs`
- processing lane: `analysis:processing`
- retry schedule: `analysis:retry`
- lease hash/zset: `analysis:lease:*`, `analysis:lease_expiry`
- DLQ transport: `analysis:dlq:*`, `analysis:dlq:active`

Evidence:

- `python-backend/app/worker/queue.py:735`
- `python-backend/app/worker/queue.py:774`
- `python-backend/app/worker/queue.py:892`
- `python-backend/app/worker/queue.py:973`

### 2. Auth protection / token-state acceleration

Redis nese:

- per-account brute-force counter `auth:fail:<email>`
- revoked-token cache entries

Ale autoritativní pravda zůstává v DB:

- token lookup padá zpět do `revoked_tokens`
- session validity jde přes `user_sessions`
- global invalidace jde přes `users.tokens_valid_after` a `token_version`

Evidence:

- `python-backend/app/core/account_limiter.py`
- `python-backend/app/repositories/token_repository.py:190`
- `python-backend/app/repositories/token_repository.py:244`
- `python-backend/app/repositories/token_repository.py:377`
- `python-backend/app/services/auth_service.py:342`
- `python-backend/app/services/auth_service.py:372`

### 3. Cache a tag invalidace

Redis nese pouze odvozená cache data a cache tagy. Kód to explicitně deklaruje jako optimization-only.

Evidence:

- `python-backend/app/core/cache.py`

### 4. Quota / soft runtime counters

Redis nese denní AI quota counter per tenant. To není audit truth ani token truth, ale je to runtime enforcement state.

Evidence:

- `python-backend/app/services/analysis_service.py:465`

### 5. Runtime health / heartbeat

Redis nese worker heartbeat a queue runtime observability.

Evidence:

- `python-backend/app/api/routes/system.py:255`
- `python-backend/app/api/routes/system.py:320`
- `python-backend/app/worker/runner.py:627`

---

## B) Které části jsou bezpečné

### 1. Token truth je DB-authoritative

Tohle je nejsilnější část návrhu.

- login vytváří `user_sessions` v DB
- access/refresh validace čte DB session state
- refresh rotation revokuje starý refresh v DB
- logout / revoke session zapisují revokace do DB
- password reset/change-password zvyšuje `token_version` a nastavuje `tokens_valid_after`

Evidence:

- `python-backend/app/services/auth_service.py:297`
- `python-backend/app/services/auth_service.py:342`
- `python-backend/app/services/auth_service.py:372`
- `python-backend/app/services/auth_service.py:469`
- `python-backend/app/services/auth_service.py:509`
- `python-backend/app/services/auth_service.py:588`

Důsledek:

- restart Redis nezpůsobí ztrátu token truth
- ztráta Redis cache pouze zdraží lookupy a oslabí akceleraci

### 2. Audit truth je DB-authoritative

Security-critical cesty vynucují audit commit do DB a při selhání vracejí chybu místo silent success.

Evidence:

- `python-backend/app/api/routes/admin.py:248`
- `python-backend/app/services/auth_service.py:527`

Důsledek:

- restart Redis nezpůsobí ztrátu audit truth

### 3. Job truth je DB-authoritative

Worker sice používá Redis pro dequeue/lease, ale finální pravda je v `analysis_jobs`:

- queued/running/completed/failed/dead_letter jsou DB stavy
- worker překlápí `queued -> running` v DB
- finalizace výsledku je DB commit
- expired lease reconciliation rozhoduje proti DB, ne proti Redis-only stavu

Evidence:

- `python-backend/app/repositories/analysis_repository.py`
- `python-backend/app/services/analysis_service.py:1236`
- `python-backend/app/services/analysis_service.py:1812`

Důsledek:

- restart Redis sám o sobě nemaže job truth

### 4. Auth flow fail-closed při nedostupném shared protection backendu

Login/account throttle a token-state unavailable vedou na `503`, ne na tichý bypass ochrany.

Evidence:

- `python-backend/app/api/routes/auth.py:68`
- `python-backend/app/api/routes/auth.py:169`
- `python-backend/app/api/routes/auth.py:266`
- `python-backend/app/api/routes/auth.py:304`
- `python-backend/tests/test_auth_lifecycle_hardening.py`

---

## C) Kde je Redis příliš kritický

### 1. Auth Redis a queue Redis sdílí stejný failure domain

V runtime se `get_redis()` vrací `job_queue` a `get_auth_redis()` padá na `job_queue`, pokud neexistuje `auth_token_store`.

Evidence:

- `python-backend/app/api/deps.py:97`
- `python-backend/app/api/deps.py:102`
- `python-backend/app/api/deps.py:112`
- v aplikačním startupu se `auth_token_store` nikde neinicializuje, jen v testech

Důsledek:

- výpadek queue Redis = výpadek auth protection backendu
- auth a queue nejsou oddělené failure domains

### 2. Sdílený wrapper neumí metody, které cache/auth kód používá

`FailoverRedisClient` implementuje `get`, `set`, `delete`, `eval`, `llen`, ... ale neimplementuje `setex`, `incr`, `expire`.

Současně tyto metody používají:

- `cache.py`
- `token_repository.py`
- `analysis_service._enforce_daily_ai_quota()`

Evidence:

- `python-backend/app/core/redis_client.py`
- `python-backend/app/core/cache.py`
- `python-backend/app/repositories/token_repository.py:126`
- `python-backend/app/services/analysis_service.py:505`

Důsledek:

- revoked-token cache write není spolehlivá na sdíleném wrapperu
- cache invalidace/tagging není spolehlivá na sdíleném wrapperu
- daily quota enforcement je křehká, pokud běží přes stejný shared wrapper

Tohle je **P0/P1 architekturní chyba rozhraní**, ne jen ops detail.

### 3. Queue recoverability závisí na worker startup reconciliation

To je dobrý mechanismus, ale není fail-fast.

- worker startup purgeuje orphan Redis transport
- requeueuje DB queued jobs bez transportu
- resetuje stale running -> queued

Ale pokud reconciliation selže, worker jen zaloguje chybu a pokračuje dál.

Evidence:

- `python-backend/app/worker/runner.py:1439`
- `python-backend/app/worker/runner.py:1599`
- `python-backend/app/worker/runner.py:1640`

Důsledek:

- Redis data loss po restartu je teoreticky recoverable
- prakticky je recovery best-effort, ne enforceovaný invariant

### 4. `/ready` toleruje degraded processing stav

API readiness umí vrátit HTTP `200`, i když processing plane není green.

Evidence:

- `python-backend/app/api/routes/system.py:1000`
- `python-backend/app/api/routes/system.py:1096`
- `python-backend/app/api/routes/system.py:1105`
- `python-backend/tests/test_health_readiness_semantics.py`

Důsledek:

- systém má explicitní degraded mode, ale pro orchestration může být příliš benevolentní
- to není ztráta truth, ale je to failure isolation/slaměný safety problém

### 5. Queue remains operationally critical for job progress

Job truth se neztratí, ale bez Redis:

- nové enqueue selžou `503`
- dequeue se zastaví
- retry promotion se zastaví
- background processing není servable

Evidence:

- `python-backend/app/api/routes/analysis_jobs.py`
- `python-backend/app/main.py:169`
- `python-backend/app/worker/runner.py:604`

To je přijatelná závislost jen pokud degraded mode a recovery jsou opravdu tvrdé.

---

## D) Priority fixů P0–P3

### P0

- Oddělit `auth_token_store` od `job_queue` v reálném startupu. Auth Redis musí mít vlastní klient a vlastní endpoint/failure domain.
- Opravit Redis client kontrakt: buď doplnit `setex`/`incr`/`expire` do `FailoverRedisClient`, nebo nepoužívat queue wrapper pro cache/auth code paths.
- Udělat worker startup reconciliation fail-fast v strict env. Pokud reconciliation selže, worker nesmí pokračovat do `started`.
- Zapsat invariant: Redis loss nesmí ztratit DB job truth a musí být deterministicky rekonstruovatelný před návratem processing plane do `ready`.

### P1

- Přidat explicitní startup inicializaci `app.state.auth_token_store`.
- Přidat metric/alert na `DB queued job without Redis transport` a `orphan Redis transport without DB row`.
- Přitvrdit `/ready` nebo provozní routování tak, aby degraded processing nebyl omylem považován za plně ready.

### P2

- Přidat interní reconcile command/endpoint pro auditovatelný repair queue transportu vůči DB.
- Přidat Redis chaos testy pro startup a běžící dequeue/retry flow.
- Oddělit také quota/cache store od queue store, nebo alespoň odlišit klientský wrapper.

### P3

- Zavést separátní Redis topology profile:
  - `REDIS_QUEUE_URL`
  - `REDIS_AUTH_URL`
  - `REDIS_CACHE_URL`
- Přidat periodický reconciliation dry-run report, nejen startup repair.

---

## E) Návrh bezpečných invariantů

### DB authoritative where needed

- token validity musí být určena pouze přes DB session/revocation state a `token_version`
- audit trail musí existovat pouze jako DB truth
- `analysis_jobs.status` musí být jediná autorita pro job lifecycle
- finální export/photo/result stav nesmí být inferován z Redis-only transportu

### Redis derivative where possible

- revoked-token cache je jen acceleration layer
- cache/tag invalidace je jen derivative layer
- queue payload je transport, ne business truth
- retry schedule a DLQ jsou operational transport evidence, ne source of truth o tom, zda job existuje a v jakém je business stavu

### Explicit degraded mode

- auth protection backend unavailable => `503`, ne bypass
- token-state backend unavailable => `503`, ne fail-open
- queue unavailable => API může zůstat read-servable, ale enqueue/dequeue musí jít do explicitně degraded režimu
- processing readiness musí být oddělená od API readiness a používaná jako skutečný gate

### Failure isolation

- auth Redis nesmí sdílet failure domain s queue Redis
- cache failure nesmí ovlivnit token truth ani queue truth
- queue failover wrapper nesmí být používán tam, kde chybí potřebný command surface

---

## F) Ověření

## 1. Redis restart

**Co je dnes dobré:**

- token truth se neztratí, protože je v DB
- audit truth se neztratí, protože je v DB
- worker startup umí requeue DB queued jobs a purge orphan transport

**Co chybí do plného bezpečí:**

- reconciliation není fail-fast
- auth/cache store je defaultně sdílený s queue store

**Status:** `partially covered by code/tests, operationally still fragile`

Evidence:

- `python-backend/tests/test_r19_job_queue.py`
- `python-backend/tests/test_r36_stale_job_recovery.py`
- `python-backend/app/worker/runner.py:1439`

## 2. Redis data loss simulation

**Expected safe behavior:**

- DB `queued/running` jobs zůstanou pravdivé
- při worker startupu se chybějící transport zrekonstruuje z DB
- orphan Redis payloady se purgeují

**Current weakness:**

- pokud startup reconciliation selže, worker přesto pokračuje

**Status:** `recoverable by design, not hard-enforced`

## 3. Redis unavailable on startup

**Backend:**

- v strict env fail-fast na startupu

**Worker:**

- v strict env fail-fast na startupu

Evidence:

- `python-backend/app/main.py:169`
- `python-backend/app/worker/runner.py:604`

**Status:** `good`

## 4. Redis unavailable during auth

**Account throttle / protection path:**

- login/change-password fail-closed na `503`

**Token-state path:**

- refresh/logout/get_current_user fail-closed na `503`

Evidence:

- `python-backend/app/api/routes/auth.py:68`
- `python-backend/app/api/routes/auth.py:169`
- `python-backend/app/api/routes/auth.py:266`
- `python-backend/app/api/routes/auth.py:304`
- `python-backend/tests/test_auth_lifecycle_hardening.py`

**Status:** `safe`

## 5. Redis unavailable during dequeue

**Current behavior:**

- processing plane se zastaví
- job truth v DB se nemaže
- po návratu Redis lze queue obnovit přes reconciliation/reaper

**Current weakness:**

- progress je blokován
- recovery není hard-gated na successful reconcile

**Status:** `safe for truth, fragile for recoverability`

---

## G) Verdikt

**`fragile`**

Ne `blocked`, protože:

- token truth není Redis-only
- audit truth není Redis-only
- job truth není Redis-only
- auth protection při výpadku Redis fail-closed
- startup v strict env fail-fast

Ale ne `Redis-safe`, protože:

- auth a queue defaultně sdílí stejný Redis failure domain
- shared wrapper neodpovídá potřebám auth/cache code paths
- queue recovery po Redis loss spoléhá na startup reconciliation, která není blocking
- `/ready` dovoluje příliš měkký degraded režim

## Doporučený cílový stav

Pro verdict `Redis-safe` musí platit:

- `auth_token_store` je samostatný klient i samostatný endpoint
- queue wrapper implementuje celý command surface, který jeho konzumenti používají, nebo se vůbec nepoužívá mimo queue
- worker startup reconciliation je hard gate v strict env
- `DB queued jobs without transport = 0` je měřený a alarmovaný invariant
- orchestrace používá strict processing readiness, ne tolerantní API-ready semantiku
