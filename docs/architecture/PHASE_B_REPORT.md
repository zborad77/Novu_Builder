# Fáze B – report modulárního refaktoru

| | |
|---|---|
| Větev | `refactor/modular-architecture` (lokální, **nepushnuto**), z `3f581d7` |
| Commity | 22 (B0–B8, opravy nálezů); seznam: `git log --oneline 3f581d7..HEAD` |
| Prostředí ověření | Windows 11, Python 3.13, Node 24, PostgreSQL 16 + Redis 7 (Docker), Qt 6.10.3 + MSVC 2022 |
| Závazná architektura | [MODULAR_ARCHITECTURE.md](MODULAR_ARCHITECTURE.md) |

## 1. Nová struktura projektu

```
src/backend/      FastAPI modulární monolit, balíček app
  app/main.py, app/worker/            vstupní body (beze změny: app.main:app, python -m app.worker.runner)
  app/composition/                    router, wiring (porty), models (registr ORM), bootstrap, api/system
  app/modules/<modul>/public.py       veřejné rozhraní modulu
  app/platform/                       config, http (exposure/gateway/client IP/limiter), db, jobs, events, storage
src/frontend/     React/Vite – UI, prezentační stav, API klienti (features/*/api)
src/desktop/      Qt6 klient (samostatný CMake projekt)
src/contracts/    openapi/{openapi.json, routes.snapshot.json}, workflow/case-workflow.json
deploy/ ops/ scripts/ docs/ nginx/
```

Zrušené vrstvené balíčky: `app/{api, core, db, models, schemas, services, repositories,
case_workflow, work_catalog, offer_processing, ai, storage}` (hlídá test R4).

## 2. Mapa modulů a závislostí (skutečný stav, grimp, bez TYPE_CHECKING)

```
main         -> composition, media, cases, identity, audit, platform
worker       -> composition, offers, exports, workflow, quoting, analysis, catalog, media, cases, platform
composition  -> admin, offers, exports, workflow, quoting, analysis, catalog, media, cases, identity, audit, platform
admin        -> analysis, media, cases, identity, audit, platform
offers       -> cases, identity, platform
exports      -> workflow, quoting, analysis, media, cases, identity, audit, platform
workflow     -> quoting, analysis, catalog, media, cases, identity, platform
quoting      -> analysis, catalog, media, cases, identity, platform
analysis     -> catalog, media, cases, identity, audit, platform
catalog      -> media, cases, identity, platform
media        -> cases, identity, audit, platform
cases        -> platform
identity     -> audit, platform
audit        -> platform
platform     -> (nic)
```

Všechny hrany vedou dolů (import-linter `KEPT`, 218 souborů, 654 závislostí), žádné cykly
mezi moduly, mezi moduly jen přes `public.py`. Volání nahoru: 5 portů + registr efektů
(tabulka v MODULAR_ARCHITECTURE.md §2.1a).

## 3. Výsledky testů

| Sada | Baseline `3f581d7` | Finál `HEAD` |
|---|---|---|
| Backend pytest (PG 16 + Redis 7) | 1786 passed, 1 skipped | **1811 passed, 1 skipped** (+25 nových) |
| Coverage (`--cov=app`, gate 40 %) | 75 % | 75 % |
| Audit účinnosti mocků | 2244 patchů, 579 volaných | 2246 patchů, **579/579 volaných** |
| Statická kontrola cílů mocků | 619 cílů, 0 neúčinných | 0 neúčinných |
| `migration_tests` (čistá i existující DB) | 17 passed | **19 passed** (+2 baseline testy schématu) |
| Bezpečnostní regresní sada (F0, SA-05, SA-06, F0.3, F3, F3.4, F3.5, F3.6, D-10 + e2e tenant/security) | součást pytest | součást pytest – vše zelené |
| Živé sondy CI (`test-db-connection`, `verify_deploy`, `test-api-contracts` 8/8, `test-auth-validation` 6/6, `test-business-flow` 6/6) | – | **vše prošlo** (API + worker, strict processing ready) |
| ruff / mypy / bandit / pip-audit | OK / 0 chyb / 0 / – | OK / **0 chyb (218 souborů)** / 0 / **bez zranitelností** |
| `lint-imports` | – | **KEPT** |

Ověření účinnosti mocků: dynamický audit odhalil 3 patche, které by po přesunu kódu prošly
naprázdno, a statická kontrola 2 patche na neexistující atribut. Všech 5 bylo přesměrováno
na skutečné místo volání a ověřeno (B4a).

## 4. Shoda API a DB

| Kontrola | Výsledek |
|---|---|
| `src/contracts/openapi/openapi.json` | **beze změny** od B0 |
| `routes.snapshot.json` (pořadí rout pro exposure guard) | **beze změny** |
| Pořadí a parametry middlewarů | **beze změny** |
| Bezpečnostní povrch (zóny, RBAC/tenant závislosti, rate limity, exposure tabulka) | beze změny kromě jména DI provideru `get_project_service` → `get_case_reader` u 24 rout (ověřeno skriptem) |
| SQLAlchemy metadata | **beze změny** |
| Alembic: 59 revizí (SHA-256 obsahu), head `20261017_0059` | **beze změny** (jen přesun souborů) |
| Schéma PG po čisté instalaci | **beze změny** (`migration_tests/baseline/pg_schema.json`) |
| Rozdíl ORM × migrace (existující N9) | **beze změny** |
| Gateway allowlist (91 rout) | beze změny obsahu (jen `generatedFrom`) |

