# FORENZNÍ AUDIT — NOVU BUILDER
**Datum:** 2026-03-30 | **Auditor:** Claude Sonnet 4.6 | **Rozsah:** Full-stack, based on live code

---

## METODOLOGIE

Audit byl proveden přímým čtením kódu — ne z dokumentace ani z paměti předchozích sezení. Porovnáno s historickým audit dokumentem `16_production_audit_2026-03-30.md`. Zjistil jsem, že velká část kritických a vysokých rizik z toho dokumentu byla **mezitím opravena**. Tento audit odráží skutečný dnešní stav.

---

## EXECUTIVE SUMMARY

| Oblast | Stav |
|---|---|
| Security & Auth | Produkční kvalita |
| DB pool architektura | Opraveno + vynikající dual-pool design |
| Worker architektura | Opraveno + concurrent execution |
| docker-compose | Produkce připravena |
| Zbývající rizika | Střední a nízká — žádné kritické blokátory |
| Test coverage | Výjimečná (60+ test souborů) |

**VERDIKT: Systém je schopen produkce pro malé/střední zatížení.**
Zbývající problémy jsou střední závažnosti a nebrání nasazení, ale měly by být řešeny v prvních týdnech provozu.

---

## ČÁST 1 — SILNÉ STRÁNKY (PLUSY)

### ✅ P1 — Dual-pool DB architektura: vynikající design

`python-backend/app/db/session.py`

Projekt má **dvě oddělené DB connection pools** — `AsyncSessionFactory` pro HTTP requesty a `WorkerAsyncSessionFactory` pro background joby. Worker pool má `max_overflow=0` (přesně dimenzovaný) a session není držena při AI analýze (0–180s). HTTP pool je dimenzovaný přes env vars `DB_POOL_SIZE` + `DB_MAX_OVERFLOW` + `pool_recycle=1800`.

Toto je profesionální řešení, které zabraňuje vyčerpání poolů a connection starvation při AI analýzách. Obvykle v projektech v tomto stadiu chybí úplně.

---

### ✅ P2 — Concurrent worker s asyncio.Semaphore

`python-backend/app/worker/runner.py:413-425`

```python
concurrency_limiter=asyncio.Semaphore(worker_concurrency),
inflight_tasks=set(),
```

Worker zpracovává joby **souběžně** přes `asyncio.create_task` + `Semaphore`. Každá worker instance má unikátní `worker_instance_id`, heartbeat je per-instance. Concurrency je konfigurována přes `WORKER_CONCURRENCY` env var.

---

### ✅ P3 — Multi-tenant isolation: systematická ochrana

- `organization_id` filtrace je vynucena na repository vrstvě pro všechny list/read operace
- `update_manual_selection_by_result_id` má parametr `organization_id` — cross-tenant write je blokovaný na service vrstvě
- `get_project_lean` je konzistentně používán v `images.py` a dalších routes pro org guard bez heavy fetch
- Audit trail zachytí každou mutaci s user_id, org_id, action

---

### ✅ P4 — Security layer: JWT, revocation, brute-force

