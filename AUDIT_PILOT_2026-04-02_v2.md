# Audit rizik pro pilotní nasazení — Novu Builder v0.7.000

**Datum:** 2. dubna 2026  
**Verze:** v0.7.000  
**Předchozí audit:** AUDIT_PILOT_2026-04-02.md (pre-v0.7.000)  
**Rozsah:** Python backend, Docker infrastruktura, worker queue, multi-tenancy, auth, operační připravenost

---

## Shrnutí

Verze v0.7.000 přinesla podstatné zlepšení: per-session revokace tokenů, worker healthcheck, deterministická seed ID a payload offload. Nicméně nová analýza kódu odhalila **5 nových kritických rizik (P0)** a **4 vysoká rizika (P1)**, která nebyla v předchozím auditu zachycena nebo byla vyvolána kódovými změnami.

**Pilotní nasazení: PODMÍNĚNO** — opravit P0 před go-live.

---

## P0 – KRITICKÁ (blokují go-live)

### P0-1: Chybí Content-Security-Policy header

**Soubor:** [python-backend/app/main.py](python-backend/app/main.py) (řádky 308–318)

Aplikace implementuje `X-Frame-Options`, `X-Content-Type-Options` a `Referrer-Policy`, ale **chybí `Content-Security-Policy`**. Bez CSP lze provést:
- Stored XSS v poli popisu případu → spuštění libovolného JS → krádež tokenů
- Resource injection z externích CDN

**Oprava:**
```python
response.headers["Content-Security-Policy"] = (
    "default-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
    "font-src 'self'; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
```

---

### P0-2: Chybí fallback větev pro neznámý `finalize_action` ve worker runneru

**Soubor:** [python-backend/app/worker/runner.py](python-backend/app/worker/runner.py) (řádky 678–850)

State machine pro `finalize_action` zpracovává jen hodnoty `"ack"`, `"retry"`, `"dlq"`. Pokud se přidá nová hodnota `disposition` do schématu bez synchronní aktualizace runneru, job skončí bez uvolnění leasu → lease visí až do timeoutu (600 s) → worker slot zablokován.

**Scénář:** Nový disposition `"reprocess"` zaveden v schématu → starý runner ho nerozpozná → 10 minut zablokovaný slot na každý takový job.

**Oprava:**
```python
# Za poslední elif větví:
else:
    logger.error(
        "worker.invalid_finalization_disposition",
        finalize_action=finalize_action,
        job_id=lease.job_id,
    )
    finalize_action = "ack"  # Safe default — uvolní slot
```

---

### P0-3: Tenant filter v `get_analysis_job` pouze loguje, nevynucuje

**Soubor:** [python-backend/app/api/routes/analysis_jobs.py](python-backend/app/api/routes/analysis_jobs.py) (řádky 96–114)

Cross-tenant přístup je **logován**, ale pokud `AnalysisService.get_job()` neaplikuje `organization_id` filtr na DB úrovni, data se vrátí před tím, než log zaznamená porušení.

**Scénář:** User z `org_1` zkouší `GET /analysis-jobs/{job_id}` kde job patří `org_2` → data vrácena, log zapsán — ale data jsou již uniknutá.

**Oprava:** Ověřit, že `AnalysisService.get_job()` obsahuje:
```python
select(AnalysisJob).where(
    AnalysisJob.id == job_id,
    AnalysisJob.organization_id == organization_id,
)
```
Pokud chybí → přidat okamžitě.

---

### P0-4: Hardcoded seed hesla v repository

**Soubor:** [python-backend/app/db/bootstrap.py](python-backend/app/db/bootstrap.py) (řádky 231, 259, 273)

```python
hash_password("NovuAdmin2024!")  # superadmin
hash_password("demo1234")        # demo manager
hash_password("tech1234")        # demo technician
```

Hesla jsou viditelná v repo. Pokud někdo omylem nastaví `DB_SEED_ON_STARTUP=true` v produkci, superadmin účet s veřejně známým heslem existuje od první migrace.

