# Registr nálezů – modulární refaktor

Nálezy z auditu (Fáze A) a z průběhu Fáze B. **Žádný nález se neopravuje uvnitř
refaktorovacího commitu.** Každá oprava = samostatný commit s vlastním testem
(rozhodnutí O5). Stav se aktualizuje s každou etapou.

| # | Závažnost | Nález | Stav | Commit |
|---|---|---|---|---|
| N1 | střední | `analysis_repository` a `quote_variant_repository` volají `apply_transition` mimo registr efektů (`case_workflow/effects.py`): `proposal.ready` outbox se píše ručně a after-commit live publish neproběhne; přechod `analyzing→quote_ready` nemá efekty. | otevřeno – refaktor zachovává chování 1:1 | – |
| N2 | **blokér nasazení** | `worker/offer_runner.py` (+ reconciler, budget sweeper) nemá systemd ani compose službu → offer pipeline v produkci neběží. | otevřeno | – |
| N3 | nízká | `alembic/env.py` registroval offer tabulky jen vedlejším efektem `app/models/__init__.py`. | **vyřešeno v refaktoru** – `app.composition.models.import_all_models()` / `init_modules()` ve všech vstupních bodech, hlídá `tests/architecture/test_entrypoints_register_models.py` | B3c–B4b |
| N4 | střední | Qt `adminapi.cpp` skládá `/api/v1/api/v1/admin/...`; navíc `/admin/*` je jen v zóně admin, kam desktop nemá přístup. | otevřeno | – |
| N5 | střední | `org_users` routy (D-10) nemají `@limiter.limit` na rozdíl od `admin.py`. | otevřeno | – |
| N6 | info | Mrtvý kód: `app/user.api.py` (0 B), `core/email.py` (nyní `platform/email.py`), `deps.get_storage_consistency_service` (nyní `exports/api/deps.py`), `CaseActionService.worker_quote_ready`; model `RolePermission` (tabulka se nečte, migrace F0 do ní zapisuje – **nemazat**); web `shared/lib/permissions.ts`. | `user.api.py` (B1) a `permissions.ts` (B6) odstraněny; ostatní ponechány (mazání = změna mimo refaktor) | `694fe1a`, `9432412` |
| N7 | střední | Duplicitní business pravidla v klientech: web `ACTION_CONFIG`, `CasePhaseIndicator`; Qt výpočty cen, vlastní slovník stavů. | **web vyřešen** (B6: hodnoty ze serveru a z kontraktu workflow); desktop otevřeno – Qt může generovat slovník z `src/contracts/workflow/case-workflow.json` | `9432412` |
| N8 | info | Docs drift: `API_EXPOSURE_MATRIX.md` (86 vs 91 rout, stará cesta `gateway/allowlist.json`); docstring purge routy v `media/api/images.py` uvádí `{image_id}` místo `{photo_id}`. | dokumentace **opravena**; docstring ponechán – je zdrojem `description` v OpenAPI, oprava = změna kontraktu ke schválení | viz commit „docs: N8“ |
| N9 | střední | ORM metadata × schéma z migrací se liší ve 114 položkách: 15 indexů a tabulka `reconciler_events` existují jen v migracích, 1 index jen v modelu, 97 rozdílných server defaultů. Testy (`create_all`) proto běží nad jiným schématem než produkce. Zmrazeno v `migration_tests/baseline/metadata_diff.txt`. | otevřeno – refaktor rozdíl nesmí změnit | – |
| N10 | střední | `npm run build` (web) nikdy neprošel: `tsconfig.node.json` zahrnoval jen gitignorovaný placeholder (= SECURITY_AUDIT B3 / plán F0.4). Po opravě `tsc -b` emitoval `.js` vedle zdrojáků → dependency-cruiser pak alias importy resolvoval na vyloučené `.js` a tiše je vynechal (271 → 64 hran) a Vite by mohl bundlovat zastaralé `.js`. | **opraveno** (reference + `noEmit`) | `5a5eadf`, viz další commit |
| N11 | nízká (testy) | `tests/test_case_transition_effects.py` nepožaduje fixture `test_tenants`, spoléhá na seed z dříve běžícího testu – samostatně spuštěný soubor selže na FK (platí i na baseline `3f581d7`). | otevřeno | – |
