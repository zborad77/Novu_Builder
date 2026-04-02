# Audit rizik pro pilotní nasazení — Novu Builder

**Datum:** 2. dubna 2026  
**Verze:** v0.6.003  
**Rozsah:** Python backend, Docker infrastruktura, worker queue, multi-tenancy, operační připravenost

---

## Shrnutí

Architektura je kvalitní a má silné základy, ale obsahuje **3 kritická rizika (P0)** a **7 vysokých rizik (P1)**, která musí být ošetřena před nebo krátce po spuštění pilotu.

**Pilotní nasazení: PODMÍNĚNO** — opravit P0 před go-live, P1 před škálováním na 100+ tenantů.

---

## P0 – KRITICKÁ (opravit před spuštěním)

### P0-1: Retry queue obchází limit hloubky fronty

**Soubor:** `python-backend/app/worker/queue.py` (přibližně řádky 205–215)

Lua skript `_PROMOTE_RETRY_SCRIPT` provádí přímý `RPUSH` bez kontroly limitu `max_depth`. Při hromadném selhání jobů (např. 500 najednou) scheduler povýší všechny retrye najednou, přeteče fronta a způsobí:

- Memory spike v Redisu (riziko OOM)
- Workers přijmou víc jobů než je `ANALYSIS_QUEUE_MAX_DEPTH`

**Oprava:** Použít stejnou logiku jako `_ENQUEUE_WITH_LIMIT_SCRIPT` — odmítnout přetečení.

---

### P0-2: Redis fail-open u per-account brute-force ochrany

**Soubor:** `python-backend/app/core/account_limiter.py` (řádky 106–128)

Při výpadku Redisu se přepne na in-memory fallback (`_FALLBACK_FAILURES` dict). V multi-instance nasazení (více API podů) má každý pod vlastní čítač:

- Útočník distribuuje pokusy přes 3 pody → 3× více pokusů bez aktivace throttle
- Výpadek Redisu (i 30 sekund) otevírá okno pro útok

**Oprava:** Buď fail-closed (vrátit 503 při nedostupnosti Redisu v produkci), nebo durable fallback (lokální SQLite).

---

### P0-3: Worker healthcheck chybí v Docker Compose

**Soubor:** `docker-compose.yml` (sekce `worker`)

Worker nemá `healthcheck` direktivu. Docker orchestrátor nedokáže automaticky restartovat zaseknutý worker proces.

**Oprava:**

