# NovuConstruct – modulární architektura

Závazný popis struktury po refaktoru (Fáze B). Návrh a zdůvodnění:
[MODULAR_ARCHITECTURE_PROPOSAL.md](MODULAR_ARCHITECTURE_PROPOSAL.md); nálezy: [REFACTOR_FINDINGS.md](REFACTOR_FINDINGS.md).

## 1. Repozitář

```
src/backend/    FastAPI modulární monolit (Python balíček `app`)
src/frontend/   React/Vite – jen UI, prezentační stav a API klienti
src/desktop/    Qt6 desktopový klient (samostatný CMake projekt)
src/contracts/  sdílené API kontrakty generované backendem (OpenAPI, pořadí rout, workflow)
deploy/ ops/ scripts/ docs/ nginx/   provoz, skripty, dokumentace
```

Kořen repozitáře označuje soubor `.novu-repo-root`; skripty a testy ho hledají
přes `app.platform.paths.repo_root()` místo počítání `parents[N]`.

## 2. Backend – vrstvy a moduly

Závislosti smějí vést jen **shora dolů** (vynucuje import-linter, `[tool.importlinter]`
v `src/backend/pyproject.toml`):

| Vrstva | Balíček | Odpovědnost |
|---|---|---|
| kompozice | `app.main`, `app.worker`, `app.composition` | sestavení aplikace a workeru, registr modelů, propojení portů, router, seedy |
| moduly | `app.modules.admin` | systémová administrace (superadmin zóna) |
| | `app.modules.offers` | offer requesty, AI budget, reconciler |
| | `app.modules.exports` | exporty/archivy zakázky, kontrola konzistence úložiště |
| | `app.modules.workflow` | orchestrace zakázky napříč moduly (use-cases, detail zakázky, akce stavového automatu) |
| | `app.modules.quoting` | varianty nabídky, položky, draft a finální návrh, odhady |
| | `app.modules.analysis` | analytické joby, vision pipeline, měření |
| | `app.modules.catalog` | katalog prací (global → tenant → work items → detekce), ceníky, materiály, dodavatelé |
| | `app.modules.media` | fotografie, markery, soft delete a purge (F0.3) |
| | `app.modules.cases` | zakázka, klient, stavový automat a registr jeho efektů |
| | `app.modules.identity` | organizace, uživatelé, autentizace, JWT zóny, RBAC, device binding, D-10 |
| | `app.modules.audit` | audit log, audit middleware, security-critical audit |
| jádro | `app.platform` | konfigurace, HTTP bezpečnost (F3/F3.4/SA-05), DB, joby, události/outbox, úložiště, observabilita |

`app.platform` neobsahuje doménovou logiku a nezná žádný modul.

### 2.1 Pravidla komunikace

| # | Pravidlo | Kontrola |
|---|---|---|
| R1 | Z jiného modulu (i z composition/worker) se importuje **jen** `app.modules.<modul>.public`. | `tests/architecture/test_module_boundaries.py` |
| R1b | Přes hranici modulu se neimportují privátní jména (`_x`). | totéž |
| R2 | Jen směrem dolů, bez cyklů. | import-linter (`lint-imports`) |
| R3 | `app.platform` neimportuje moduly, composition ani worker. | test + import-linter |
| R4 | Volání „nahoru“ jen přes port registrovaný v `app.composition.wiring` nebo přes registr efektů `cases`. Neregistrovaný port selže výjimkou (nikdy tiše). | test vstupních bodů, testy modulů |
| R5 | Transakce: synchronní volání `public` API předává `session`; přechod stavu + outbox v jedné transakci zůstává. | invariantní testy |
| R6 | Tenant izolace explicitně: route → `identity.public.resolve_org_id/require_org_id` → `org_id` do služby/repozitáře; `None` = superadmin. | bezpečnostní regresní sada |
| R7 | ORM relace mezi modely různých modulů se deklarují stringem; typové importy jen pod `TYPE_CHECKING`. | ruff/mypy, import-linter (`exclude_type_checking_imports`) |
| R8 | Každý vstupní bod volá `app.composition.models.import_all_models()`. | `tests/architecture/test_entrypoints_register_models.py` |

### 2.1a Porty (volání nahoru) a jejich propojení

| Port (definuje) | Implementace (dodává) | Účel |
|---|---|---|
| `audit.audit_log.register_actor_lookup` | `identity.audit_actor.lookup_audit_actor` | e-mail/organizace aktéra audit záznamu |
| `media.ports.register_export_invalidator` | `exports.ExportRepository.expire_project_exports` | purge fotky zneplatní exporty zakázky (F0.3), stejná transakce |
| `analysis.ports.register_quote_recalculator` | `quoting.recalculation.QuoteVariantRecalculator` | rekalkulace nabídky na analytické frontě |
| `analysis.ports.register_proposal_ready_notifier` | `workflow.proposal_ready.mark_proposal_ready` | analyzing → proposal_ready po rekalkulaci |
| `workflow.ports.register_final_proposal_exporter_factory` | `exports.ExportService` | exporty finálního návrhu |
| registr `cases.effects` (`before_transition`/`after_transition`) | `workflow.action_effects`, `exports.case_effects` | efekty přechodů zakázky |

