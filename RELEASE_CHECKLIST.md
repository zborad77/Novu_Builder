# Novu Builder — Release Readiness Checklist

**Verze:** v0.5.x
**Použití:** Před každým nasazením do pilot/produkce projdi každou položku. Zaznamenej datum a initials odpovědné osoby.

---

## 0. Před nasazením (pre-flight)

| # | Položka | Jak ověřit | OK |
|---|---------|------------|----|
| 0.1 | `.env.production` existuje a není `change-me` ani prázdné hodnoty | `grep -E "change-me|^[A-Z_]+=($)" .env.production` nesmí nic vrátit | ☐ |
| 0.2 | `POSTGRES_PASSWORD` — náhodný, min. 32 hex znaků | `openssl rand -hex 32` | ☐ |
| 0.3 | `REDIS_PASSWORD` — náhodný, min. 32 hex znaků | `openssl rand -hex 32` | ☐ |
| 0.4 | `JWT_SECRET` — náhodný, min. 32 hex znaků | `openssl rand -hex 32` | ☐ |
| 0.5 | `METRICS_AUTH_TOKEN` — náhodný token (bude použit v Prometheus scrape config) | `openssl rand -hex 32` | ☐ |
| 0.6 | `METRICS_AUTH_ENABLED=true` nastaven | Zkontroluj `.env.production` | ☐ |
| 0.7 | `CORS_ALLOWED_ORIGINS` — obsahuje pouze povolené origin(y) frontendu | Žádný wildcard `*` v produkci | ☐ |
| 0.8 | SSL certifikáty v `nginx/certs/cert.pem` a `nginx/certs/key.pem` | `openssl x509 -in nginx/certs/cert.pem -noout -dates` | ☐ |
| 0.9 | `AI_ANALYSIS_PROVIDER` nastaven (`mock` / `claude` / `openai`) | Závisí na záměru nasazení | ☐ |
| 0.10 | Pokud `AI_ANALYSIS_PROVIDER=claude`: `ANTHROPIC_API_KEY` vyplněn | — | ☐ |

---

## 1. Database & migrace

| # | Položka | Jak ověřit | OK |
|---|---------|------------|----|
| 1.1 | PostgreSQL volume má dostatek místa | `df -h /var/lib/docker/volumes` | ☐ |
| 1.2 | DB je dostupná před spuštěním backendů | `docker compose up -d db && docker compose exec db pg_isready -U novu -d novu_builder` | ☐ |
| 1.3 | Migrace aplikovány na HEAD (`20260326_0018`) | `docker compose run --rm backend alembic current` → musí vrátit `20260326_0018 (head)` | ☐ |
| 1.4 | Žádné čekající migrace | `docker compose run --rm backend alembic check` — musí vrátit `No new upgrade operations detected.` | ☐ |
| 1.5 | Záloha DB před migrací provedena | Viz BACKUP_RESTORE.md | ☐ |

---

## 2. Start backendu a workeru

| # | Položka | Jak ověřit | OK |
|---|---------|------------|----|
| 2.1 | Backend kontejner startuje bez chyby | `docker compose logs backend` — žádný ERROR/CRITICAL při startu | ☐ |
| 2.2 | `GET /api/v1/alive` vrací 200 | `curl -f http://localhost:8000/api/v1/alive` | ☐ |
| 2.3 | `GET /api/v1/health` vrací `{"status":"ok"}` | `curl http://localhost:8000/api/v1/health` | ☐ |
| 2.4 | Worker kontejner běží | `docker compose ps worker` — status `running` | ☐ |
| 2.5 | Worker heartbeat se zapisuje do Redis | Po 60 s: `docker compose exec redis redis-cli -a "$REDIS_PASSWORD" GET worker:heartbeat` — nesmí být prázdné | ☐ |
| 2.6 | `/api/v1/health/internal` hlásí `worker.alive=true` | Vyžaduje superadmin token, volat pouze z internetu | ☐ |

---

## 3. Redis autentizace

| # | Položka | Jak ověřit | OK |
|---|---------|------------|----|
| 3.1 | Redis vyžaduje heslo | `docker compose exec redis redis-cli ping` → musí vrátit `NOAUTH` | ☐ |
| 3.2 | Backend se autentizuje | `docker compose logs backend` — žádná chyba `NOAUTH` | ☐ |
| 3.3 | Cache funguje | Zavolej `GET /api/v1/pricebooks` dvakrát; druhý request musí být rychlejší | ☐ |

---

## 4. Storage (souborové úložiště)

| # | Položka | Jak ověřit | OK |
|---|---------|------------|----|
| 4.1 | `storage_data` volume je namontován | `docker compose exec backend ls /data/storage` — adresář existuje | ☐ |
| 4.2 | Backend má práva zápisu do storage | Nahraj testovací fotku přes API, zkontroluj, že soubor vznikl | ☐ |
| 4.3 | Dostatek místa pro storage | `docker compose exec backend df -h /data/storage` | ☐ |

---

## 5. Bezpečnost a přístupová politika

