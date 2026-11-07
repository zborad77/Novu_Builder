# Registr nálezů – modulární refaktor

Nálezy z auditu (Fáze A) a z průběhu Fáze B. **Žádný nález se neopravuje uvnitř
refaktorovacího commitu.** Každá oprava = samostatný commit s vlastním testem
(rozhodnutí O5). Stav se aktualizuje s každou etapou.

| # | Závažnost | Nález | Stav | Commit |
|---|---|---|---|---|
| N1 | nízká (dluh) | Repozitáře `analysis_repository` a `quote_variant_repository` volají `apply_transition` mimo registr efektů. **Rozbor:** pro `analyzing→quote_ready` nejsou v registru žádné efekty (nic se nevynechá); `analyzing→proposal_ready` zapisuje outbox ve stejné transakci a živou publikaci po commitu dělá `AnalysisService` – funkčně shodné s efekty registru, jen zduplikované. Cesta přes registr (`AnalysisService._transition_to_proposal_ready` → `worker_proposal_ready`) se nikde nevolá (mrtvý kód). | **uzavřeno jako technický dluh**: ochranné testy `test_worker_transition_invariants.py` (právě jedna událost `proposal.ready`, žádné vynechané efekty); sjednocení na registr / odstranění mrtvé cesty = samostatné rozhodnutí | viz commit „N1“ |
| N2 | **blokér nasazení** | `worker/offer_runner.py` neměl systemd ani compose službu → offer pipeline neběžela. Prvním spuštěním se ukázaly dvě latentní chyby (N12, N2b). | **opraveno**: `nc-offer-worker.service`, compose `offer-worker` (profil `offers`); worker se **nezapíná automaticky** – `nc-provision offer-worker` vypíše backlog (`nc-offer-backlog`) a zapne ho až s `NC_CONFIRM_OFFER_BACKLOG=1`; `AI_OFFER_PROVIDER=mock` výchozí, `claude` jen s platným klíčem a tvrdými rozpočtovými limity (jinak worker odmítne start) | `c1d23cd`, `24f58b5`, viz „N2c“ |
| N3 | nízká | `alembic/env.py` registroval offer tabulky jen vedlejším efektem `app/models/__init__.py`. | **vyřešeno v refaktoru** – `app.composition.models.import_all_models()` / `init_modules()` ve všech vstupních bodech, hlídá `tests/architecture/test_entrypoints_register_models.py` | B3c–B4b |
| N4 | střední | Qt `adminapi.cpp` skládal `/api/v1/api/v1/admin/...`; `/admin/*` je navíc jen v zóně admin. | **opraveno** (cesty `/admin/...`, kontrola `scripts/check_desktop_api_usage.py` v CI); zóna admin = provozní omezení beze změny | `6fe92bc` |
| N5 | – | ~~`org_users` routy (D-10) nemají `@limiter.limit`~~ | **neplatný nález**: baseline `security_surface.json` (3f581d7) ukazuje stejné limity jako `admin.py` (60/10/10/60/5 za minutu); bez změny kódu | – |
| N6 | info | Mrtvý kód: `app/user.api.py` (0 B), `core/email.py` (nyní `platform/email.py`), `deps.get_storage_consistency_service` (nyní `exports/api/deps.py`), `CaseActionService.worker_quote_ready`; model `RolePermission` (tabulka se nečte, migrace F0 do ní zapisuje – **nemazat**); web `shared/lib/permissions.ts`. | `user.api.py` (B1) a `permissions.ts` (B6) odstraněny; ostatní ponechány (mazání = změna mimo refaktor) | `694fe1a`, `9432412` |
| N7 | střední | Duplicitní business pravidla v klientech: web `ACTION_CONFIG`, `CasePhaseIndicator`; Qt výpočty cen, vlastní slovník stavů. | **web vyřešen** (B6: hodnoty ze serveru a z kontraktu workflow); desktop otevřeno – Qt může generovat slovník z `src/contracts/workflow/case-workflow.json` | `9432412` |
| N8 | info | Docs drift: `API_EXPOSURE_MATRIX.md` (86 vs 91 rout, stará cesta `gateway/allowlist.json`); docstring purge routy v `media/api/images.py` uvádí `{image_id}` místo `{photo_id}`. | dokumentace **opravena**; docstring ponechán – je zdrojem `description` v OpenAPI, oprava = změna kontraktu ke schválení | viz commit „docs: N8“ |
| N9 | **blokér nasazení** | ORM metadata × schéma z migrací se lišily ve 114 položkách (97 server defaultů, 15 indexů a tabulka `reconciler_events` jen v migracích, 1 index pojmenovaný jinak) – testy a dev (`create_all`) běžely nad jiným schématem než produkce; `reconciler_events`, do které reconciler zapisuje, v nich chyběla. | **opraveno bez migrace**: modely doplněny tak, aby přesně odpovídaly migracím (produkční schéma ani data se nemění); `test_orm_metadata_matches_migrated_schema` nyní vyžaduje nulový rozdíl | větev `fix/n9-orm-migration-parity` |
| N10 | střední | `npm run build` (web) nikdy neprošel: `tsconfig.node.json` zahrnoval jen gitignorovaný placeholder (= SECURITY_AUDIT B3 / plán F0.4). Po opravě `tsc -b` emitoval `.js` vedle zdrojáků → dependency-cruiser pak alias importy resolvoval na vyloučené `.js` a tiše je vynechal (271 → 64 hran) a Vite by mohl bundlovat zastaralé `.js`. | **opraveno** (reference + `noEmit`) | `5a5eadf`, viz další commit |
| N11 | nízká (testy) | `tests/test_case_transition_effects.py` nepožaduje fixture `test_tenants`, spoléhá na seed z dříve běžícího testu – samostatně spuštěný soubor selže na FK (platí i na baseline `3f581d7`). | **oprava připravena, NEOVĚŘENO** (viz [N11 – záznam realizace](#n11--záznam-realizace)) | – (necommitnuto) |
| N12 | vysoká | `FailoverRedisClient` neměl `publish` → každá živá SSE publikace (efekty přechodů v API, analytický worker, outbox publisher) končila `AttributeError`, klienti dostávali události jen z replay outboxu. Na baseline už existovalo. | **opraveno** | `0302694` |
| N2b | střední | `BudgetSweeper`: `:expiry_interval::interval` v `text()` SQL → syntaktická chyba na PostgreSQL při každém průchodu; zapomenuté rezervace AI budgetu se neuvolňovaly. | **opraveno** (`CAST(... AS interval)` + `timedelta`) | `24f58b5` |

## N11 – záznam realizace

Úloha T3 (P1), Multi-Agent run #15, krok Coding, 2026-10-24.

- **Výchozí stav:** větev `feat/nc-007-secure-web-platform`, HEAD
  `ea5d5f9d2164f671989fd4dfb87d818b219cce84`. Cizí necommitnutá práce byla
  zachována beze změny: `M .gitattributes`, `M .gitignore`,
  `M docs/architecture/INTEGRATION_PLAN.md`, `M docs/architecture/INTEGRATION_REPORT.md`,
  `?? build.bat`, `?? test.bat`, `?? docs/architecture/BUILD_SCRIPT_NOTES.md`,
  `?? src/backend/.coverage`.
- **Pracovní diff N11:** pouze `src/backend/tests/test_case_transition_effects.py`
  (6+/4−). Všechny čtyři testy si explicitně vyžadují fixture `test_tenants`
  (session scope, idempotentní seed `org_e2e_a` / `usr_e2e_a1`). Je doplněn
  komentář s důvodem. Produkční kód, `conftest.py`, migrace ani závislosti se
  neměnily. Plošný seed ani vypnutí FK kontrol se nezavádí.
- **Statický rozbor (není runtime důkaz):** `_create_project` vkládá `Project`
  s `organization_id="org_e2e_a"` (FK `organizations.id`) a
  `created_by_user_id="usr_e2e_a1"` (FK `users.id`). Modul tyto řádky sám
  nevytváří. V `src/backend` není nikde `PRAGMA foreign_keys=ON`, takže
  výchozí SQLite z `conftest.py` FK nevynucuje. Selhání se proto očekává jen
  nad PostgreSQL (`TEST_DATABASE_URL`, jako v CI). Lokální běh bez
  `TEST_DATABASE_URL` ho pravděpodobně nereprodukuje. Hypotéza
  „chybí `test_tenants`“ zůstává nepotvrzená.
- **Reprodukce před opravou:** NOT RUN. Runtime zamítl spuštění
  `.venv\Scripts\python.exe -m pytest tests/test_case_transition_effects.py`
  (PowerShell i Bash) i `cmd /c test.bat pytest …` hláškou „requires approval“.
  Vyhrazená PostgreSQL DB se proto nepřipravovala ani neověřovala.
- **Po opravě (jednotlivě, celý modul, různá pořadí):** NOT RUN — DEPENDS ON
  reprodukce.
- **Build (`cmd /c build.bat backend`):** NOT RUN, zamítnuto stejně
  („requires approval“). Ruff, mypy, bandit, lint-imports,
  export_contracts --check, pip-audit a sada s coverage také NOT RUN.
- **`git diff --check`** nad změněným testem: bez nálezů.
- **Náhodné pořadí v CI:** odloženo. Vyžadovalo by novou závislost
  (`pytest-randomly` / `pytest-random-order`), což je mimo rozsah N11 a
  předloží se samostatně. N11 se navíc projevuje při samostatném běhu
  souboru. Proto je levnější kontrolou spustit v CI nad PostgreSQL vybrané
  moduly izolovaně, například `pytest tests/test_case_transition_effects.py`
  jako samostatný krok. I to je změna CI a navrhuje se samostatně.
- **Postup ověření (k ručnímu spuštění z `src/backend`, s vyhrazenou
  prázdnou PostgreSQL DB pro každou pytest session; `_setup_test_db` volá
  `drop_all`, takže souběžné běhy nad jednou DB se navzájem mažou):**
  1. V samostatném worktree čistého HEAD (`git worktree add`) spustit
     `pytest tests/test_case_transition_effects.py -p no:cacheprovider` →
     očekávané selhání FK (důkaz před opravou).
  2. Na pracovní kopii spustit stejný příkaz a potom každý ze čtyř node IDs
     samostatně (`::test_start_analysis_…`, `::test_approve_proposal_…`,
     `::test_send_quote_…`, `::test_complete_…`). Každý běh probíhá v nové
     session nad čerstvou DB.
  3. Kombinace pořadí: modul samostatně, modul před
     `tests/test_d1_e2e_analysis_flow.py` i po něm a čtyři node IDs
     v obráceném pořadí.
  4. `build.bat backend`, `bandit -r app/ -ll -ii`,
  `python -m scripts.export_contracts --check`, `pytest tests/ --cov=app --cov-fail-under=40`.
- **Závěr:** N11 **není** označen za opravený. Výsledky nenahrazují validaci
  SHA `3f581d7`, `027feb6`, `04076a1`, `ea5d5f9` ani DEP-1 a neuzavírají
  F1/R1, R2 ani R3.

### N11 – fix round 1 (run #15, Coding attempt 2, 2026-10-24)

Reaguje na review nálezy F1 (chybí reprodukce a ověřená oprava) a F2 (chybí
běhy, pořadí a kontroly). **Ani jeden nález toto kolo neuzavírá.**

- **Výchozí stav (ověřeno `git rev-parse HEAD`, `git status --short`):** HEAD
  `ea5d5f9d2164f671989fd4dfb87d818b219cce84`, stejná cizí práce jako výše.
  Pracovní diff N11 v testu se oproti předchozímu kolu nezměnil (6+/4−).
  Kromě tohoto odstavce se v tomto kole neměnil žádný soubor.
- **Prostředí (ověřeno `docker ps`):** běží kontejner `nc-refactor-pg`
  (`postgres:16`, `127.0.0.1:55432`, uživatel `postgres` podle
  `docker inspect`) a `nc-refactor-redis` (`127.0.0.1:56379`). Dotčené testy
  Redis nepoužívají (fronty jsou nahrazeny `patch`/`object()`). Vyhrazená DB
  se má jmenovat `n11_repro`. Existující DB v kontejneru se nesmí použít,
  protože `_setup_test_db` volá `drop_all`.
- **Pokusy o spuštění, všechny zamítnuté runtime hláškou „requires approval“
  (žádný exit kód, nic neproběhlo):**
  `docker exec nc-refactor-pg psql …` (výpis DB);
  `.venv\Scripts\python.exe -I n11_db.py list` (asyncpg, vytvoření
  `n11_repro`); `& .venv\Scripts\python.exe --version` (PowerShell);
  `cmd //c "test.bat pytest tests/test_case_transition_effects.py -v"`;
  `cmd //c "build.bat backend"` (jediný pokus o build).
- **Stav:** reprodukce před opravou NOT RUN. Běhy po opravě NOT RUN — DEPENDS
  ON reprodukce. Build a kontroly NOT RUN. Hypotéza zůstává nepotvrzená.
- **Připravené příkazy (PowerShell, `src/backend`; DB před každým během
  znovu vytvořit `DROP DATABASE n11_repro WITH (FORCE); CREATE DATABASE n11_repro;`):**
  ```powershell
  $env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/n11_repro"
  # 1) před opravou – čistý HEAD v samostatném worktree
  git worktree add ..\..\..\n11_baseline ea5d5f9d2164f671989fd4dfb87d818b219cce84
  Push-Location ..\..\..\n11_baseline\src\backend
  ..\..\..\Novu_Builder\src\backend\.venv\Scripts\python.exe -m pytest tests/test_case_transition_effects.py -p no:cacheprovider -v; "exit=$LASTEXITCODE"
  Pop-Location
  # 2) po opravě – stejný příkaz, potom každý node ID zvlášť (nová DB před každým)
  .venv\Scripts\python.exe -m pytest tests/test_case_transition_effects.py -p no:cacheprovider -v; "exit=$LASTEXITCODE"
  # 3) pořadí: obrácené node IDs; modul před/po tests/test_d1_e2e_analysis_flow.py
  ```
  Worktree se po ověření odstraní (`git worktree remove`).

### N11 – run #16 (Coding attempt 1, 2026-10-24)

- **Výchozí stav (ověřeno `git rev-parse HEAD`, `git status --short`):** HEAD
  `ea5d5f9d2164f671989fd4dfb87d818b219cce84`, větev
  `feat/nc-007-secure-web-platform`. Cizí práce beze změny (navíc proti
  prvnímu záznamu `M PHASE_B_REPORT.md`, `M REFACTOR_FINDINGS.md`). Diff testu
  stále 6+/4− a v tomto kole se neměnil. Měnil se jen tento odstavec.
- **Statický rozbor znovu ověřen:** FK `Project.organization_id` →
  `organizations.id` a `Project.created_by_user_id` → `users.id`
  (`app/modules/cases/models.py:64,66`). `test_tenants` je session-scoped
  a seeduje přes stejný `_TestSession` idempotentně (`session.get` před `add`).
  Doplnění fixture proto nemění data ostatních testů. Výchozí SQLite FK
  nevynucuje (v `app/` ani v `conftest.py` není `PRAGMA foreign_keys`).
  Zůstává to ale jen statický rozbor, ne runtime důkaz.
- **Zamítnuto runtime („requires approval“, bez exit kódu):**
  `.venv\Scripts\python.exe -m pytest tests/test_case_transition_effects.py -q`
  (PowerShell), `cmd //c "test.bat pytest …"` (Bash),
  `./build.bat backend` (jediný pokus o build) a `Get-Service *postgres*`.
- **Oprava postupu výše:** `git worktree add ..\..\..\n11_baseline` míří mimo
  kořen workspace (`J:\Github\n11_baseline`). Baseline worktree je proto
  potřeba založit uvnitř `J:/Github/Novu_Builder`, například
  `git worktree add .n11_baseline ea5d5f9…`, a po ověření ho odstranit.
- **Stav:** reprodukce NOT RUN. Běhy po opravě NOT RUN — DEPENDS ON
  reprodukce. Build a kontroly NOT RUN. N11 **není** opravený a F1/R1, R2
  ani R3 se neuzavírají.

### N11 – run #16 (Coding attempt 2, fix round 1, 2026-10-24)

- **Výchozí stav (ověřeno `git rev-parse HEAD`, `git status --short`,
  `git diff --stat`):** HEAD `ea5d5f9d2164f671989fd4dfb87d818b219cce84`, větev
  `feat/nc-007-secure-web-platform`. Pracovní diff beze změny proti attempt 1,
  diff testu stále 6+/4− (`test_tenants` ve 4 testech + komentář N11).
- **Kandidát vyhrazené DB (ověřeno `docker ps`, `docker inspect`):** běží
  kontejner `nc-refactor-pg` (postgres:16, port 55432, výchozí DB `novu_test`).
  Pro N11 je určena samostatná DB `n11_repro`, aby `drop_all` v conftest
  nezasáhl jiné běhy. Její založení a výpis aktivních připojení nebyly možné.
- **Zamítnuto runtime („requires approval“, bez exit kódu):**
  `docker exec nc-refactor-pg psql …` (výpis DB a připojení),
  `src/backend/.venv/Scripts/python.exe --version` (Bash i PowerShell)
  a `cmd //c "build.bat backend"` (jediný pokus o build).
- **Stav:** F1 (reprodukce před a po opravě) i F2 (validační matice) zůstávají
  NOT RUN, stejně jako build a kontroly. N11 **není** opravený.
- **Připravené příkazy pro ruční nebo povolený běh** (z `src/backend`, DB
  `n11_repro` vždy nejprve dropnout a znovu vytvořit):
  1. `docker exec nc-refactor-pg psql -U postgres -c "DROP DATABASE IF EXISTS n11_repro" -c "CREATE DATABASE n11_repro"`
  2. `$env:TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/n11_repro"`
  3. Baseline: `git stash` není dovolen, proto
     `git worktree add .n11_baseline ea5d5f9` a v něm
     `pytest tests/test_case_transition_effects.py -q -p no:randomly`
     (očekávání: FK chyba `organizations`/`users`), plus každý ze 4 node IDs
     samostatně.
  4. Kandidát (pracovní kopie): stejné příkazy, poté obrácené pořadí 4 node IDs,
     `pytest tests/test_d1_e2e_analysis_flow.py tests/test_case_transition_effects.py`
     a opačně.
  5. `build.bat backend`, `bandit -r app/ -ll -ii`,
     `python -m scripts.export_contracts --check`,
     `pytest tests/ --cov=app --cov-fail-under=40` (vlastní čerstvá DB),
     `pip-audit` (nálezy jen evidovat, DEP-1 je samostatný).
- **CI a náhodné pořadí:** odloženo. Vyžaduje novou závislost
  (`pytest-randomly`/`pytest-random-order`), a ta je mimo rozsah N11. Návrh je
  potřeba předložit samostatně až po doložené reprodukci.

### N11 – run #18 (Coding attempt 1, 2026-10-24)

- **Výchozí stav (ověřeno `git rev-parse HEAD`, `git status --short`,
  `git diff --stat`):** HEAD `ea5d5f9d2164f671989fd4dfb87d818b219cce84`, větev
  `feat/nc-007-secure-web-platform`. Diff testu beze změny (6+/4−), ostatní
  rozpracované soubory zachovány.
- **Zamítnuto runtime („requires approval“, bez exit kódu):**
  `src/backend/.venv/Scripts/python.exe -m pytest --version` (Bash i PowerShell),
  `Get-Service *postgres*` a `cmd //c "build.bat backend"` (jediný pokus o build).
  Bez spuštění Pythonu ani přístupu k DB nelze ověřit cílové připojení,
  reprodukovat selhání ani provést validační matici.
- **Stav:** F1 BLOCKED (bez oprávnění ke spouštění příkazů). F2 NOT RUN — DEPENDS
  ON F1. Build NOT RUN — BLOCKED. N11 **není** opravený. Potřebné příkazy jsou
  uvedené v předchozím záznamu (run #16, attempt 2). K jejich provedení je nutné
  povolit spouštění `.venv\Scripts\python.exe`, `docker exec` a `build.bat`,
  případně je spustit ručně.

### N11 – run #18 (Coding attempt 2, fix round 1, 2026-10-24)

- **Výchozí stav (ověřeno):** HEAD `ea5d5f9d2164f671989fd4dfb87d818b219cce84`,
  `git status --short` beze změny proti attempt 1, diff testu beze změny.
- **Nově zjištěno:** `docker ps` (povolen) vypsal kontejnery `nc-refactor-pg`,
  `nc-refactor-redis` a `novutrade-backend`. Kandidát PostgreSQL serveru tedy
  existuje, ale jeho databáze ani izolace ověřené nejsou.
- **Zamítnuto („requires approval“, bez exit kódu):**
  `src/backend/.venv/Scripts/python.exe --version` (PowerShell i Bash),
  `docker exec nc-refactor-pg psql -U postgres -Atc "select version(); …"` a
  `cmd //c build.bat backend` (jediný pokus o build).
- **Stav:** F1 BLOCKED, F2 NOT RUN — DEPENDS ON F1, build NOT RUN — BLOCKED.
  N11 **není** opravený. Bez povolení výše uvedených příkazů nelze další kolo
  posunout.

### N11 – run #19 (Coding attempt 1, 2026-10-24)

- **Výchozí stav (ověřeno `git rev-parse HEAD`, `git status --short`,
  `git diff`):** HEAD `ea5d5f9d2164f671989fd4dfb87d818b219cce84`, diff testu
  beze změny (6+/4−: `test_tenants` ve 4 testech + komentář N11);
  `tests/conftest.py` bez lokálních změn. Ostatní rozpracované soubory zachovány.
- **Statická kontrola (bez runtime):** v `app/` ani `tests/conftest.py` není
  `PRAGMA foreign_keys`, výchozí SQLite tedy FK nevynucuje (potvrzuje bod výše).
  Reprodukce N11 vyžaduje `TEST_DATABASE_URL` na vyhrazenou PostgreSQL DB.
  `test_tenants` je session-scoped a seeduje idempotentně (`session.get` před
  `add`), doplnění fixture tedy nemění data ostatních testů.
- **Zamítnuto („requires approval“, bez exit kódu):** `git worktree add --detach
  .novu/wt-n11-base HEAD` (izolovaná baseline), `git show HEAD:…` přes Bash,
  kopie baseline do scratchpadu, `.venv\Scripts\python.exe -m pytest
  tests/test_case_transition_effects.py` (PowerShell i Bash),
  `test.bat pytest …` a `build.bat backend` (jediný pokus o build).
- **Stav:** krok 1 (reprodukce a potvrzení opravy) BLOCKED, krok 2 (matice
  pořadí, backendová sada, coverage) NOT RUN — DEPENDS ON krok 1, build NOT RUN —
  BLOCKED. Kód ani testy nad rámec existujícího kandidáta nebyly měněny,
  protože příčina není runtime doložená. N11 **není** opravený.

### N11 – run #19 (Coding attempt 2, fix round 1, 2026-10-24)

- **Výchozí stav (ověřeno):** HEAD `ea5d5f9d2164f671989fd4dfb87d818b219cce84`,
  `git status --short` i diff testu (6+/4−) beze změny proti attempt 1.
- **Zamítnuto („requires approval“, bez exit kódu):**
  `src\backend\.venv\Scripts\python.exe --version`, `cmd /c test.bat pytest
  tests/test_case_transition_effects.py -q`, totéž přes Bash a
  `.\build.bat backend` (jediný pokus o build).
- **Nově:** celá matice z bodu 3–5 záznamu run #16/attempt 2 je sepsaná do
  jednoho skriptu pro ruční běh (mimo repozitář, scratchpad session
  `n11-matrix.ps1`): reset DB `n11_repro` před každým během, baseline ve
  worktree `.novu\wt-n11-base`, 4 testy samostatně, modul, obrácené pořadí,
  obě pořadí s `test_d1_e2e_analysis_flow.py`, celá sada s `--cov-fail-under=40`;
  log do `.novu\n11-matrix-*.log`. Odstraní jen vlastní worktree.
- **Stav:** F1 BLOCKED, F2 NOT RUN — DEPENDS ON F1, build NOT RUN — BLOCKED.
  N11 **není** opravený.

### N11 – run #20 (Coding attempt 1, 2026-10-24)

- **Výchozí stav (ověřeno):** HEAD `ea5d5f9d2164f671989fd4dfb87d818b219cce84`,
  větev `feat/nc-007-secure-web-platform`, `git status --short` i diff testu
  (6+/4−: `test_tenants` ve 4 testech + komentář N11) beze změny.
- **Statické ověření (čtení kódu, ne runtime důkaz):** `Project.organization_id`
  → FK `organizations.id`, `Project.created_by_user_id` → FK `users.id`
  (`app/modules/cases/models.py:64,66`); `_create_project` používá
  `org_e2e_a`/`usr_e2e_a1`, které vytváří jen session fixture `test_tenants`
  (idempotentní get-or-add + commit, bez úklidu). `db_session` je
  function-scoped a na `test_tenants` nezávisí. Kandidát tedy odpovídá
  hypotéze a je minimální (bez seedu, bez vypínání FK); další úprava kódu
  nebyla provedena.
- **Provedeno:** `git diff --check` – bez chyb (jen varování LF→CRLF u
  `.gitattributes`, `.gitignore`, `PHASE_B_REPORT.md`).
- **Zamítnuto („requires approval“, bez exit kódu):** dotaz na port 5432
  (`Get-NetTCPConnection`), `src\backend\.venv\Scripts\python.exe --version`,
  `git worktree add --detach .novu/baseline-ea5d5f9 ea5d5f9`,
  `build.bat backend` (jediný pokus o build).
- **Stav kroků 1–6:** PostgreSQL izolace NOT RUN — BLOCKED; baseline worktree
  NOT RUN — BLOCKED; matice baseline/kandidát NOT RUN — DEPENDS ON 1–2;
  build, ruff, mypy, bandit, lint-imports, export_contracts, pip-audit,
  coverage NOT RUN — BLOCKED. N11 **není** opravený.

### N11 – run #20 (Coding attempt 2, fix round 1, 2026-10-24)

- **Provedeno:** `git rev-parse HEAD` → `ea5d5f9d2164f671989fd4dfb87d818b219cce84`
  (beze změny). Kód testu ani fixtures nebyly měněny.
- **Zamítnuto („requires approval“, bez exit kódu):**
  `src/backend/.venv/Scripts/python.exe --version`, `git status --short`
  (přes Bash), `build.bat backend` (jediný pokus o build v tomto kole).
- **Nálezy review F1, F2:** neopraveny – izolace PostgreSQL, baseline
  worktree, matice pořadí, build a kontroly (ruff, mypy, bandit,
  lint-imports, export_contracts, pip-audit, coverage) NOT RUN — BLOCKED.
  N11 **není** opravený. Podmínka dalšího kola: povolit spouštění
  `src\backend\.venv\Scripts\python.exe`, `build.bat`, `git worktree` a
  přístup k vyhrazené PostgreSQL DB.

### N11 – run #20 (Coding attempt 3, fix round 2, 2026-10-24)

- **Provedeno (Bash):** `git status --short` (stav shodný se začátkem
  session), `git diff --stat` (7 souborů, +471/−9), `git diff
  src/backend/tests/test_case_transition_effects.py` (kandidát: parametr
  `test_tenants` ve čtyřech testech + komentář N11 u `_USER_ID`),
  `git worktree list` (jen hlavní worktree `ea5d5f9`). Kód testu ani
  fixtures nebyly měněny.
- **Zamítnuto („requires approval“, bez exit kódu):** venv Python
  (`--version`, PowerShell i Bash, absolutní cesta), `git worktree add
  --detach .novu/n11-baseline ea5d5f9…`, `cmd.exe /c build.bat backend`
  (jediný pokus o build v tomto kole), `git diff --check`.
- **Nálezy review F1, F2:** neopraveny – izolace PostgreSQL, baseline
  worktree, matice pořadí, build a kontroly (ruff, mypy, bandit,
  lint-imports, export_contracts, pip-audit, coverage) NOT RUN — BLOCKED.
  DEP-1 neřešeno (mimo rozsah). N11 **není** opravený. Opakování kola bez
  změny oprávnění nepřinese jiný výsledek.

### N11 – run #22 (Coding attempt 1, 2026-10-24)

- **Ověřovaný obsah:** HEAD `ea5d5f9d2164f671989fd4dfb87d818b219cce84`
  (`feat/nc-007-secure-web-platform`) + necommitnutý kandidát v
  `src/backend/tests/test_case_transition_effects.py` (parametr
  `test_tenants` ve čtyřech testech + komentář N11), beze změny oproti
  run #20. Ostatní cizí rozpracovaná práce zachována.
- **Statická kontrola (čtení):** `cases/models.py:64,66` – `Project` má
  FK `organizations.id` a `users.id` (`created_by_user_id`, RESTRICT);
  `_create_project` používá `org_e2e_a` / `usr_e2e_a1`, které vytváří
  jen session fixture `test_tenants` (`tests/conftest.py:261`). SQLite
  v testech FK nevynucuje (žádný `PRAGMA foreign_keys`), proto se chyba
  projeví až nad PostgreSQL (`TEST_DATABASE_URL`). Kandidát odpovídá
  příčině, nepřidává plošný seed a neoslabuje FK.
- **Zamítnuto („requires approval“, bez exit kódu):** venv pytest
  (Bash i PowerShell), `build.bat backend` (jediný pokus o build).
- **Nezměněno záměrně:** kód testu ani fixtures – kontrakt zakazuje
  účelové změny bez runtime důkazu.
- **NOT RUN — BLOCKED:** reprodukce na baseline, izolované testy, matice
  pořadí (vč. před/po `test_d1_e2e_analysis_flow.py`), build, ruff, mypy,
  bandit, lint-imports, export_contracts, pip-audit, coverage.
  N11 **není** opravený.

### N11 – run #22 (Coding attempt 2, fix round 1, 2026-10-24)

- **Ověřovaný obsah:** beze změny proti attempt 1 (HEAD `ea5d5f9…` +
  stejný necommitnutý kandidát v `test_case_transition_effects.py`).
- **Zamítnuto („requires approval“, bez výstupu a exit kódu):**
  `src\backend\.venv\Scripts\python.exe --version` (PowerShell i Bash),
  `cmd //c build.bat backend` (jediný pokus o build v tomto kole).
  Ověření `TEST_DATABASE_URL` a služby PostgreSQL bylo součástí
  zamítnutého příkazu.
- **F1, F2:** neopraveny. Reprodukce na baseline, matice pořadí, build a
  kontroly NOT RUN — BLOCKED (oprávnění spouštění). Kód ani testy
  nezměněny. N11 **není** opravený.

### N11 – run #22 (Coding attempt 3, fix round 2, 2026-10-24)

- **Ověřovaný obsah:** HEAD `ea5d5f9d2164f671989fd4dfb87d818b219cce84`
  (`git rev-parse HEAD`, proběhlo) + necommitnutý kandidát v
  `src/backend/tests/test_case_transition_effects.py` (`git diff`, proběhlo):
  fixture `test_tenants` ve 4 testech + komentář N11. Beze změny proti
  attempt 1 a 2.
- **Zamítnuto („requires approval“, bez výstupu a exit kódu):**
  `& src\backend\.venv\Scripts\python.exe --version` (PowerShell),
  `./.venv/Scripts/python.exe --version` (Bash), složené `git` příkazy
  (`rev-parse && status && diff --stat`), `cmd //c build.bat backend`
  (jediný pokus o build v tomto kole). Povoleny byly jen samostatné
  `git rev-parse HEAD` a `git diff -- <soubor>`.
- **Změna kódu:** žádná. Alternativa „zapnout `PRAGMA foreign_keys=ON`
  pro SQLite v `conftest.py`“ (aby se N11 projevil i bez PostgreSQL) byla
  zvážena a zamítnuta: mění chování celé sady a bez spuštění ji nelze
  ověřit – odporovalo by to kontraktu (změna jen podle doložené příčiny).
- **F1, F2:** neopraveny – NOT RUN — BLOCKED (oprávnění spouštění).
  Reprodukce na baseline, izolované testy, celý modul, obrácené pořadí,
  modul před/po `test_d1_e2e_analysis_flow.py`, build, ruff, mypy, bandit,
  lint-imports, export_contracts, pip-audit a coverage neproběhly.
  N11 **není** opravený.
- **Odblokování (mimo pravomoc agenta):** povolit spouštění
  `src\backend\.venv\Scripts\python.exe` a `build.bat`, `git worktree add`
  a zadat `TEST_DATABASE_URL` na vyhrazenou PostgreSQL DB (jedna DB na
  session, viz conftest `drop_all`). Další kolo bez změny oprávnění
  dopadne stejně – opakování kola nemá smysl.

### N11 – run #23 (Coding attempt 1, 2026-10-24)

- **Ověřovaný obsah:** HEAD `ea5d5f9d2164f671989fd4dfb87d818b219cce84`
  (`feat/nc-007-secure-web-platform`) + necommitnutý kandidát v
  `test_case_transition_effects.py` beze změny (`git diff`, proběhlo).
  `tests/conftest.py`: `_setup_test_db` dělá `drop_all` jen při
  `TEST_DATABASE_URL`; bez něj SQLite bez `PRAGMA foreign_keys` (čtení).
- **Zamítnuto („requires approval“, bez výstupu a exit kódu):** venv Python
  `--version` (PowerShell i Bash), `Get-Service *postgres*`,
  `cmd /c build.bat backend` (jediný pokus o build).
- **Kroky 1–5:** 1 (izolovaná PostgreSQL DB, ověření připojení) BLOCKED;
  2 (reprodukce na baseline) NOT RUN — DEPENDS ON 1; 3 (matice pořadí)
  NOT RUN — DEPENDS ON 1, 2; 4 (build, ruff, mypy, bandit, lint-imports,
  export_contracts, pip-audit, sada s coverage) BLOCKED; 5 cílené review
  diffu provedeno staticky (kandidát minimální, FK ani assertions
  neoslabeny, cizí práce zachována), záznam doplněn. Kód nezměněn.
  N11 **není** opravený.

### N11 – run #23 (Coding attempt 2, fix round 1, 2026-10-24)

- **Ověřovaný obsah:** stejný jako attempt 1 (HEAD `ea5d5f9`, `git status`
  beze změny proti začátku session; proběhlo přes Bash).
- **Zamítnuto („requires approval“):** `src/backend/.venv/Scripts/python.exe
  --version` a `-m pytest --version`, `cmd //c build.bat backend`
  (jediný pokus o build). Nálezy review F1 a F2 proto zůstávají otevřené.
- **Kroky 1–5:** 1 BLOCKED; 2 NOT RUN — DEPENDS ON 1; 3 NOT RUN — DEPENDS
  ON 1, 2; 4 BLOCKED; 5 jen tento záznam. Kód nezměněn, N11 **není**
  opravený. Odblokování viz výše; bez změny oprávnění nemá další kolo smysl.

### N11 – run #23 (Coding attempt 3, fix round 2, 2026-10-24)

- **Ověřovaný obsah:** HEAD `ea5d5f9d2164f671989fd4dfb87d818b219cce84`,
  `git status --short` shodný se začátkem session (přes Bash).
- **Zamítnuto („requires approval“):** `src/backend/.venv/Scripts/python.exe
  --version` (PowerShell) a `cmd //c build.bat backend` (Bash, jediný pokus
  o build). F1 a F2 zůstávají otevřené.
- **Kroky 1–5:** 1 BLOCKED; 2 NOT RUN — DEPENDS ON 1; 3 NOT RUN — DEPENDS
  ON 1, 2; 4 BLOCKED; 5 jen tento záznam. Kód nezměněn, N11 **není**
  opravený. Třetí kolo se stejnou blokací – nutné povolit spouštění
  `.venv` Pythonu a `build.bat` a dodat vyhrazenou PostgreSQL DB
  (`TEST_DATABASE_URL`), jinak další kolo nepřinese nové důkazy.
