# NovuConstruct – návrh modulární architektury (Fáze A)

| | |
|---|---|
| Stav | **NÁVRH – čeká na schválení.** Nic se neimplementuje, nepushuje ani nenasazuje. |
| Datum | 2026-10-19 |
| Výchozí stav | větev `fix/f0-rbac-tenant-isolation` @ `3f581d7` (10 commitů před `master`) |
| Rozsah | backend, web, desktop, kontrakty, CI, migrace, `deploy/linux` |

---

## 0. Shrnutí

1. **Repo layout:** `python-backend/ → src/backend/`, `web/ → src/frontend/`, `desktop-qt/ → src/desktop/`, nový `src/contracts/`. `deploy/`, `ops/`, `scripts/`, `docs/`, `nginx/` zůstávají v kořeni.
2. **Backend = modulární monolit** s 8 doménovými moduly (`identity`, `audit`, `catalog`, `cases`, `media`, `analysis`, `quoting`, `offers`), sdíleným jádrem `platform` a dvěma kompozičními kořeny (`main` = HTTP, `worker` = background).
3. **Kořenový Python balíček zůstává `app`.** Vstupní body `app.main:app`, `app.worker.runner`, `app.worker.healthcheck` se nemění → systemd, compose i Dockerfile mění jen cesty, ne příkazy.
4. **Žádná změna DB schématu.** Modely se jen přesouvají mezi soubory, `__tablename__` zůstává, Alembic řetězec (head `20261017_0059`) zůstává jeden a nedotčený.
5. **Žádná změna veřejného API** – vynuceno strojově: před refaktorem se zmrazí snapshot OpenAPI + pořadí rout + exposure tabulka a každý krok musí být byte-identický.
6. **Hranice vynucuje CI:** `import-linter` (backend), stávající ESLint boundaries + dependency-cruiser (frontend, se dvěma doplněnými pravidly), drift-checky kontraktů.
7. Migrace probíhá **mechanicky a po malých krocích** (jeden modul = jeden PR), s dočasnými re-export shimy, které se v posledním kroku odstraní a jejich návrat hlídá test.

---

## 1. Audit současného stavu

### 1.1 Velikost

| Část | Rozsah |
|---|---|
| `python-backend/app` | ~56 tis. řádků, 15 balíčků organizovaných **po vrstvách** (`api`, `services`, `repositories`, `models`, `schemas`, `core`…), ne po doménách |
| z toho seed data katalogu | ~6,9 tis. řádků (`work_catalog/*_seed_data.py`) |
| testy | 112 souborů v `tests/`, `migration_tests/`; 60 Alembic revizí |
| `web/src` | 89 souborů, už dnes vrstvené (`app/pages/features/shared/store`) a hlídané ESLint + dep-cruiserem |
| `desktop-qt/src` | jeden CMake target `NovuBuilder`, síťová vrstva `network/*Api`, ruční DTO |

### 1.2 Závislosti backendu (balíčková úroveň, top-level importy)

Vrstvy se navzájem kříží – typické zpětné hrany:

| Hrana | Soubor | Problém |
|---|---|---|
| `core → models, db` | `core/audit.py:31-32, 288` | „core" zná ORM a session factory |
| `core → worker` | `core/backpressure.py:10-11` | „core" zná fronty |
| `db → services, work_catalog` | `db/bootstrap.py:13, 52` | seeding zná doménové služby |
| `repositories → case_workflow, offer_processing` | `analysis_repository.py:10`, `quote_variant_repository.py:10,13` | repozitář dělá přechod stavu a zapisuje outbox |
| `case_workflow → worker, services, repositories` | `action_effects.py:47-50`, `case_actions.py:36-38` | stavový automat přímo zakládá joby jiných domén |
| `work_catalog → case_workflow` | `phase_bindings.py:32` | katalog zná stavy zakázky |
| `routes/org_users → routes/admin` (privátní) | `org_users.py:29` | import `_enforce`, `_commit_security_critical_audit` |

**Cykly:** při top-level importech žádný; skutečný cyklus je jediný – `core.config ↔ core.exposure ↔ core.gateway_auth` (řešen lokálními importy). Dalších ~40 lokálních importů je „preventivních" a po rozdělení zmizí.

### 1.3 Nálezy, které refaktor musí respektovat (neopravuje je potichu)