**Oprava:**
1. **Ihned:** ověřit `DB_SEED_ON_STARTUP=false` v `.env.production`
2. Dlouhodobě: seed hesla načítat z env proměnné nebo secrets manageru, v produkci přeskočit

---

### P0-5: Metrics endpoint bez autentizace při `METRICS_AUTH_ENABLED=false`

**Soubor:** [python-backend/app/core/config.py](python-backend/app/core/config.py) (řádky 662–689)

Pokud admin explicitně nastaví `METRICS_AUTH_ENABLED=false`, endpoint `/metrics` je dostupný bez tokenu. Startup sice správně odmítne chybějící token při `METRICS_AUTH_ENABLED=true`, ale explicitní vypnutí projde bez varování.

**Scénář:** V Kubernetes prostředí s broad NetworkPolicy → Prometheus scrape `/metrics` bez auth → leakují timing data, job counts, error patterns pro útočníka v monitorovacím namespace.

**Oprava:**
```python
if _is_strict_environment(self.app_env) and not self.metrics_auth_enabled:
    raise ValueError(
        "METRICS_AUTH_ENABLED musí být true v produkci. "
        "Nastav METRICS_AUTH_TOKEN a nakonfiguruj Prometheus bearer_token."
    )
```

---

## P1 – VYSOKÁ (blokují škálování na 100+ tenantů)

### P1-1: Retry promotion může uvíznout ve smyčce při plné frontě

**Soubor:** [python-backend/app/worker/queue.py](python-backend/app/worker/queue.py) (řádky 256–273)

Lua skript `_PROMOTE_RETRY_SCRIPT` správně respektuje kapacitní limit, ale joby s prošlým `due_time` (< now) zůstávají v retry ZSET. Při příštím spuštění promoteru se pokusí znovu — pokud fronta stále plná, opakuje se donekonečna.

**Scénář:** 90 jobů čeká na retry, fronta plná → promoter je přeskakuje každých 30 s → bloqueji nové retrye.

**Oprava:** Při zamítnutí kvůli kapacitě přeplánovat s exponenciálním backoffem:
```python
next_due = now + timedelta(seconds=min(3600, backoff_base * 2 ** attempt_count))
await redis.zadd(RETRY_QUEUE_KEY, {raw: next_due.timestamp()})
```

---

### P1-2: Tiché selhání obnovy leasu — job pokračuje bez platného leasu

**Soubor:** [python-backend/app/worker/runner.py](python-backend/app/worker/runner.py) (řádky 590–636)

Při selhání obnovy leasu vrátí `_renew_job_lease_loop()` bez výjimky. Job executor pokračuje v práci — ale lease mohl být mezitím ukradnut reaperem, nebo ho přebral jiný worker.

**Scénář:**
1. Worker A zpracovává job (AI volání 60 s)
2. V 35. sekundě obnova leasu selže (Redis restart)
3. Reaper v 40. sekundě označí job jako FAILED
4. Worker A v 60. sekundě dokončí → ACK selže → job je zároveň FAILED i zpracovaný

**Oprava:** Selhání obnovy leasu musí propagovat výjimku, která zruší `execute_lease()` task.

---

### P1-3: Retry analýzy obchází tenant limit aktivních jobů

**Soubor:** [python-backend/app/api/routes/analysis_jobs.py](python-backend/app/api/routes/analysis_jobs.py) (řádky 172–185)

Endpoint `POST /analysis-jobs/{job_id}/retry` nekontroluje, zda tenant dosáhl limitu (`analysis_jobs_per_tenant_limit`). Nový job se vytvoří i při plné kapacitě tenanta.

**Oprava:**
```python
active_count = await analysis_service.count_active_jobs(org_id)
if active_count >= settings.analysis_jobs_per_tenant_limit:
    raise HTTPException(status_code=429, detail="Tenant job limit reached.")
```

---

### P1-4: Docker healthcheck `start_period` pro worker je kratší než grace period

**Soubor:** [docker-compose.yml](docker-compose.yml) (řádky 237–242)

Worker healthcheck: `start_period: 45s`  
Worker `readiness_processing_grace_seconds`: 75 s (config výchozí)