- JWT `jti` revocation via `RevokedToken` tabulka — logout skutečně funguje
- `account_limiter.py`: brute-force throttle na email (Redis-backed)
- `sanitize_request_id()` v `request_id.py`: délka, ASCII, control-char validace
- ILIKE search escapuje `%`, `_`, `\` přes `_LIKE_ESCAPE_CHAR`
- Upload validace: typ, velikost, bezpečný filename

---

### ✅ P5 — Fail-fast konfigurace s jasnými error messages

`python-backend/app/core/config.py` má 15+ validátorů na produkční nastavení. Startup selže okamžitě s čitelnou chybou pokud chybí JWT_SECRET, CORS je localhost, local storage v produkci, pool misconfiguration atd. Operator ví přesně co opravit.

---

### ✅ P6 — docker-compose: kompletní produkční konfigurace

`docker-compose.yml` správně mapuje všechny povinné env vars (`STORAGE_BACKEND`, `CORS_ALLOWED_ORIGINS`, `METRICS_AUTH_TOKEN`, `APP_BASE_URL`). Redis má password, healthchecky jsou na všech services, worker jako separátní service s restart policy.

---

### ✅ P7 — Výjimečná test coverage

60+ test souborů pokrývají: tenant isolation, auth lifecycle, concurrency guards, upload security, worker heartbeat, DB pool config, alembic chain, backup/restore E2E, export TTL, storage consistency. Toto je neobvyklá úroveň kvality pro projekt v tomto stadiu.

---

### ✅ P8 — Export + Storage Consistency services (nové)

Nové: `export_service.py`, `export_repository.py`, `storage_consistency_service.py`. Export má TTL management (worker cleanup každých 5 minut), storage consistency service hlídá soulad DB ↔ storage. Správná architektura s oddělenými repository a service vrstvami.

---

## ČÁST 2 — RIZIKA

### 🟠 R1 — `_deny_counts`: in-process dict, multi-instance slepota

**Soubor:** `python-backend/app/core/audit.py:88`

```python
_deny_counts: dict[str, tuple[float, int]] = {}
```

**Problém:** Každá backend instance má vlastní dict. Při 2 instancích (load balancer) útočník získá `2 × _DENY_MAX_PER_WINDOW` pokusů před throttle. Dict nikdy nemaže staré záznamy — pro 10k users s deny events = nekontrolovaný memory leak.

**Riziko:** Střední — bypassovatelný cross-tenant probing rate limit, postupný memory leak.

**Řešení:** Přesunout do Redis (stejný pattern jako `account_limiter.py`), nebo přidat LRU eviction.

---

### 🟠 R2 — account_limiter: sliding TTL místo fixed window

**Soubor:** `python-backend/app/core/account_limiter.py:84-85`

```python
pipe.incr(key)
pipe.expire(key, _WINDOW_SECONDS)  # TTL se resetuje na každý pokus
```

`expire()` je voláno po každém `incr` — okno se posouvá od *posledního* pokusu, ne od *prvního*. Útočník: 9 pokusů → čekat 14:50 min → 1 pokus → counter se neresetnul, nové TTL. Efektivně 9 pokusů každých ~15 minut místo pevného okna.

**Riziko:** Nízké-střední — je to sliding window místo fixed, ne úplné obejití.

**Řešení:** Použít `set key 0 EX window_seconds NX` pro init a `incr` bez resetu TTL.

---

### 🟠 R3 — AuditMiddleware: extra DB session na každou mutaci

**Soubor:** `python-backend/app/core/audit.py:262`

Middleware otevře novou session pro obohacení actora (DB lookup uživatele) i přesto, že data jsou v contextvars. Fallback na DB lookup nastane jen pokud contextvary neobsahují email+org — ale při každém requestu kde kontextvary nejsou plné jde extra SELECT.

**Riziko:** Nízké (optimalizace) — contextvary jsou obvykle plné po autentizaci, ale edge cases (public endpoints, systémové akce) generují zbytečné DB roundtripy.

---

### 🟡 R4 — Non-atomic enqueue + DB create job

**Soubory:** `analysis_service.py` + `worker/queue.py`

Sekvence: `create_job()` (DB write) → `enqueue_analysis_job()` (Redis write). Tyto dvě operace nejsou atomické:
- DB OK → Redis selže → Job je `queued` v DB ale nikdy nezpracován (stuck job)
- Redis OK → backend padne před DB write → worker dostane payload bez DB záznamu → `job not found`

**Riziko:** Nízké-střední — nastane jen při výpadku Redis nebo backendu přesně mezi operacemi. Stale-job recovery (R-36) zachytí část, ale ne Redis-only scénář.

**Řešení (dlouhodobé):** Outbox pattern nebo saga.

---

### 🟡 R5 — Rolling restart: race condition stale job recovery vs. worker

**Soubor:** `python-backend/app/main.py` (stale-job recovery při startupu)

Při rolling update (Kubernetes):
1. Backend A restartuje → označí `running` job jako `failed`
2. Worker stále zpracovává job (z Redis fronty)
3. Worker zavolá `mark_job_running()` na `failed` job → `InvalidAnalysisJobStatusTransition` → worker přeskočí

Job skončí jako `failed` i když byl dokončen. Data nejsou ztracena (projekt zůstane), ale uživatel vidí chybový stav a musí znovu spustit analýzu.

**Riziko:** Nízké (edge case v Kubernetes rolling update) — v docker-compose je to bezpředmětné.

---

### 🟡 R6 — AuditLog roste bez archivace

**Soubor:** `python-backend/app/models/domain.py` tabulka `audit_logs`

Žádné partitionování, žádná retention policy, žádný TTL. Odhad: 10k users × 100 mutací/den = 1M řádků/den, 30 dnů = 30M řádků. Pro menší zatížení (stovky users) to není problém v prvních měsících.

**Riziko:** Nízké v krátkodobém horizontu, střední pro 6+ měsíců produkce.

**Řešení (P2):** PostgreSQL table partitioning by month + archivační job.

---

### 🟡 R7 — Prometheus: Redis queue depth není metrika

**Soubor:** `python-backend/app/api/routes/system.py`

`JOBS_QUEUED` metrika čte z DB (`COUNT` analysis jobs), nikoliv z `LLEN analysis:jobs` v Redis. Pokud Redis obsahuje joby které ještě nebyly zapsány do DB (viz R4), nebo DB je transiently unavailable, metrika neukazuje skutečnou délku fronty.

**Riziko:** Nízké — monitoring gap, ne funkční problém.

---

### 🟡 R8 — Multi-file upload: partial failure bez inventáře

**Soubor:** `python-backend/app/api/routes/images.py`

Soubor 1 se uloží → soubor 2 selže validací → klient dostane 415 bez informace o souboru 1. Retry uploaduje soubor 1 znovu = duplikáty.

**Riziko:** Nízké-střední — špatné UX, duplikáty musí čistit uživatel ručně.

---

### 🟡 R9 — Sentry může zachytit PII v exceptions

**Soubor:** `python-backend/app/main.py:398`

```python
sentry_sdk.capture_exception(exc)
```

Exceptions mohou obsahovat email, user_id, organization_id. Bez PII scrubbing konfigurace jde celý exception context do Sentry.

**Riziko:** Nízké (záleží na Sentry konfiguraci a GDPR požadavcích).

---

### 🟡 R10 — Redis interní síť bez TLS

**Soubor:** `docker-compose.yml:50`

`redis://:${REDIS_PASSWORD}@redis:6379/0` — Redis password je nastaven, ale `redis://` ne `rediss://` — žádné TLS šifrování. V docker interní síti je to akceptovatelné, ale při jakémkoli cloud managed Redis (Elasticache, Redis Cloud) je TLS standard.