Vše propojuje `app/composition/wiring.py::init_modules()`. Neregistrovaný port vyhodí
`RuntimeError`; registr efektů odmítne přechod, dokud nejsou poskytovatelé načteni.

### 2.1b Odchylky od návrhu Fáze A (podle analýzy skutečných závislostí)

- Orchestrace zakázky (`project_service`, `case_actions`, detail zakázky) je samostatný
  modul **workflow** nad media/quoting/analysis; `cases` je jen jádro (model, stavový
  automat, registr efektů). Jinak by cases ↔ media ↔ quoting tvořily cyklus.
- **exports** je samostatný modul nad workflow (exporty skládají detail zakázky).
- **admin** (systémová administrace) je horní modul, URL `/admin/*` beze změny.
- `ProjectWorkItem`, `ProjectWorkItemValue`, `VisionDetection` patří do **catalog**
  (specifikace work-catalog subsystému).
- ORM relace mezi moduly zůstaly (stringové, bez runtime importu) – jejich zrušení by
  změnilo eager-loading a kaskády.
- `shared` kernel nebyl potřeba (stavy zakázky vlastní `cases`, catalog je nad cases).
- Gateway allowlist zůstává v `docs/security/` (interní bezpečnostní konfigurace, O3).

### 2.2 Neměnné bezpečnostní invarianty

Pořadí middlewarů, pořadí a šablony rout (exposure guard bere první shodu), zóny,
závislosti RBAC/tenant guardů a rate limity jsou zmrazené v
`src/contracts/openapi/routes.snapshot.json` a `src/backend/tests/architecture/baseline/*`
a kontroluje je `tests/architecture/test_baselines.py`. Změna = schválená změna API.

## 3. Přidání nového backendového modulu

1. Zařaď modul do vrstvy (koho smí volat, kdo smí volat jeho) a přidej ho do
   `layers` v `[tool.importlinter]`.
2. Vytvoř `app/modules/<modul>/`:
   ```
   __init__.py      (prázdný)
   public.py        veřejné rozhraní – jediné místo pro importy zvenku
   models.py        ORM modely (relace k cizím modelům stringem)
   repository.py / service.py / schemas.py / ports.py (podle potřeby)
   api/routes.py    APIRouter, api/deps.py  DI providery modulu
   case_effects.py  (volitelně) efekty přechodů zakázky – registrace v composition
   ```
3. Modely přidej do `app/composition/models.py::import_all_models()`.
4. Router zařaď v `app/composition/router.py` – **na konec**, aby se nezměnilo pořadí
   existujících rout; každou novou routu klasifikuj v `app/platform/http/exposure.py`.
5. Porty (volání nahoru) a registrace efektů propoj v `app/composition/wiring.py`.
6. Schéma DB změň výhradně Alembic revizí (`alembic revision --autogenerate -m "<modul>_<popis>"`).
7. Testy dej do `tests/` (stejná konvence jmen), spusť `python -m scripts.export_contracts`
   a commitni změněné kontrakty – PR pak nese viditelnou změnu API.
8. `python tools/refactor/make_public.py --check` ukáže chybějící exporty z `public.py`.

## 4. Frontend – feature moduly

```
src/frontend/src/
  app/        router, layouty, providery, guardy (skládá features)
  pages/      stránky (skládají features)
  features/<f>/  index.ts (veřejné API) | api/ (jediné místo volání backendu) | hooks/ | components/ | containers/ | types/
  shared/     ui, lib (apiClient), api/generated (VYGENEROVÁNO z src/contracts)
  store/      prezentační stav (zustand)
```

Pravidla (ESLint boundaries + dependency-cruiser, CI `web-lint`):
- `features/X` nesmí importovat vnitřky `features/Y`; `app/` a `pages/` jen `features/<f>/index.ts`.
- `shared/lib/apiClient` smí importovat jen `features/*/api/**`.
- Žádná business logika: stavy, přechody, labely akcí, povinnost důvodu, ceny a
  oprávnění rozhoduje backend; frontend je zobrazuje. Slovník stavů a akcí je
  `shared/api/generated/caseWorkflow.ts`, typy API `shared/api/generated/openapi.ts`.
- `npm run check:contracts` selže, pokud vygenerované soubory neodpovídají `src/contracts`.

### 4.1 Přidání nové frontendové feature

1. `src/features/<f>/index.ts` – exportuj jen to, co potřebují `app/` a `pages/`.
2. Volání backendu jen v `features/<f>/api/*.ts` přes `apiClient`; typy odvozuj z
   `shared/api/generated/openapi.ts`.
3. Komponenty/hooky importují vlastní `api/` relativně; jiné features jen přes jejich `index.ts`.
4. Stránku přidej do `pages/` a routu do `app/router`.
5. `npm run typecheck && npm run lint && npm run dep-cruise && npm run check:contracts && npm run build`.

## 5. Desktop

`src/desktop` je samostatný CMake projekt (`NovuBuilder`), se zbytkem repozitáře
sdílí jen HTTP API. Smoke skripty v `src/desktop/scripts` hledají backend v `src/backend`.