| # | Položka | Jak ověřit | OK |
|---|---------|------------|----|
| 5.1 | `/api/v1/metrics` bez tokenu vrátí 401 z backendu | `curl -o /dev/null -w "%{http_code}" https://<host>/api/v1/metrics` — nginx blokuje, nebo backend vrátí 401 | ☐ |
| 5.2 | `/api/v1/metrics` s platným tokenem vrátí 200 | `curl -H "Authorization: Bearer $METRICS_AUTH_TOKEN" https://<host>/api/v1/metrics` | ☐ |
| 5.3 | `/api/v1/health/internal` z veřejného internetu vrátí 403 | `curl https://<host>/api/v1/health/internal` — nginx musí vrátit 403 | ☐ |
| 5.4 | Port 8000 backendového kontejneru není publicky expozován | `docker compose port backend 8000` — nesmí vrátit výsledek (nebo vrátí 127.0.0.1) | ☐ |
| 5.5 | HTTPS funguje, HTTP přesměrovává na HTTPS | `curl -I http://<host>/api/v1/alive` — status 301 | ☐ |
| 5.6 | SSL certifikát je platný a neexpiroval | `openssl s_client -connect <host>:443 </dev/null 2>/dev/null | openssl x509 -noout -dates` | ☐ |
| 5.7 | CORS hlavičky nepovolují wildcard | V response na preflight request z nepovolené domény — žádné ACAO:* | ☐ |

---

## 6. Zálohovací strategie

| # | Položka | Jak ověřit | OK |
|---|---------|------------|----|
| 6.1 | Zálohovací skript `scripts/backup.sh` je funkční | `BACKUP_DIR=/tmp/test-backup ./scripts/backup.sh` — vzniknou soubory `.pgdump`, `.pgdump.sha256` a `.tar.gz` | ☐ |
| 6.2 | Cron job pro denní zálohu je nastaven | `crontab -l | grep backup.sh` | ☐ |
| 6.3 | Zálohy se kopírují na vzdálené úložiště (off-site) | Rsync/S3/jiný mechanismus aktivní | ☐ |
| 6.4 | Postup restore byl ověřen na jiném prostředí (restore drill) | Viz BACKUP_RESTORE.md | ☐ |

---

## 7. Monitoring a alerting

| # | Položka | Jak ověřit | OK |
|---|---------|------------|----|
| 7.1 | Prometheus scrape funguje | `curl -H "Authorization: Bearer $METRICS_AUTH_TOKEN" http://<host>/api/v1/metrics | grep novu_db_alive` | ☐ |
| 7.2 | Grafana (nebo jiný) dashboard je nastaven | — | ☐ |
| 7.3 | Alert na `novu_worker_alive == 0` je nakonfigurován | — | ☐ |
| 7.4 | Alert na `novu_db_alive == 0` je nakonfigurován | — | ☐ |
| 7.5 | Alerting kanál (email/Slack/PagerDuty) je otestován | Pošli testovací alert | ☐ |
| 7.6 | `SENTRY_DSN` nastaven (pokud se Sentry používá) | `grep SENTRY_DSN .env.production` | ☐ |

---

## 8. Smoke testy

| # | Položka | Jak ověřit | OK |
|---|---------|------------|----|
| 8.1 | Smoke check skript prošel | `python scripts/smoke_check_live.py https://<host> <email> <password>` — exit 0 | ☐ |
| 8.2 | Login s testovacím účtem funguje | Zkusit přes UI nebo API | ☐ |
| 8.3 | Vytvoření zakázky funguje | `POST /api/v1/cases` vrací 201 | ☐ |
| 8.4 | Nahrání fotky funguje | `POST /api/v1/cases/{id}/photos` vrací 201 | ☐ |
| 8.5 | Spuštění analýzy funguje | `POST /api/v1/cases/{id}/analysis-jobs` vrací 202 | ☐ |

---

## 9. Rollback plán

| # | Položka | Jak ověřit | OK |
|---|---------|------------|----|
| 9.1 | Předchozí Docker image je dostupný pro rollback | `docker images | grep novu` | ☐ |
| 9.2 | Záloha DB z těsně před deployem existuje | Soubor v backup adresáři | ☐ |
| 9.3 | Postup rollback migrací je zdokumentován | Viz DEPLOY.md — sekce Rollback | ☐ |
| 9.4 | Čas potřebný na rollback je odhadnut a přijatelný | Odhadovaně: ~5-10 minut (bez migrace zpět) | ☐ |

---

## Go / No-Go

**Blocker (MUST):** položky 0.1–0.8, 1.3, 2.1–2.5, 5.4, 5.5
**Pilot (SHOULD):** položky 6.1–6.2, 7.1, 8.1
**Produkce (ALL):** všechny výše + 6.3–6.4, 7.2–7.6

| Stav | Podmínka |
|------|----------|
| **GO** | Všechny MUST položky ✅, žádná otevřená CRITICAL chyba |
| **CONDITIONAL GO** | MUST splněny, ≥1 SHOULD chybí s dokumentovaným rizikem |
| **NO-GO** | Jakýkoliv MUST nesplněn |

---

*Poslední revize: 2026-03-28 | Platí pro v0.5.x*
