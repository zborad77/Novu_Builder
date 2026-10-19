# Registr nálezů – modulární refaktor

Nálezy z auditu (Fáze A) a z průběhu Fáze B. **Žádný nález se neopravuje uvnitř
refaktorovacího commitu.** Každá oprava = samostatný commit s vlastním testem
(rozhodnutí O5). Stav se aktualizuje s každou etapou.

| # | Závažnost | Nález | Stav | Commit |
|---|---|---|---|---|
| N1 | střední | `analysis_repository` a `quote_variant_repository` volají `apply_transition` mimo registr efektů (`case_workflow/effects.py`): `proposal.ready` outbox se píše ručně a after-commit live publish neproběhne; přechod `analyzing→quote_ready` nemá efekty. | otevřeno – refaktor zachovává chování 1:1 | – |
| N2 | **blokér nasazení** | `worker/offer_runner.py` (+ reconciler, budget sweeper) nemá systemd ani compose službu → offer pipeline v produkci neběží. | otevřeno | – |
| N3 | nízká | `alembic/env.py` registruje offer tabulky jen vedlejším efektem `app/models/__init__.py`. | řešeno v refaktoru (explicitní registr modelů) – bez změny chování | – |
| N4 | střední | Qt `adminapi.cpp` skládá `/api/v1/api/v1/admin/...`; navíc `/admin/*` je jen v zóně admin, kam desktop nemá přístup. | otevřeno | – |
| N5 | střední | `org_users` routy (D-10) nemají `@limiter.limit` na rozdíl od `admin.py`. | otevřeno | – |
| N6 | info | Mrtvý kód: `app/user.api.py` (0 B), `core/email.py`, `deps.get_storage_consistency_service`, `CaseActionService.worker_quote_ready`; model `RolePermission` (tabulka se nečte, migrace F0 do ní zapisuje – **nemazat**). | `user.api.py` odstraněn v B1; ostatní ponechány | – |
| N7 | střední | Duplicitní business pravidla v klientech: web `ACTION_CONFIG`, `CasePhaseIndicator`; Qt výpočty cen, vlastní slovník stavů. | web: B6; desktop: otevřeno | – |
| N8 | info | Docs drift: `API_EXPOSURE_MATRIX.md` (86 vs 91 rout), docstring `images.py:400` (`{image_id}` vs `{photo_id}`). | B7 (jen dokumentace) | – |
| N9 | střední | ORM metadata × schéma z migrací se liší ve 114 položkách: 15 indexů a tabulka `reconciler_events` existují jen v migracích, 1 index jen v modelu, 97 rozdílných server defaultů. Testy (`create_all`) proto běží nad jiným schématem než produkce. Zmrazeno v `migration_tests/baseline/metadata_diff.txt`. | otevřeno – refaktor rozdíl nesmí změnit | – |
| N10 | střední | `npm run build` (web) nikdy neprošel: `tsconfig.node.json` zahrnoval jen gitignorovaný placeholder. CI build nespouští. | **opraveno** | `5a5eadf` |