**Riziko:** Nízké pro single-host deploy, střední pro distributed cloud deploy.

---

## ČÁST 3 — ARCHITEKTONICKÉ POZOROVATELNOSTI

### Nový kód: Export + Storage Consistency

Nové untracked soubory (`export_repository.py`, `storage_consistency_service.py`, `storage_consistency_repository.py`) jsou v git working tree ale nejsou committed. Jsou to dobré přírůstky — export TTL management a storage/DB soulad jsou produkční funkce. Ale:

1. Alembic migrace `20260330_0024_add_project_exports.py` je untracked — musí být commitnuta a aplikována před deploy
2. `storage_consistency_service.py` — potřeba ověřit, zda opravy v consistency check jsou idempotentní (bezpečné opakovat)

---

### WORKER_CONCURRENCY=1 (výchozí)

Worker ve výchozím nastavení zpracovává 1 job najednou. Pro produkci s reálnými AI joby (30–180s) je nutné nastavit `WORKER_CONCURRENCY=4` nebo více v `.env.production`. Není to bug, ale operační riziko pokud operátor nezná tento parametr.

---

## SOUHRN RIZIK

| # | Riziko | Závažnost | Effort |
|---|---|---|---|
| R1 | `_deny_counts` in-process dict | Střední | 2h |
| R2 | account_limiter sliding TTL | Nízká-Střední | 1h |
| R3 | AuditMiddleware extra session | Nízká | 2h |
| R4 | Non-atomic enqueue+DB | Nízká-Střední | 4h+ |
| R5 | Rolling restart race (K8s) | Nízká | 3h |
| R6 | AuditLog bez archivace | Nízká krátkodobě | 4h |
| R7 | Redis queue depth metrika | Nízká | 1h |
| R8 | Multi-file upload partial fail | Nízká-Střední | 2h |
| R9 | Sentry PII scrubbing | Nízká | 1h |
| R10 | Redis bez TLS | Nízká | 1h |

**Žádné kritické blokátory.** Původní kritické problémy (DB pool, single-threaded worker, docker-compose, ILIKE injection, heavy fetch) jsou **všechny opraveny**.

---

## DOPORUČENÍ

### Před prvním produkčním deploy
- Commitnout untracked soubory (export repository, alembic migrace)
- Nastavit `WORKER_CONCURRENCY` v `.env.production` na realistickou hodnotu (doporučeno: 4)
- R1 (`_deny_counts` → Redis) — krátká práce, vysoká hodnota pro multi-instance deploy

### V prvních 2 týdnech
- R2 (fixed window pro account limiter)
- R8 (multi-file upload inventory response)
- R9 (Sentry PII scrubbing konfigurace)

### Ve škálovací fázi
- R4 (outbox/saga pro atomic job creation)
- R6 (AuditLog partitioning by month)
- PostgreSQL trigram indexy pro project search (`pg_trgm` + GIN index)
- Distributed tracing (OpenTelemetry)