| # | Nález | Doporučení |
|---|---|---|
| N1 | `analysis_repository` a `quote_variant_repository` volají `apply_transition` **mimo registr efektů** (`case_workflow/effects.py`) – `proposal.ready` outbox se píše ručně, after-commit publish neproběhne. | Při přesunu **zachovat chování 1:1** (port volá jen `apply_transition`). Sjednocení s registrem = samostatná změna chování ke schválení. |
| N2 | `worker/offer_runner.py` (+ reconciler, budget sweeper) není nasazen v compose ani systemd → offer pipeline fakticky neběží. | Mimo refaktor; rozhodnout zvlášť. Modul `offers` připraví registraci, ale nespouští ji. |
| N3 | `alembic/env.py` registruje offer tabulky jen vedlejším efektem `app/models/__init__.py`. | Explicitní registr modelů (§4.6). |
| N4 | Qt `adminapi.cpp` skládá `/api/v1/api/v1/admin/...`; `/admin/*` je navíc jen v zóně admin. | Bug klienta, mimo refaktor (samostatný ticket). |
| N5 | `org_users` routy (D-10) nemají `@limiter.limit` na rozdíl od `admin.py`. | Mimo refaktor (bezpečnostní změna ke schválení). |
| N6 | Mrtvý kód: `app/user.api.py` (0 B), `core/email.py`, model `RolePermission` (tabulka se nečte), `deps.get_storage_consistency_service`, `CaseActionService.worker_quote_ready`. | `user.api.py` smazat v B1; ostatní jen označit (tabulku `role_permissions` **nemazat** – migrace F0 do ní zapisuje). |
| N7 | Duplicitní business pravidla v klientech: web `ACTION_CONFIG` (`caseActionsApi.ts:10-46`), `CasePhaseIndicator` (pořadí stavů), Qt výpočty cen (`casedetailview.cpp:998-1006`), Qt jiný slovník stavů (`analysed`, `in_progress`, `completed`). | Řešeno kontrakty (§6) a fází B6. |
| N8 | Docs drift: `API_EXPOSURE_MATRIX.md` uvádí 86 rout, allowlist má 91; docstring `images.py:400` uvádí `{image_id}` místo `{photo_id}`. | Opravit v B7 (jen dokumentace). |

---

## 2. Cílová adresářová struktura

```
/
├─ src/
│  ├─ backend/                      # dříve python-backend/
│  │  ├─ app/
│  │  │  ├─ main.py                 # HTTP kompoziční kořen (beze změny názvu)
│  │  │  ├─ composition/            # skládání napříč moduly (router, deps, read-modely, seedery)
│  │  │  ├─ platform/               # sdílené jádro (viz §4)
│  │  │  ├─ shared/                 # sdílený doménový kernel: ID typy, CaseStatus, Money, TenantContext
│  │  │  ├─ modules/
│  │  │  │  ├─ identity/
│  │  │  │  ├─ audit/
│  │  │  │  ├─ catalog/
│  │  │  │  ├─ cases/
│  │  │  │  ├─ media/
│  │  │  │  ├─ analysis/
│  │  │  │  ├─ quoting/
│  │  │  │  └─ offers/
│  │  │  └─ worker/                 # background kompoziční kořen (runner, healthcheck, offer_runner)
│  │  ├─ alembic/                   # beze změny, jeden řetězec revizí
│  │  ├─ tests/
│  │  │  ├─ conftest.py
│  │  │  ├─ modules/<modul>/…
│  │  │  ├─ platform/…
│  │  │  ├─ security/…              # bezpečnostní regresní sada (F0–F3, SA-05/06, D-10)
│  │  │  ├─ architecture/…          # testy hranic, snapshoty API
│  │  │  └─ e2e/…
│  │  ├─ migration_tests/
│  │  ├─ scripts/  tools/
│  │  ├─ pyproject.toml  alembic.ini  pytest.ini  requirements*.txt  Dockerfile
│  ├─ frontend/                     # dříve web/
│  ├─ desktop/                      # dříve desktop-qt/
│  └─ contracts/
│     ├─ openapi/openapi.json       # generováno z backendu, drift-check
│     ├─ openapi/routes.snapshot.json
│     ├─ security/gateway-allowlist.json   # přesun z docs/security/ (viz otázka O3)
│     ├─ workflow/case-workflow.json       # stavy, akce, labely, requires_reason
│     ├─ events/*.schema.json              # SSE / outbox eventy
│     └─ README.md                  # pravidla verzování kontraktů
├─ deploy/  ops/  nginx/  scripts/  docs/   # zůstávají
├─ novu-mobile/                      # FROZEN – viz otázka O2
└─ docker-compose.yml
```

### 2.1 Vnitřní struktura modulu (backend)

```
app/modules/<modul>/
├─ __init__.py          # prázdný (žádné side-effect importy)
├─ public.py            # VEŘEJNÉ API modulu – jediný bod importu pro ostatní moduly
├─ ports.py             # (volitelně) protokoly, které modul vyžaduje od okolí
├─ models.py            # ORM modely (případně models/ balíček)
├─ schemas.py           # Pydantic schémata HTTP vrstvy
├─ repository.py | repositories/
├─ service.py    | services/
├─ domain/              # čistá logika (např. transitions, pricing výpočty)
├─ api/
│  ├─ routes.py         # APIRouter(y) modulu
│  └─ deps.py           # DI providery modulu
├─ jobs.py              # handlery jobů / periodických úloh / reconcilerů (registruje worker)
├─ case_effects.py      # (volitelně) handlery efektů stavového automatu zakázky
└─ seed.py              # (volitelně) seeder modulu
```

---

## 3. Moduly a mapování souborů

Pořadí = povolený směr závislostí (modul smí importovat jen **nižší** moduly, a to jen přes `public.py`).