## 5. Buildy

| Komponenta | Výsledek |
|---|---|
| Backend Docker image (kontext `src/backend`) | build OK; v kontejneru import API + workeru, konfigurace mapperů a `init_modules()` OK |
| Web (`src/frontend`) | `npm ci`, typecheck, eslint (0 warnings), dep-cruise (0 porušení, 272 hran), `check:contracts`, `build` OK |
| Desktop (`src/desktop`, CMake + Ninja + MSVC, Qt 6.10.3) | čistý build 28/28 OK (i po opravě N4) |

## 6. Deployment

| Kontrola | Výsledek |
|---|---|
| `deploy/linux/tests/validate-configs.sh` (ubuntu:24.04: nginx -t, nft -c, systemd-analyze verify/security, sh -n) | **ALL CHECKS PASSED**, vč. nové jednotky `nc-offer-worker` (expozice 1.2) |
| `docker compose config` | OK, build kontexty `./src/backend`, služba `offer-worker` |
| `verify_import_startup.py`, `test-env.py` | OK |
| Bare-metal instalace na čistém serveru / upgrade existujícího | **nespuštěno** (vyžaduje staging) |
| GitHub CI, job `deployment-config` (compose + MinIO ze zdrojů) | **nespuštěno** (bez push/PR) |

## 7. Otevřená rizika a rozhodnutí

| # | Riziko / rozhodnutí | Doporučení |
|---|---|---|
| R1 | Větev nikdy neprošla GitHub CI (ani F0–F6). | Push + PR bez merge, nechat proběhnout celé CI (INTEGRATION_PLAN.md). |
| R2 | Upgrade existujícího bare-metal serveru: nová cesta `/opt/novuconstruct/src/backend` → nový venv; starý strom `python-backend/` zůstane. | Ověřit `nc-provision install && migrate && start && smoke` na stagingu; starý strom smazat ručně. |
| R3 | slowapi klíčuje limity jménem modulu routy → po nasazení se čítače limitů jednorázově vynulují (O8). | Akceptovat (uvedeno v CHANGELOG). |
| R4 | N2: první start offer workeru zveřejní backlog nepublikovaných outbox událostí; `AI_OFFER_PROVIDER=claude` ve vzoru = reálná volání AI (s budget limity). | Rozhodnout provider (claude/mock) před nasazením. |
| R5 | N12 (oprava publish) zapíná živé SSE události, které dosud v produkci nefungovaly – nové chování klientů (web/desktop). | Ověřit na stagingu s klienty. |
| R6 | ORM relace mezi moduly zůstávají (stringové, bez runtime importu); `public.py` některých modulů exponuje repozitáře a ORM modely. | Postupně zužovat veřejná rozhraní (další iterace). |
| R7 | N1: duplicitní zápis `proposal.ready` (repozitář vs. registr efektů) a mrtvá cesta `_transition_to_proposal_ready`. | Sjednotit/odstranit samostatně (zamčeno testy). |
| R8 | N9: testy (`create_all`) běží nad jiným schématem než produkce (migrace). | Samostatná oprava modelů/migrací. |
| R9 | N11: `test_case_transition_effects` závisí na pořadí testů. | Přidat fixture `test_tenants`. |
| R10 | N7 (desktop): Qt má vlastní výpočty cen a slovník stavů. | Generovat slovník z `src/contracts/workflow`. |
| R11 | N8: docstring purge routy (`{image_id}`) je zároveň `description` v OpenAPI. | Opravit jako schválenou změnu kontraktu. |

## 8. Body ke schválení (O2, O4, O8)

- **O2** – `novu-mobile/` (FROZEN) zůstal v kořeni beze změny; nic se na něj neodkazuje.
  *Návrh:* ponechat, nebo přesunout do `archive/novu-mobile` (čistě organizační změna).
- **O4** – backend není instalovatelný balíček; běží z adresáře `src/backend` (systemd
  `WorkingDirectory`, Docker `WORKDIR`). *Návrh:* ponechat; `[project]` + `pip install .`
  až při potřebě sdíleného kódu mimo backend.
- **O8** – *Schválit:* jednorázový reset čítačů rate limitů při nasazení (R3).

## 9. Lokální prostředí po práci

- Docker kontejnery `nc-refactor-pg` (port 55432) a `nc-refactor-redis` (56379) běží – lze odstranit
  `docker rm -f nc-refactor-pg nc-refactor-redis`. Docker Desktop byl během práce jednou restartován.
- `J:/tmp/nc_webtest` – pomocná kopie z diagnostiky; obsahuje **junction** `node_modules` na
  `src/frontend/node_modules`: nejdřív `rmdir J:\tmp\nc_webtest\node_modules`, pak smazat složku.
- `src/desktop/build/` obsahuje CMake cache se starou cestou `desktop-qt` – Qt Creator ho
  překonfiguruje (nebo smazat a sestavit znovu).
- Venv backendu byl přesunut s adresářem (`src/backend/.venv`), přidány `import-linter` a `libcst`.