Worker může být správně inicializován až za 60–75 s, ale healthcheck ho označí jako unhealthy po 45 s → Docker restartuje → restart loop.

**Oprava:**
```yaml
healthcheck:
  start_period: 90s   # > readiness_processing_grace_seconds
  interval: 10s
  retries: 6
```

---

## P2 – STŘEDNÍ (opravit v prvním sprintu po pilotu)

| ID | Problém | Soubor | Popis |
|----|---------|--------|-------|
| P2-1 | Reset token nezneplatněn při změně hesla | [auth_service.py](python-backend/app/services/auth_service.py):498–525 | `change_password()` nevolá `invalidate_active_password_reset_tokens()` → starý reset token lze zneužít po změně hesla |
| P2-2 | Chybí indexy na `audit_logs` | migrace 0012 | Queries filtrující `user_id + created_at` nebo `org_id + action` bez indexu → full table scan |
| P2-3 | CORS povoluje `methods=["*"]`, `headers=["*"]` | [main.py](python-backend/app/main.py):300–306 | Zpřísnit na explicitní seznam metod a hlaviček |
| P2-4 | Rate limity sdíleny per-IP (ne per-user) | [config.py](python-backend/app/core/config.py):446–451 | Za NAT/proxy sdílí limit všichni uživatelé z jedné sítě; útočník může DoSnout kolegy |

---

## Co bylo opraveno od v0.6.003 ✅

| Oprava | Kde |
|--------|-----|
| Per-session token revokace | migrace 0037, `user_sessions` tabulka |
| Deterministická invalidace tokenů `token_version` | migrace 0040, `users.token_version` |
| Worker healthcheck entrypoint | `app/worker/healthcheck.py`, docker-compose.yml |
| Analysis job payload offload z hlavní tabulky | migrace 0038 |
| JSONB audit logs pro strukturované dotazy | migrace 0039 |
| Deterministická seed UUID | `app/work_catalog/seed_ids.py` |
| Auth error isolation `_raise_auth_protection_unavailable()` | `auth.py`:68–117 |
| Lease ownership verifikace před ACK | migrace 0026, `_ACK_JOB_SCRIPT` |

---

## Matice rizik

| Oblast | P0 Kritická | P1 Vysoká | P2 Střední |
|--------|------------|-----------|------------|
| Bezpečnost | 3 | 1 | 3 |
| Operační | 1 | 2 | 1 |
| Datová integrita | 1 | 1 | 0 |
| **Celkem** | **5** | **4** | **4** |

---

## Deployment checklist

**Před pilotem (P0):**
- [ ] Přidat CSP header do `main.py` — [main.py:318](python-backend/app/main.py#L318)
- [ ] Přidat else/fallback větev pro `finalize_action` — [runner.py:822](python-backend/app/worker/runner.py#L822)
- [ ] Ověřit tenant filter v `AnalysisService.get_job()` na DB úrovni
- [ ] Ověřit `DB_SEED_ON_STARTUP=false` v `.env.production`
- [ ] Přidat produkční guard pro `METRICS_AUTH_ENABLED=false`

**Před škálováním (P1):**
- [ ] Exponenciální backoff pro retry joby při plné frontě
- [ ] Propagovat selhání obnovy leasu jako výjimku do executor tasku
- [ ] Přidat tenant limit check do retry endpointu
- [ ] Opravit `start_period` worker healthcheku na 90 s

**Sprint po pilotu (P2):**
- [ ] Invalidovat reset tokeny při `change_password()`
- [ ] Přidat indexy na `audit_logs` (user_id, org_id, created_at)
- [ ] Zpřísnit CORS methods/headers
- [ ] Přejít na per-user rate limiting klíče

---

## Verdikt

**Podmíněné schválení pilotu — fix 5× P0 před go-live**

Odhadovaná pracnost P0: ~6 hodin  
Odhadovaný go-live po opravě P0: **4. dubna 2026**

---

*Audit připraven: 2. dubna 2026 | Claude Code (claude-sonnet-4-6) | verze kódu v0.7.000*
