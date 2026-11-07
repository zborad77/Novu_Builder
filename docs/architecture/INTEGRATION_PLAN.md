# Bezpečný postup integrace F0–F6 a modulárního refaktoru (rozhodnutí O7)

> Aktuální stav PR, CI, blokerů, stagingu a rollbacku: [INTEGRATION_REPORT.md](INTEGRATION_REPORT.md) (2026-10-20).

Stav k 2026-10-19. **Nic z tohoto dokumentu se neprovádí bez výslovného schválení**
(žádný push, PR, merge ani deployment).

## 1. Ověřený stav větví

| Ref | Commit | Poznámka |
|---|---|---|
| `origin/master` | `84d9b73` | poslední stav na GitHubu |
| lokální `master` | `904ac05` | **+2 nepushnuté commity**: `5b7a278 docs-cleanup` (2026-06-30) a merge `904ac05` |
| `fix/f0-rbac-tenant-isolation` | `3f581d7` | +10 commitů nad lokálním `master` (F0, SA-05/06, F0.3, F3, F3.4/3.6, D-10, F6, F6.2); **nikdy nepushnuto → CI na nich nikdy neběželo** |
| `refactor/modular-architecture` | od `3f581d7` | Fáze B; jen lokální commity |

Push `fix/f0-…` by na GitHub přenesl i `5b7a278` a `904ac05` (jsou jeho předky).

## 2. Důsledky `docs-cleanup` (`5b7a278`)

Ověřeno porovnáním stromů:

| Změna v `5b7a278` | Stav na `3f581d7` |
|---|---|
| Smazáno 51 dokumentů (README, ARCHITECTURE, RUNBOOK, BACKUP_RESTORE, audity …) | **všechny obnoveny** v `dcf210f`; žádný soubor smazaný tímto commitem nechybí |
| Login throttle bez Redisu „fail-open" při `APP_ENV=development` (`routes/auth.py`) | **nahrazeno** v F0 (`36b6d41`) explicitním `AUTH_THROTTLE_DEV_FAIL_OPEN`; bez něj fail-closed |
| `echo=False` natvrdo v `db/session.py` (dřív `echo=settings.app_debug`) | trvá – `APP_DEBUG` už nezapíná SQL echo. Vědomé? (otázka I1) |
| Potlačení „hlučných" loggerů (`sqlalchemy.*`, `uvicorn.access`, `httpx`) na WARNING | trvá – přístupové logy uvicornu se nezapisují (aplikace má vlastní `http.request` log) |
| Nový `web/vite.config.ts` (aliasy) | trvá – bez něj by `vite build` neresolvoval aliasy |
| Přepsaná `web/src/pages/LoginPage.tsx` | trvá – volá `apiClient` přímo ze stránky (porušení konvence vrstev, viz B6) |
| Desktop: verzování (`version.json`, `cmake/*`), úpravy UI | trvá |
| Pomocné `backend.bat`, `frontend_web.bat`, `redis.bat`, `.gitmessage`, `design/NovuBuilder.png` | trvá; `*.bat` se v B1 aktualizují na nové cesty |

## 3. Ekvivalent CI spuštěný lokálně na `3f581d7`

GitHub CI na těchto commitech neběželo, proto byly všechny joby `orchestration-release-gate`
spuštěny lokálně (Windows 11, Python 3.13, Node 24, PostgreSQL 16 + Redis 7 v Dockeru).

| CI job | Výsledek |
|---|---|
| `lint` – ruff, mypy, bandit | ruff ✔, mypy ✔ (0 chyb / 154 souborů), bandit ✔ (bez nálezů ≥ medium) |
| `lint` – pip-audit | spustí se v B8 (vyžaduje síť) |
| `web-lint` – typecheck, eslint, dep-cruise | ✔ (po `npm ci`; lokální `node_modules` byly zastaralé – chyběl `fflate`) |
| web build (`npm run build`, mimo CI) | ✘ → nález **N10**, opraveno samostatným commitem `5a5eadf` |
| `test` – pytest na PG + Redis | **1786 passed, 1 skipped**, coverage 75 % (gate 40 %) |
| `test` – živé sondy (`verify_deploy.py`, kontrakty, auth, business flow) | spustí se v B8 |
| `postgresql-migrations` | ✔ 17/17 (+2 nové baseline testy) |
| `deployment-config` (compose + MinIO ze zdrojů) | spustí se v B8 (těžký build) |
| `deploy-linux-config` | ✔ `ALL CHECKS PASSED` (ubuntu:24.04 kontejner) |

Výsledek: **větev `fix/f0-…` je lokálně zelená**; jediný nalezený problém (N10) je
mimo CI a je opraven.

## 4. Migrace

- Nové revize: `20261017_0057` (RBAC), `20261017_0058` (soft delete fotek), `20261017_0059` (vlastnictví fotek, purge). Lineární řetězec, jeden head.
- Upgrade z předchozí produkční hlavy (`20260527_0055`/`0056`) s daty je pokryt `migration_tests`.
- `0059` downgrade odmítne běžet, existují-li fotky ve stavu `purge_pending` – rollback po nasazení vyžaduje nejdřív dokončit purge.
- Refaktor schéma ani migrace nemění (zmrazeno v `migration_tests/baseline/` a `tests/architecture/baseline/migrations.json` včetně SHA-256 každé revize).

## 5. Doporučený postup integrace (ke schválení)

> **Nahrazeno (2026-10-21, NC-001):** body 4–6 níže jsou historické. Platný postup je
> [INTEGRATION_REPORT.md §1](INTEGRATION_REPORT.md): **řetězené PR bez rebase** (PR 1 F0 → `master`,
> PR 2 refaktor → `fix/f0-…`, PR 3 N9 → `refactor/…`), merge merge-commitem se zachováním hashů;
> opravy N1, N2/N2b/N2c, N4, N10, N12 jsou součástí PR 2 (ne samostatné PR), N9 je PR 3;
> N5 je neplatný nález (viz [REFACTOR_FINDINGS.md](REFACTOR_FINDINGS.md)).
> Body 1–3 a 7 (CI, review, staging, rollback tag) platí dál.

1. **Push `fix/f0-rbac-tenant-isolation` na origin a PR do `master`** (ne merge). Nechat proběhnout plné GitHub CI včetně `deployment-config`.
2. Review po commitech; merge **merge-commitem** (ne squash) – dokumentace F0–F6 odkazuje na jednotlivé hashe.
3. Před merge zkouška na stagingu: záloha DB → `nc-provision migrate` (0056→0059) na kopii produkčních dat → `deploy/linux/tests/network_isolation.sh`.
4. Po merge: lokální `master` = `origin/master` (lokální `904ac05` zanikne jako předek).
5. Refaktor: `refactor/modular-architecture` rebase na nový `master`; PR po etapách (B0, B1, … B7) nebo jeden PR s jednotlivými commity – každý commit samostatně zelený.
6. Nálezy N1, N2, N4, N5: samostatné PR. **N2 je blokér produkčního nasazení.**
7. Rollback: tag `pre-f0-merge` na `origin/master` před merge; DB rollback jen z pre-migrační zálohy (viz bod 4 – downgrade 0059 má podmínku).

## 6. Otevřené otázky

| # | Otázka |
|---|---|
| I1 | Je natvrdo vypnutý SQL echo (`echo=False`) z `docs-cleanup` žádoucí? Pokud ne, samostatná oprava. |
| I2 | Má se `docs-cleanup` (2026-06-30, bez popisu změn v commit message) před push revidovat zvlášť? |