| Úroveň | Modul | Odpovědnost | Hlavní zdroje (dnes) | ORM tabulky |
|---|---|---|---|---|
| 0 | `platform` | infrastruktura bez doménové logiky | `core/{config, logging, metrics, redis_client, cache, request_id, api_versioning, client_ip, limiter, exposure, gateway_auth, sql_like, tenant_timing, slo}`, `db/{base, session, seed_runtime}`, `storage/*`, `worker/{queue, heavy_queue, offer_queue, heartbeat}`, `core/backpressure.py`, `offer_processing/outbox.py`, `core/events.py`, `routes/system.py` | `outbox_events` |
| 0 | `shared` | sdílený kernel – hodnoty, ne logika | stavy zakázky z `case_workflow/transitions.VALID_STATUSES`, `TenantRole`, ID typy | – |
| 1 | `audit` | audit log, audit middleware, security-critical commit | `core/audit.py` | `audit_logs` |
| 2 | `identity` | auth, JWT zóny, session, RBAC, firmy, uživatelé, device binding, throttling | `routes/{auth, org_users}`, část `routes/admin` (companies/users/impersonate), `services/{auth_service, company_service}`, `repositories/token_repository`, `core/{rbac, security, device_binding, account_limiter, token_limits}`, `schemas/{auth, company}`, `api/deps.get_current_user/require_*/resolve_org_id` | `organizations, users, revoked_tokens, user_sessions, password_reset_tokens, role_permissions` |
| 3 | `catalog` | globální katalog prací, tenant overrides, analysis profily, pricing profily, materiály, dodavatelé, ceníky | `work_catalog/*`, `services/{work_catalog, tenant_work_type_resolution, analysis_profile, pricing_profile, material_catalog, supplier, pricebook}_service`, odpovídající repozitáře, schémata a routy | `work_categories, work_types*, analysis_profiles*, catalog_pricing_profiles*, tenant_work_type_*, pricing_profiles, suppliers, material_catalog, supplier_material_prices` |
| 4 | `cases` | zakázky, klienti, stavový automat, timeline, SSE case events | `case_workflow/{transitions, effects, case_actions}`, `services/project_service` (bez read-model kompozice), `repositories/project_repository`, `routes/{cases, case_events}`, `schemas/project` (bez ProposalDraft*) | `clients, projects, project_status_history` |
| 5 | `media` | fotky, markery, soft delete / purge (F0.3), exporty, storage consistency | `routes/{images, markers, exports, storage}`, `api/photo_purge.py`, `core/purge_ledger.py`, `services/{photo, export, storage_consistency}_service`, repozitáře photo/marker/export/storage_consistency, část `routes/admin` (photo purge) | `project_photos, markers, project_exports` |
| 6 | `analysis` | analysis joby, výsledky, vision pipeline, měření, detekce | `ai/*`, `services/analysis_service`, `repositories/analysis_repository`, `routes/{analysis_jobs, measurements}`, `core/analysis_provider_capabilities.py`, část `routes/admin` (jobs) | `analysis_jobs, analysis_results, vision_detections` |
| 7 | `quoting` | rozsah prací zakázky, varianty nabídky, položky, draft/final proposal, odhady | `services/{quote_variant, proposal_draft}_service`, repozitáře quote_variant/proposal_draft/final_proposal, `routes/estimates`, `schemas/quote_variant`, ProposalDraft* schémata, CRUD `ProjectWorkItem` z work_catalog služby | `quote_variants, quote_items, project_proposal_drafts, project_final_proposals, project_work_items, project_work_item_values` |
| 8 | `offers` | offer requesty, AI budget, reconciler, offer runner | `offer_processing/*` (bez `outbox.py`), `routes/{offer_requests, offer_events}`, `schemas/offer_requests`, `worker/offer_runner.py` (handler) | `offer_requests, offer_jobs, agent_runs, ai_budget_reservations, organization_ai_budgets` |
| top | `composition` | sestavení aplikace | `api/router.py`, `api/deps.py` (zbytek), `db/bootstrap.py` (jako registr seederů), read-model detailu zakázky (`build_project_detail`) | – |
| top | `worker` | runtime běhu jobů | `worker/runner.py`, `worker/healthcheck.py` | – |

Kompletní tabulka soubor → modul (všech ~200 souborů) bude v B0 vygenerována do `tools/refactor/module_map.yaml`; tento soubor zároveň řídí codemod (§7.3).

### 3.1 Rozpad `routes/admin.py` (916 ř.)

`admin.py` se **nerozkládá na URL úrovni** – `/api/v1/admin/*` zůstává. Rozdělí se jen implementace: každý modul vystaví `admin_router` a `composition/router.py` je zařadí **ve stejném pořadí rout jako dnes** (kontrolováno snapshotem, §5.1). Sdílené helpery `_enforce` a `_commit_security_critical_audit` se stanou veřejným API `identity.public` resp. `audit.public` (oprava importu privátních symbolů z `org_users.py`).

### 3.2 Cross-modulové relace ORM

