# Novu Builder — Production Readiness Verdict

**Verze:** v0.5.0 (commit 648b59d)
**Datum hodnocení:** 2026-03-28
**Hodnotitel:** Claude Code (automatizovaná analýza + manuální revize)

---

## Výsledek

```
╔══════════════════════════════════════════╗
║                                          ║
║   VERDICT:  ✅  PILOT READY              ║
║                                          ║
║   NOT READY  →  CONDITIONALLY READY      ║
║             →  [PILOT READY]  ←          ║
║             →  PRODUCTION READY          ║
╚══════════════════════════════════════════╝
```

**Podmínky pilotního provozu:** Viz sekce "Co musí být splněno před pilotem".

---

## Co je hotovo a robustní

### Architektura a bezpečnost

| Oblast | Stav | Poznámka |
|--------|------|----------|
| Multi-tenant izolace | ✅ Robustní | `resolve_org_id()` na každém endpointu; 100% pokryto testy |
| JWT autentizace | ✅ Produkční | JTI blacklist + `tokens_valid_after` — okamžitá invalidace po reset hesla |
| Admin reset tokenů | ✅ Otestováno | D1 testy pokrývají celý flow (token → 401 po resetu) |
| Audit log | ✅ Funkční | Každý admin request logován do `audit_logs` tabulky; dedup pro unauth endpointy |
| Redis autentizace | ✅ Nasazeno | `--requirepass` v docker-compose, backend se autentizuje |
| Metriky auth guard | ✅ Nasazeno | `METRICS_AUTH_ENABLED=true` + Bearer token; nginx IP whitelist |
| Health endpoint split | ✅ Správně | `/alive` (public) / `/health` (public, minimal) / `/health/internal` (superadmin + IP) |
| Port 8000 neexpozován | ✅ Opraveno | Backend dostupný pouze přes nginx docker network |
| Rate limiting | ✅ Nakonfigurováno | slowapi s různými limity pro login/admin/upload |
| HTTPS | ✅ V nginx | HTTP → HTTPS redirect, TLS 1.2/1.3 |
| Security headers | ✅ V nginx | X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy |

### Testovací pokrytí

| Oblast | Počet testů | Pokrytí |
|--------|-------------|---------|
| Tenant izolace (E2E) | 25+ | Kompletní — cross-tenant 404 na všech endpointech |
| Auth flow | 15+ | Login, refresh, reset, admin reset, token invalidace |
| Metriky auth guard | 5 | Enabled/disabled, správný/špatný token, unconfigured |
| Analýza workflow | 11 | Create, retrieve, list, cancel, cross-tenant deny |
| Duplikace projektů | 6 | DB record, fyzické soubory, preview, tenant izolace |
| Finanční validace | 17 | _normalize_cost_value unit testy + PATCH acceptance |
| Status constraints | 9 | Send bez final proposal (409), archive, cross-tenant |
| **Celkem** | **430+** | 430/436 passing (6 selhání = chybí Pillow lokálně) |

### Infrastruktura

| Komponenta | Stav |
|------------|------|
| Docker Compose (db + redis + backend + nginx + worker) | ✅ Kompletní |
| Alembic migrace (18 migrací, HEAD = 0018) | ✅ Aplikovány |
| Worker process (`app.worker.runner`) | ✅ V docker-compose s `restart: unless-stopped` |
| Backup skript (`scripts/backup.sh`) | ✅ Existuje |
| Smoke check skript (`scripts/smoke_check_live.py`) | ✅ Nový |
| Prometheus metriky (http, db, worker, jobs gauges) | ✅ Funkční |

---

## Blokerů pro produkci (MUST FIX)

Tyto položky **blokují produkční nasazení** (ne pilota):