```yaml
healthcheck:
  test: ["CMD", "python", "-m", "app.worker.healthcheck"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

---

## P1 – VYSOKÁ (opravit před škálováním na 100+ tenantů)

### P1-1: Worker finalize action při neočekávané výjimce

**Soubor:** `python-backend/app/worker/runner.py` (řádky 609–674)

Výjimka mimo `WorkerJobExecutionError` (např. síťový výpadek S3 při ukládání výsledku) ponechá `finalize_action = "none"` → lease visí v `analysis:processing` až 10 minut. Uživatel vidí job jako zaseknutý.

**Oprava:** Mapovat všechny výjimky na explicitní akci (`retry` pro síťové chyby, `dlq` pro zbytek).

---

### P1-2: DLQ history — ověřit aplikaci migrací

**Soubor:** `python-backend/app/worker/queue.py` + migrace 0027, 0038–0040

History tracking byl přidán (LPUSH do klíče `:history`), ale fallback stále používá původní SET klíč. Je nutné ověřit, že všechny migrace jsou aplikovány přes `alembic current`.

---

### P1-3: Timing oracle při enumeraci obrázků (cross-tenant)

**Soubor:** `python-backend/app/api/routes/images.py` (řádky 145–180)

První dotaz načítá obrázek bez tenant filtru, druhý filtruje. Útočník může měřit časy odpovědí a enumerovat image ID přes hranice tenantů.

**Oprava:** Spojit oba dotazy do jednoho s JOIN na Project a WHERE na `organization_id`.

---

### P1-4: Revoked tokens bez Redis cache

**Soubor:** `python-backend/app/repositories/token_repository.py` (řádky 60–70)

Každý autentizovaný request = DB dotaz na `revoked_tokens`. Při 1 000 req/s → 1 000 DB dotazů/s jen pro JTI validaci.

**Oprava:** Cache revokovaných JTI v Redisu s TTL = expirace tokenu.

---

### P1-5: Sentry traces zakázáno (0 % sampling)

**Soubor:** `python-backend/app/main.py` (řádky 259–265)

`sentry_traces_sample_rate=0.0` → žádná performance viditelnost. Pomalé DB dotazy, AI latence, storage operace jsou neviditelné.

**Oprava:** Nastavit 5 % pro pilot: `SENTRY_TRACES_SAMPLE_RATE=0.05`.

---

### P1-6: Worker metriky zakázány

**Soubor:** `docker-compose.yml` sekce `worker`, env `WORKER_METRICS_ENABLED`

Výchozí hodnota `false` → Prometheus nevidí worker. Monitorovací slepá skvrna při výpadku nebo zpomalení.

**Oprava:** `WORKER_METRICS_ENABLED=true`, `WORKER_METRICS_PORT=9101` v `.env.production`.

---

### P1-7: Unbounded startup scan lokálního storage

**Soubor:** `python-backend/app/storage/local_photo_storage.py` (řádky 62–63)

`rglob("*")` při 100 K+ souborech trvá 30+ sekund a blokuje startup. Dopad jen pro dev/local storage — S3 backend tento sken neprovádí.

**Oprava:** Použít S3 backend v produkci (doporučeno). Pro dev limitem počtu souborů.

---

## P2 – STŘEDNÍ (opravit v prvním sprintu po pilotu)

| ID   | Problém                                        | Soubor                            |
| ---- | ---------------------------------------------- | --------------------------------- |
| P2-1 | CORS povoluje `methods=["*"]`, `headers=["*"]` | `app/main.py:300–306`             |
| P2-2 | Chybí Content-Security-Policy header           | `app/main.py:308–318`             |
| P2-3 | Seed hesla jsou hardcoded v bootstrap          | `app/db/bootstrap.py:231,260,275` |
| P2-4 | JWT refresh token lifetime 7 dní               | `.env.production.example:68`      |
| P2-5 | Chybí index na `revoked_tokens.expires_at`     | ověřit v migraci 0023             |

---

## Co je v pořádku ✅

- Silná validace konfigurace v produkčním módu (JWT_SECRET, REDIS heslo, METRICS token)
- Tenant izolace konzistentně aplikována na všech user-facing routách
- 40 Alembic migrací se schema version guardem při startu
- Dual DB engine pool (API vs Worker) — bez connection starvation
- Worker session lifecycle oddělen od AI volání (žádné spojení drženo 180s)
- User sessions tabulka (0037) — force-logout z konkrétních zařízení
- S3_CDN_BASE_URL správně odmítnut config validací
- `DB_SEED_ON_STARTUP: "false"` v docker-compose.yml

---

## Deployment checklist

**Před pilotem:**

- [ ] Ověřit `DB_SEED_ON_STARTUP=false` v `.env.production`
- [ ] Vygenerovat JWT_SECRET, METRICS_AUTH_TOKEN (32+ náhodných hex bytů)
- [ ] Nastavit POSTGRES_PASSWORD, REDIS_PASSWORD (32+ náhodných hex bytů)
- [ ] Aplikovat všech 40 Alembic migrací — ověřit `alembic current`
- [ ] **Opravit P0-1** — retry queue respektuje max_depth
- [ ] **Opravit P0-2** — Redis fail-closed nebo durable fallback
- [ ] **Přidat P0-3** — worker healthcheck do docker-compose.yml

**Před 100+ tenanty:**

- [ ] P1-1: mapování výjimek ve worker finalize
- [ ] P1-3: timing oracle v image enumeration
- [ ] P1-4: Redis cache pro revoked tokens
- [ ] P1-5: Sentry traces zapnout (5 %)
- [ ] P1-6: Worker metriky zapnout

---

## Matice rizik

| Oblast               | P0 Kritická | P1 Vysoká | P2 Střední |
| -------------------- | ----------- | --------- | ---------- |
| Bezpečnost           | 1           | 2         | 4          |
| Operační             | 1           | 3         | 1          |
| Datová integrita     | 0           | 1         | 0          |
| Výkon/škálovatelnost | 1           | 1         | 0          |
| **Celkem**           | **3**       | **7**     | **5**      |

---

## Verdikt

**Podmíněné schválení pilotu**

- **NELZE nasadit** bez opravy P0-1, P0-2, P0-3
- **MOŽNÉ nasadit** do staging/pilotu po opravě P0
- **NUTNÉ** P1 mitigace před škálováním na 100+ tenantů
- Odhadovaná pracnost P0: ~8 hodin → možné go-live **4. dubna 2026**

---

_Audit připraven: 2. dubna 2026 | Claude Code (claude-sonnet-4-6)_  
_Analyzováno: ~109 Python souborů, 40 migrací, docker-compose.yml_