- **DB cizí klíče zůstávají beze změny** (žádná migrace).
- `relationship()` přes hranici modulu se ponechá jen směrem dolů (např. `ProjectPhoto.project`). Zpětné kolekce na nižších modulech (`Organization.projects`, `User.analysis_jobs`, `Project.photos/quote_variants/...`, `PricingProfile.quote_variants` …) se nahradí dotazy přes `public.py` vyššího modulu.
- **Výjimka s ohledem na chování:** eager-load graf na `Project` (`project_repository.py:104`) a mazání markerů při mazání fotky se přepíše tak, aby generoval **stejné SQL a stejné pořadí operací** – ověřeno testy duplikace/mazání (`test_d1_project_duplication_integrity`, `test_project_duplication_cleanup`, `test_r14_photo_delete`). Pokud by to nešlo bez změny chování, relace dočasně zůstane a hranice se označí jako výjimka v `import-linter` (`ignore_imports`) s ticketem.
- `VisionDetection.project_work_item_id` (analysis → quoting) zůstane jen jako FK sloupec bez `relationship()`.

---

## 4. Pravidla sdíleného jádra (`platform` + `shared`)

1. **Žádná doménová logika.** Platform nezná žádný model ani službu modulu. Test: `platform` nesmí importovat `app.modules.*` (import-linter `forbidden`).
2. **Obsah platform:**
   - `platform/config` – `Settings` (beze změny proměnných prostředí); doménové validace (např. analysis provider capabilities) se registrují jako validátory, aby config neimportoval `analysis`.
   - `platform/db` – `Base`, session factories (`AsyncSessionFactory` pro HTTP, `WorkerAsyncSessionFactory` jen pro worker – pravidlo se nemění), `model_registry.py`.
   - `platform/http` – middlewary F3/F3.4/SA-05 (`exposure`, `gateway_auth`, `client_ip`), `limiter`, `request_id`, `api_versioning`, error handlery.
   - `platform/jobs` – fronty, heavy lane, heartbeat, backpressure, **registry** handlerů (`register_job_handler`, `register_periodic_task`, `register_startup_reconciler`).
   - `platform/events` – outbox (`OutboxEvent`, `build_outbox_event`), in-process event bus pro doménové události.
   - `platform/storage` – adaptér local/S3 (pravidlo „local storage je DEV ONLY" platí dál).
   - `platform/observability` – logging, metrics, SLO.
   - `platform/ops` – `/health`, `/alive`, `/ready*`, `/metrics` (`routes/system.py`); zdravotní sondy domén se registrují (`register_readiness_probe`), takže system routy nebudou importovat `AnalysisJob`.
3. **`shared` kernel** obsahuje jen neměnné hodnoty sdílené víc moduly a klienty: `CaseStatus`, `TenantRole`, typy ID. Změna v `shared` = změna kontraktu (review + update `src/contracts/workflow`).
4. **Exposure tabulka (`EXPOSURE`) zůstává centrální** v `platform/http/exposure.py` – je to bezpečnostní pravidlo pro celé API a jeden zdroj pravdy pro gateway allowlist. Modul nesmí registrovat routu bez záznamu (test `test_every_route_is_classified` zůstává).
5. **Změny platform** vyžadují review vlastníka jádra (CODEOWNERS – nově vytvořit, viz §8).
6. **Model registry:** `platform/db/model_registry.import_all_models()` importuje `app.modules.*.models` explicitně; volá ho `alembic/env.py`, `main.py` (create_all v dev) a `tests/conftest.py`. Konec závislosti na vedlejších efektech `app/models/__init__.py` (N3).

---

## 5. Pravidla komunikace mezi moduly

| Pravidlo | Vynucení |
|---|---|
| R1. Modul importuje z jiného modulu **pouze** `app.modules.<x>.public` (nebo `shared`, `platform`). Žádné `models`, `repository`, `service`, `_privátní` symboly. | import-linter `forbidden` + vlastní test na `_`-symboly |
| R2. Závislosti jen směrem dolů dle tabulky §3 (DAG). | import-linter `layers` |
| R3. Žádné cykly (ani přes lokální importy). | import-linter (analyzuje i lokální importy) + `no-circular` na frontendu |
| R4. Volání **nahoru** jen přes registr/event: stavový automat `cases` publikuje efekty, `analysis`/`media`/`quoting` se do registru přihlásí (`case_effects.py`); analýza po dokončení emituje událost, kterou zpracuje `quoting`. | struktura + R2 |
| R5. Transakční hranice: synchronní volání `public` API v rámci **jedné session** (`session` se předává explicitně), aby se zachovala atomicita dnešních přechodů (`apply_transition` + outbox v jedné transakci). | code review + existující invariantní testy |
| R6. Read-modely skládající data více modulů (detail zakázky, export) žijí v `composition/`, ne v modulu. | import-linter (composition je top vrstva) |
| R7. Moduly nesdílí tabulky: zápis do tabulky smí jen vlastník; čtení cizí tabulky jen přes `public`. Výjimka: SSE routy čtou `outbox_events` (vlastník `platform/events`, read API). | review + test „model importován jen z vlastního modulu" |
| R8. Tenant izolace zůstává **explicitní**: route volá `identity.public.resolve_org_id/require_org_id`, `org_id` se předává do služeb a repozitářů, `None` = superadmin. Žádný „magický" filtr se nezavádí (byla by to změna chování). | bezpečnostní regresní sada |

### 5.1 Bezpečnostní invarianty, které refaktor nesmí změnit

| Invariant | Proč je křehký | Ochrana |
|---|---|---|
| Pořadí middlewarů: GatewaySignature → TrustedProxy → ExposureGuard → security_headers → request_id → log → CORS → Audit → ApiVersioning → HTTPSRedirect | změna pořadí rozbije F3.4 / SA-05 | `main.py` zůstává jediné místo registrace; nový test na pořadí `app.user_middleware` |
| Exposure je klíčována `(METHOD, šablona URL)` včetně názvů path parametrů; `_match_template` bere **první shodu v pořadí registrace** | přejmenování parametru / změna pořadí `include_router` změní zónu → 404 nebo únik | snapshot `routes.snapshot.json` (metoda, cesta, název endpointu, **pořadí**) – musí být identický; routy zůstávají ploché (žádné `Mount`) |
| slowapi klíč limitu = `"<module>.<function>"` | přesun `routes/auth.py` resetuje čítače a rozbije `test_f0_rbac_tenant_isolation.py:717` | zachovat názvy funkcí; test upravit na nový modul; při nasazení akceptovat reset čítačů (jednorázově, dokumentovat v release notes) |
| Audit middleware klíčuje literální URL (`/api/v1`…) a stringy akcí (`admin.image.purge`, `org.user.*`) | změna URL = změna názvů akcí v audit logu | URL se nemění; stringy akcí se přesunou do `audit.public` konstant beze změny hodnoty |
| JWT `aud`/`iss` per zóna (`nc-web`, `nc-desktop`, `nc-admin`), superadmin jen v admin zóně | – | beze změny kódu, jen přesun do `identity` |
| `resolve_org_id` → `None` jen pro superadmina | – | R8 |
| Purge pořadí: ledger → security-critical audit → complete_purge (F0.3) | – | `purge_photo_with_audit` se přesune jako celek do `media` |
| `"service": "python-backend"` v `/health` odpovědi | je to **hodnota API**, ne cesta | nepřejmenovat |

---

## 6. Kontrakty (`src/contracts/`) a klienti

### 6.1 Co se generuje

| Artefakt | Zdroj | Generátor | Drift-check |
|---|---|---|---|
| `openapi/openapi.json` | FastAPI app | `src/backend/scripts/export_contracts.py` | pytest + CI krok `--check` |
| `openapi/routes.snapshot.json` | `app.router.routes` (pořadí!) | tentýž | pytest |
| `security/gateway-allowlist.json` | `EXPOSURE` | `export_gateway_allowlist.py` (přesun cesty, logika beze změny) | stávající `test_gateway_allowlist.py` |
| `workflow/case-workflow.json` | `cases` stavy, akce, labely, `requires_reason` | `export_contracts.py` | pytest |
| `events/*.schema.json` | Pydantic modely SSE/outbox eventů | `export_contracts.py` | pytest |

Backend **nečte** `src/contracts` za běhu → produkční nasazení na contracts nezávisí.

### 6.2 Frontend (`src/frontend`)

- TS typy API se generují z `openapi.json` (`openapi-typescript`, dev dependency) do `src/shared/api/generated/` – ruční `*.types.ts` pro API postupně nahradit.
- `ACTION_CONFIG` a `CasePhaseIndicator` budou brát labely/`requires_reason`/pořadí z `availableTransitions` a `case-workflow.json` (backend je už posílá – žádná změna API).
- Doplnit chybějící pravidla dep-cruiseru: `app`/`pages` smí importovat jen `features/<x>/index.ts`; `apiClient` jen z `features/*/api` (dnes volá `LoginPage.tsx:22`, `AuthProvider.tsx:63`).
- „Žádná business logika ve frontendu" se vynucuje: (a) žádné výpočty cen (dnes nejsou – zachovat), (b) ESLint `no-restricted-syntax` na stringové literály stavů zakázky mimo `generated/`, (c) review checklist.
- `ArchiveViewerPage` (rozbalování exportu v prohlížeči, ověření SHA-256) – formát archivu se popíše schématem v `contracts/` (manifest), logika zůstává jako prezentační.

### 6.3 Desktop (`src/desktop`)

- Zůstává samostatný (vlastní CMake, žádné sdílené zdrojáky s backendem).
- Nová kontrola v CI: seznam endpointů používaných desktopem (`src/desktop/api-usage.json`, udržovaný ručně nebo extrahovaný skriptem z `network/*.cpp`) musí existovat v `openapi.json` – zachytí např. N4.
- Duplicitní výpočty cen a vlastní slovník stavů (N7) – samostatná položka v B6, **nebudou řešeny v rámci přesunu**.

### 6.4 Verzování kontraktů

Jakákoli změna `openapi.json` / `routes.snapshot.json` = změna veřejného API → PR musí mít label `api-change` a schválení (CODEOWNERS na `src/contracts/**`). Během refaktoru je povolena **nulová** změna.

---

## 7. Plán migrace

### 7.0 Předpoklady

- **F0–F6 nejdřív mergnout do `master`.** Aktuální větev je 10 commitů před masterem; refaktor nad nemergnutou větví by znamenal bolestivé konflikty. Refaktor poběží na `refactor/modular-architecture` z aktuálního `master`.
- Během refaktoru zmrazit větší feature práci v backendu (nebo ji rebaseovat po každém kroku).

### 7.1 Fáze B – kroky (každý krok = samostatný PR, zelená CI před dalším)

| Krok | Obsah | Změna importů Pythonu? | Hlavní riziko |
|---|---|---|---|
| **B0 Baseline** | Vygenerovat a commitnout `openapi.json`, `routes.snapshot.json`, test pořadí middlewarů, test „alembic autogenerate je prázdný" (PG), `module_map.yaml`; přidat `import-linter` v režimu report s dnešním grafem. | ne | – |
| **B1 Repo layout** | `git mv` do `src/` (zachová historii i exec bity); oprava všech cest – ~90 míst z auditu (CI, compose, `.gitignore`, `.gitattributes`, `deploy/linux`, `ops/restore.sh`, `scripts/*`, `*.bat`, `package.json`, desktop smoke skripty). Všechna `parents[N]`/„rodič backendu" nahradit helperem `repo_root()` (hledá marker soubor `.novu-repo-root`). Smazat `app/user.api.py`. | **ne** | rozbitá cesta v deploy/ops → kryto CI `deploy-linux-config`, `deployment-config`, `test_backup_restore_e2e` |
| **B2 Platform** | Přesun infrastruktury do `app/platform/*`, `shared/`, model registry, outbox do `platform/events`, fronty do `platform/jobs`. Staré moduly = re-export shimy. | ano (codemod) | patch stringy v testech |
| **B3a–h Moduly** | Po jednom: `audit` → `identity` → `catalog` → `cases` → `media` → `analysis` → `quoting` → `offers`. Přesun souborů, split `models/domain.py` a `models/work_catalog.py`, `public.py`, routy modulu. Shimy pro staré cesty. | ano (codemod) | rozbití pořadí rout → snapshot |
| **B4 Inverze závislostí** | `action_effects.py` → `case_effects.py` v cílových modulech; repozitáře přestanou volat `apply_transition` – nahradí to `cases.public.transition_in_uow()` **se stejným chováním** (N1); `core/audit` → `ActorResolver` protokol; `backpressure` bez doménových typů; `phase_bindings` → `shared.CaseStatus`. | ano | atomicita transakcí → invariantní testy |
| **B5 Kompoziční kořeny** | `worker/runner.py` → registry handlerů (moduly dodají `jobs.py`); `api/deps.py` rozdělit; `db/bootstrap.py` → registr seederů; `build_project_detail` → `composition/`. | ano | 239 patch stringů na `app.worker.runner` → shim `runner` re-exportuje jména, testy se migrují postupně |
| **B6 Kontrakty a klienti** | Generování kontraktů, TS typy, odstranění `ACTION_CONFIG` duplicit, nová dep-cruiser pravidla, desktop endpoint check. | – | – |
| **B7 Úklid** | Smazání všech shimů a prázdných balíčků (`app/services`, `app/repositories`, `app/models`, `app/schemas`, `app/core`, `app/api/routes`, `app/case_workflow`, `app/work_catalog`, `app/offer_processing`, `app/ai`, `app/storage`, `app/db`); import-linter strict; test „staré balíčky neexistují"; aktualizace `CLAUDE.md`, `ARCHITECTURE.md`, `docs/security/*`, README, DEPLOY, RUNBOOK. | – | – |
| **B8 Akceptace** | §9. | – | – |

### 7.2 Importy

- Kořen `app` zůstává (O1). Příklad: `app.services.photo_service` → `app.modules.media.service.photos`; `app.core.rbac` → `app.modules.identity.rbac` (veřejně přes `app.modules.identity.public`).
- Mapování drží `tools/refactor/module_map.yaml`; codemod (`libcst`, jen dev) přepisuje `import`/`from` a **stringové cíle** v `patch(...)`, `monkeypatch.setattr(...)`, `mypy` overrides v `pyproject.toml`.
- Shimy: `app/services/photo_service.py` = `from app.modules.media.service.photos import *  # noqa` + `DeprecationWarning`. CI v B3+ hlásí počet zbývajících použití; v B7 musí být 0.

### 7.3 Testy

- 630 stringových cílů `"app.…"` ve 46 souborech → codemod; 104 `inspect.getsource` asercí (`test_admin_hardening`, `test_admin_jobs_sanitization`) se ručně přepíšou na nové funkce **se stejným ověřovaným obsahem**.
- Testy se přesunou do `tests/modules/<modul>/`, `tests/security/`, `tests/platform/`, `tests/e2e/`; `conftest.py` zůstává jeden (+ případné `conftest.py` per modul pro lokální fixtures).
- Počet testů a coverage (`--cov=app`, ≥ 40 %) se porovnává s baseline z B0 – úbytek testů = chyba.

### 7.4 Build

| Část | Změna |
|---|---|
| Backend | `pyproject.toml` beze změny struktury (žádný `[project]` – O4); jen přidané `[tool.importlinter]`. Spouštění dál z `src/backend` (cwd). |
| Docker | `docker-compose.yml` `build.context: ./src/backend`; Dockerfile beze změny. |
| Web | `src/frontend` – žádné interní cesty se nemění (aliasy jsou relativní); CI `working-directory`. |
| Desktop | `src/desktop` – CMake je soběstačný; aktualizovat `build.bat`, README, smoke skripty (`$repoRoot`), `.gitignore`. |

### 7.5 Migrace databáze

- Žádná nová revize. Alembic adresář se přesune s backendem; `env.py` použije `import_all_models()`.
- Kontroly v každém kroku: (1) `alembic upgrade head` na **čisté** PG, (2) upgrade **existující** DB ze snapshotu na head (stávající `migration_tests/`), (3) `alembic check` / autogenerate musí vrátit prázdný diff → důkaz, že přesun modelů nezměnil metadata (názvy tabulek, constraintů, indexů).
- Budoucí moduly: dál **jeden lineární řetězec** revizí (jednodušší než branch labels per modul); konvence názvu `YYYYMMDD_NNNN_<modul>_<popis>.py`.

### 7.6 Deployment

**Bare-metal (`deploy/linux`, produkce bez Dockeru)** – mění se jen cesta `/opt/novuconstruct/python-backend` → `/opt/novuconstruct/src/backend`, v jednom commitu:

- `systemd/nc-api@.service` (WorkingDirectory, ExecStart), `systemd/nc-worker.service`, `bin/nc-migrate:20`, `provision/nc-provision` (preflight, venv, `.env.production.example`), `tests/validate-configs.sh:61-63`, komentář v `env/core.env.overrides`.
- Příkazy `uvicorn app.main:app` a `python -m app.worker.runner` **zůstávají**.
- Existující server: `nc-provision` vytvoří nový venv v `src/backend/.venv` (změní se cesta → reinstall), po úspěšném startu nabídne odstranění starého `python-backend/` stromu; `daemon-reload` už dnes dělá.
- Ověření: CI `deploy-linux-config` (systemd-analyze verify/security, nginx -t, nft -c) + ruční staging run `nc-provision` na čistém Ubuntu 24.04 a upgrade z předchozí release.

**Docker compose** – jen build context; entrypointy beze změny.

**`ops/restore.sh`, `scripts/backup.sh`** – cesty na `src/backend/...` (kryto `test_backup_restore_e2e`).

---

## 8. Automatické kontroly hranic

**Backend – `import-linter`** (`src/backend/pyproject.toml`, CI job `lint`):

```toml
[tool.importlinter]
root_package = "app"

[[tool.importlinter.contracts]]
name = "Vrstvy modulů (jen směrem dolů)"
type = "layers"
layers = [
  "app.main | app.worker | app.composition",
  "app.modules.offers",
  "app.modules.quoting",
  "app.modules.analysis",
  "app.modules.media",
  "app.modules.cases",
  "app.modules.catalog",
  "app.modules.identity",
  "app.modules.audit",
  "app.platform | app.shared",
]

[[tool.importlinter.contracts]]
name = "Jen veřejné API cizích modulů"
type = "forbidden"   # generuje se pro každý pár modulů: X nesmí importovat Y.{models,repository,service,api,domain,...}
# (v B0 generováno skriptem z module_map.yaml)

[[tool.importlinter.contracts]]
name = "Platform neimportuje domény"
type = "forbidden"
source_modules = ["app.platform", "app.shared"]
forbidden_modules = ["app.modules", "app.composition", "app.worker"]
```

Doplňkové pytesty v `tests/architecture/`: žádné importy `_privátních` symbolů z cizího modulu; každý ORM model je definován ve svém modulu; každá routa má exposure záznam (existující); routes snapshot; pořadí middlewarů; staré balíčky neexistují (po B7).

**Frontend** – existující ESLint boundaries + dep-cruiser (`no-circular`, `no-cross-feature-internals`) + 2 nová pravidla (§6.2).

**Repo** – nový `CODEOWNERS`: `src/backend/app/platform/**`, `src/backend/app/main.py`, `src/backend/alembic/**`, `src/contracts/**`, `deploy/**` → vlastník jádra. Tím vznikne konečně explicitní seznam „protected core files" (dnes jen v prose).

**CI** – `orchestration-release-gate` zůstává; job `lint` rozšířen o `lint-imports`; job `test` o `export_contracts.py --check`; nový jednoduchý job `contracts` (frontend typecheck proti vygenerovaným typům + desktop endpoint check).

---

## 9. Akceptace (B8)

| Kritérium | Jak |
|---|---|
| Kompletní backend test suite PG + Redis | CI `test` (Postgres 16, Redis 7); počet testů ≥ baseline B0, coverage ≥ 40 % |
| Migrace čistá i existující DB | `migration_tests/` + `alembic check` prázdný diff |
| Build webu | `npm ci && npm run typecheck && npm run lint && npm run dep-cruise && npm run build` v `src/frontend` |
| Build desktopu | `src/desktop/scripts/build-debug.ps1` (MSVC, Qt 6.10) + smoke skripty proti běžícímu backendu |
| Bezpečnostní regrese | `tests/security/` – F0, SA-05, SA-06, F0.3, F3, F3.4, F3.5, F3.6, D-10 (10 souborů, 152 test. funkcí) + `test_e2e_tenant_isolation`, `test_e2e_security_regression`, `test_admin_hardening`, `test_admin_phase2`, `test_security_critical_audit_routes`, `test_config_production_hardening` |
| Ruff, mypy (0 chyb), bandit | CI `lint` nad `app/` (overrides v `pyproject.toml` přemapovány, ne rozšířeny) |
| Instalátor `deploy/linux` | CI `deploy-linux-config` + ruční čistá instalace i upgrade na stagingu |
| Modulární hranice | `lint-imports` strict, `tests/architecture/`, dep-cruiser |
| Žádná změna API | `openapi.json` a `routes.snapshot.json` identické s B0; gateway allowlist 91 rout beze změny obsahu |
| Žádné staré adresáře za běhu | test na neexistenci starých balíčků + grep CI na `python-backend`, `desktop-qt`, `web/` v runtime souborech (kromě API hodnoty `"service": "python-backend"`) |

---

## 10. Rozšiřování o budoucí moduly

1. `tools/refactor/new_module.py <název>` – vygeneruje kostru dle §2.1 včetně `public.py`, testového adresáře a záznamu v import-linter vrstvách.
2. Checklist nového modulu: zařazení do DAG (úroveň), routy registrované v `composition/router.py`, **exposure záznamy pro každou routu**, modely v `model_registry`, Alembic revize s prefixem modulu, joby přes `platform/jobs` registry, události přes `platform/events`, kontrakty přegenerovány, testy v `tests/modules/<modul>/`.
3. Modul, který potřebuje data vyššího modulu, je nedostane importem – buď (a) přijme port v `ports.py` naplněný v `composition`, nebo (b) poslouchá událost.
4. Pokud modul jednou bude potřeba vyčlenit do samostatné služby, hranice `public.py` + události jsou přesně místa, kde vznikne HTTP/queue rozhraní.

Kandidáti v roadmapě, kteří do struktury zapadnou bez úprav jádra: `billing`, `notifications` (e-mail – dnes mrtvý `core/email.py`), `scheduling`, `mobile-sync` (pro budoucí Qt for Mobile).

---

## 11. Otázky ke schválení

| # | Otázka | Doporučení |
|---|---|---|
| O1 | Ponechat kořenový Python balíček `app`? | **Ano** – vstupní body a deploy příkazy beze změny, menší diff. |
| O2 | `novu-mobile/` (FROZEN) | Ponechat v kořeni beze změny, nebo přesunout do `archive/novu-mobile` – žádná runtime vazba. |
| O3 | Přesunout `docs/security/gateway-allowlist.json` → `src/contracts/security/`? | **Ano** (deploy ho nečte; jde o kontrakt). Mění se `generatedFrom` a cesta v testu, obsah ne. |
| O4 | Udělat z backendu instalovatelný balíček (`[project]`, `pip install .`)? | **Ne teď** – deploy funguje přes cwd; lze později. |
| O5 | Opravy nálezů N1, N2, N4, N5 | **Mimo refaktor**, samostatné PR po něm (každý je změna chování). |
| O6 | Nové dev závislosti: `import-linter`, `libcst` (backend), `openapi-typescript` (web) | Schválit. |
| O7 | Pořadí: nejprve merge F0–F6 do `master`, pak refaktor z `master` | **Ano.** |
| O8 | Reset slowapi čítačů při nasazení (důsledek přesunu `routes/auth.py`) | Akceptovat, uvést v release notes. |

---

## Příloha A – zdroje auditu

- Graf importů: AST analýza `python-backend/app` (balíčková i souborová úroveň, včetně lokálních importů).
- Inventura cest: CI (`.github/workflows/ci.yml`), `docker-compose.yml`, `deploy/linux/**`, `ops/**`, `scripts/**`, kořenové `*.bat`, `package.json`, `.gitignore`, `.gitattributes`, testy používající `parents[N]`.
- Bezpečnost: commity `36b6d41`, `892c979`, `45e79e1`, `730d882`, `91b8f06`, `a6b5bb3`, `bc490a7`, `3f581d7`; `docs/security/*.md`.
- Frontend/desktop: `web/eslint.config.js`, `web/.dependency-cruiser.cjs`, `web/src/**`, `desktop-qt/src/**`, `desktop-qt/CMakeLists.txt`.