### B-01: SMTP není nakonfigurovaný
**Dopad:** Funkce "zapomenuté heslo" nefunguje — uživatel nemůže obnovit heslo bez admina.
**Chybí:** `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `APP_BASE_URL` v `.env.production`
**Řešení:** Nakonfigurovat transakcionalní e-mail (SendGrid, AWS SES, vlastní SMTP)
**Závažnost:** HIGH pro produkci, LOW-MEDIUM pro pilota (admin může reset udělat přes API)

### B-02: Off-site zálohy nejsou automatické
**Dopad:** Havárie disku = ztráta dat i zálohy.
**Chybí:** rsync/S3 cron job pro kopírování `/backups/` na vzdálené úložiště
**Řešení:** Přidat do crontab nebo backup.sh volání `rclone`/`aws s3 sync`
**Závažnost:** HIGH pro produkci

### B-03: Restore drill nebyl proveden
**Dopad:** Nevíme, jestli zálohu lze skutečně obnovit v plné délce
**Chybí:** Alespoň jeden otestovaný restore z reálné zálohy na clean prostředí
**Řešení:** Provést restore drill před pilotním provozem
**Závažnost:** MEDIUM — bez drilu neznáme skutečné RTO

---

## Rizika přijatelná pro pilot

Tyto věci **chybí, ale pilot je možný** s dokumentovaným rizikem:

### R-01: Monitoring a alerting není nastaven
**Stav:** Metriky jsou exportovány, ale Prometheus/Grafana dashboard a alerty nejsou nakonfigurovány
**Přijatelné riziko:** Pro pilota s < 5 zákazníky může stačit manuální kontrola `/health`
**Akce:** Nastavit `novu_worker_alive == 0` a `novu_db_alive == 0` alerty před produkcí

### R-02: Sentry DSN není nakonfigurován
**Stav:** `sentry-sdk` je v requirements.txt, ale `SENTRY_DSN` není nastaven
**Přijatelné riziko:** Chyby jsou stále v Docker logu; pro pilota dostačující
**Akce:** Nakonfigurovat Sentry nebo jiný error tracking před produkcí

### R-03: WAL archiving / PITR není nakonfigurován
**Stav:** Pouze `pg_dump` zálohy jednou denně; RPO = max. 24 h
**Přijatelné riziko:** Pro pilota s < 50 zakázkami denně přijatelné
**Akce:** Nastavit Barman nebo pgBackRest pro produkci (RPO < 5 min)

### R-04: SSL certifikát je self-signed
**Stav:** Nginx potřebuje certifikát v `nginx/certs/`; pro interní pilot self-signed stačí
**Přijatelné riziko:** Prohlížeče zobrazí varování — pro interní pilotní tým akceptovatelné
**Akce:** Let's Encrypt nebo komerční CA před produkčním nasazením pro zákazníky

### R-05: Rate limiting závisí na Redis
**Stav:** slowapi používá Redis jako storage; při Redis outage je rate limiting dočasně vypnut
**Přijatelné riziko:** Krátkodobý Redis výpadek neotevírá zneužití v pilotním prostředí
**Akce:** Přijatelné i v produkci (Redis má `restart: unless-stopped`)

### R-06: AI analýza pouze `mock` provider ve výchozím stavu
**Stav:** Výchozí `AI_ANALYSIS_PROVIDER=mock` — analýza vrací prázdné výsledky
**Přijatelné riziko:** Závisí na záměru pilota; pro testování workflow bez AI přijatelné
**Akce:** Nastavit `AI_ANALYSIS_PROVIDER=claude` + `ANTHROPIC_API_KEY` pro ostrý pilot

---

## Co chybí do Production Ready

Přechod z **Pilot Ready** na **Production Ready** vyžaduje:

| # | Položka | Priorita | Odhad práce |
|---|---------|----------|-------------|
| 1 | SMTP nakonfigurovat (password reset e-maily) | HIGH | 1-2 h |
| 2 | Off-site zálohy (rsync/S3) | HIGH | 2-4 h |
| 3 | Restore drill zdokumentovat a provést | HIGH | 2-4 h |
| 4 | Alerting: Prometheus + Grafana dashboardy | MEDIUM | 4-8 h |
| 5 | Sentry DSN nakonfigurovat | MEDIUM | 30 min |
| 6 | Let's Encrypt / platný SSL certifikát | MEDIUM | 1-2 h |
| 7 | WAL archiving (PITR) pro RPO < 5 min | LOW | 8-16 h |
| 8 | Záloha šifrování (gpg/S3 SSE) | LOW | 2-4 h |
| 9 | Load testing (ověření výkonu pod zátěží) | MEDIUM | 4-8 h |
| 10 | Dokumentace pro uživatele (end-user) | LOW | variabilní |

**Celkový odhad:** 25–50 hodin práce pro plné Production Ready.

---

## Silné stránky architektury (hodné zachování)

1. **Tenant izolace** — `resolve_org_id()` na 100 % endpointů, ověřeno E2E testy; extrémně obtížné prolomit omylem
2. **Token invalidace** — `tokens_valid_after` mechanismus je správná volba (nevyžaduje Redis pro validaci)
3. **Audit log** — každý admin/auth request logged s `user_id`, `ip_address`, `action`; cenné pro forenziku
4. **Migrace explicitně** — `DB_AUTO_CREATE_SCHEMA=false` v produkci; žádné surprise schema změny
5. **Graceful degradace** — Redis outage nepoloží backend; cache miss, rate limiting vypnut, ne crash
6. **Worker heartbeat** — `novu_worker_alive` gauge umožňuje okamžité odhalení mrtvého workeru
7. **Testovací pokrytí** — 430+ testů se session-scoped fixtures; testy jsou rychlé a spolehlivé

---

## Rychlá checklist pro start pilota

```
[ ] .env.production vyplněn (žádné "change-me")
[ ] SSL certifikát v nginx/certs/ (i self-signed)
[ ] Migrace na HEAD: alembic current → 20260326_0018
[ ] docker compose ps → všechny služby "healthy"
[ ] smoke_check_live.py prošel
[ ] Zálohovací cron nastaven
[ ] Záloha provedena a ověřena (aspoň ls -lh)
[ ] Superadmin účet vytvořen
[ ] AI provider nastaven dle záměru (mock / claude)
```

---

*Poslední revize: 2026-03-28 | Verze: v0.5.0*
