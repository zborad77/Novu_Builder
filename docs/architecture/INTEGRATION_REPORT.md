# Integrační report – F0–F6, modulární refaktor, N9

| | |
|---|---|
| Datum | 2026-10-20 |
| Stav | **Připraveno k push a PR – čeká na samostatné potvrzení.** Nic nepushnuto, žádný PR, merge ani deployment. |
| Navazuje na | [INTEGRATION_PLAN.md](INTEGRATION_PLAN.md), [PHASE_B_REPORT.md](PHASE_B_REPORT.md), [REFACTOR_FINDINGS.md](REFACTOR_FINDINGS.md) |

## 1. Stav a pořadí PR

PR jsou **řetězené** (každý se zakládá proti předchozí větvi), aby diff každého obsahoval jen jeho část;
po merge předchozího se báze dalšího přepne na `master`. Merge **merge-commitem** (ne squash) –
dokumentace odkazuje na jednotlivé hashe.

| # | Větev → báze | Commity | Rozsah | Obsah |
|---|---|---|---|---|
| PR 1 | `fix/f0-rbac-tenant-isolation` → `master` | 12 (`5b7a278`…`3f581d7`) | 139 souborů | F0 RBAC + tenant izolace, SA-05/06, F0.3, F3 zóny, F3.4/3.6, D-10, F6/F6.2 bare-metal; obsahuje i nepushnutý `5b7a278 docs-cleanup` a merge `904ac05` (dopady: INTEGRATION_PLAN §2) |
| PR 2 | `refactor/modular-architecture` → `fix/f0-rbac-tenant-isolation` | 24 (`5a5eadf`…) | ~720 souborů (převážně přesuny) | B0–B8 modulární monolit, kontrakty, frontend, opravy N10, N2/N2b/N2c, N12, N4, N1, tento report |
| PR 3 | `fix/n9-orm-migration-parity` → `refactor/modular-architecture` | 1 | 14 souborů | N9: ORM = schéma z migrací (bez migrace) |

Postup (každý krok až po potvrzení):
1. `git push -u origin fix/f0-rbac-tenant-isolation` → PR 1 → **plné GitHub CI** (orchestration-release-gate, repo-guard) → review → merge.
2. Teprve po zeleném CI PR 1: push `refactor/modular-architecture`, PR 2 s bází `fix/f0-…` (po merge PR 1 přepnout na `master`) → CI → review → merge.
3. Push `fix/n9-orm-migration-parity`, PR 3 → CI → merge. **N9 je blokér nasazení** – nasazovat až s ním.
4. Lokální `master` po merge srovnat s `origin/master`.

## 2. Výsledky CI

**GitHub CI na těchto commitech zatím neběželo** (vyžaduje push). Lokální ekvivalent všech jobů
`orchestration-release-gate` (Windows 11, Python 3.13, Node 24, PostgreSQL 16 + Redis 7):

| Job | PR 1 (`3f581d7`) | PR 2 (`refactor/…`) | PR 3 (`fix/n9-…`) |
|---|---|---|---|
| lint: ruff / mypy / bandit / pip-audit | ✔ / 0 chyb / 0 / – | ✔ / 0 / 0 / bez zranitelností | ✔ / 0 / 0 / – |
| lint: lint-imports, desktop↔API kontrakt | – | ✔ KEPT, ✔ 36 cest | ✔ |
| web-lint: typecheck, eslint, dep-cruise (+ check:contracts, build) | ✔ (build ✘ → N10) | ✔ vše | beze změny webu |
| test: pytest PG + Redis | 1786 passed, 1 skipped | 1811 passed, 1 skipped (+ N2c: cílené testy) | **1819 passed, 1 skipped** |
| test: živé sondy (verify_deploy, kontrakty, auth, business flow) | – | ✔ všech 5 | – |
| postgresql-migrations | 17/17 | 19/19 | 19/19 (nulový rozdíl ORM × migrace) |
| deployment-config (compose + MinIO ze zdrojů) | nespuštěno | `docker compose config` ✔, image ✔ | – |
| deploy-linux-config | ✔ | ✔ ALL CHECKS PASSED | – |
| desktop build (mimo CI) | – | ✔ MSVC + Qt 6.10.3 | – |

Audit účinnosti mocků: 579/579 volaných mocků zachováno na všech větvích.

## 3. Kontrola před push (provedena)

| Kontrola | Výsledek |
|---|---|
| repo-guard (zakázané soubory, PEM) na všech třech větvích | čisté |
| `scripts/ci-check-no-secrets.sh` | hlásí `src/backend/.env.production.example` – planý poplach na `CHANGE_ME_*` placeholderech v URL, **stejně už na `origin/master`**; skript není v CI |
| Hledání secrets v přidaných řádcích (`origin/master..fix/n9-…`, 95 tis. řádků) | jen testovací hesla ve fixtures bezpečnostních testů |
| Lokální cesty / jména stroje v commitech | žádné |
| Autor commitů | jednotně `Novusion <pavel.dostal@novusion.cz>`; atribuce v každém commitu refaktoru |
| Binární soubory | jen `design/NovuBuilder.png` (z `docs-cleanup`) |
| Velké generované soubory | kontrakty a baseline (openapi.json 15 tis. ř., mock_audit.json 19 tis. ř., generated openapi.ts 8 tis. ř.) – záměrné |

## 4. Změny chování

**PR 1 (F0–F6)** – bezpečnostní změny dle CHANGELOG (superadmin jen v zóně admin, RBAC role, tenant
izolace, soft delete/purge fotek, zónové JWT, gateway HMAC, device binding, D-10). Migrace 0057–0059.
`docs-cleanup`: SQL echo natvrdo vypnutý, potlačené hlučné loggery (otázka I1).

**PR 2 (refaktor + opravy)**
| Změna | Dopad |
|---|---|
| Cesty `src/backend`, `src/frontend`, `src/desktop` | bare-metal: nový venv v `/opt/novuconstruct/src/backend/.venv`; compose build kontext |
| Rate limity klíčované modulem routy | jednorázový reset čítačů při nasazení (O8 – schváleno) |
| Jména loggerů = nové cesty modulů | dotazy/alerty filtrující podle loggeru (`app.core.…`) upravit; alerting podle textu událostí beze změny |
| `init_modules()` ve všech vstupních bodech | chybějící propojení = okamžitá výjimka (dřív tiché vynechání) |
| N12 `publish` | **živé SSE události začnou fungovat** (dosud jen replay outboxu) – ověřit klienty |
| N2/N2c offer worker | nová služba, **nezapíná se automaticky**; `AI_OFFER_PROVIDER=mock` výchozí; `claude` jen s platným klíčem a tvrdými rozpočty |
| N2b budget sweeper | prošlé rezervace AI budgetu se začnou uvolňovat |
| N4 desktop admin | admin panel desktopu volá správné URL (funguje jen proti zóně admin) |
| Web | labely akcí ze serveru (shodné texty), `npm run build` funkční (N10) |
| API, DB schéma, migrace, middlewary, zóny, RBAC | **beze změny** (zmrazené baseline) |

**PR 3 (N9)** – jen ORM: testy a dev (`create_all`) dostanou indexy, server defaulty a tabulku
`reconciler_events` jako produkce. Produkční schéma ani data se nemění.

## 5. Zbývající blokery nasazení

| # | Blokér | Stav / co je potřeba |
|---|---|---|
| B-1 | GitHub CI na PR 1–3 | po potvrzení push |
| B-2 | **N9** | opraveno ve PR 3 – nasazovat až s ním |
| B-3 | **S-1 objektové úložiště** (F6.2) | `nc-provision start` bez `NC_OBJECT_STORAGE_READY=1` API nespustí – rozhodnutí v OBJECT_STORAGE_OPTIONS.md |
| B-4 | Staging ověření (§6) | nespuštěno |
| B-5 | Gateway (F4) | core strana (HMAC, allowlist, zóna gateway) hotová; samotný gateway proces (F4.1–4.8) dle IMPLEMENTATION_PLAN otevřen – zóna gateway na stagingu jen s testovacím podepisovačem |
| B-6 | Offer worker | zapnout až po `nc-provision offer-worker` (backlog) a rozhodnutí o `claude` |
| B-7 | Otevřené fáze plánu bezpečnosti | F5 (MFA), F6.3–F6.7, F7 – potvrdit, které jsou podmínkou pilotu |

## 6. Plán stagingu

Prostředí: čistý Ubuntu 24.04 (Hetzner) + kopie produkční DB (anonymizovaná dle pravidel provozovatele).

| # | Krok | Ověření |
|---|---|---|
| S1 | Čistá instalace: rozbalit release do `/opt/novuconstruct`, `nc-provision preflight`, `plan`, `install` | preflight bez blokací; `install` idempotentní (2. běh = 0 změn) |
| S2 | Migrace čisté DB: `nc-provision migrate` | head `20261017_0059`; `nc-migrate status` up to date |
| S3 | Migrace existující DB: obnovit kopii produkce (0055/0056) → `nc-provision migrate` | pg_dump záloha vznikla; head 0059; RBAC opravy dle migrace 0057; `alembic check` bez rozdílu (N9) |
| S4 | `nc-provision start` + `smoke` | nc-api@desktop/admin, nc-worker aktivní; porty jen loopback/socket; Redis ACL; práva DB (audit_logs append-only) |
| S5 | Workery | analýza (mock) projde fronta → výsledek; heavy lane export; `ready/processing?strict=1` = ready |
| S6 | Offer worker | `nc-offer-backlog` → posoudit; `NC_CONFIRM_OFFER_BACKLOG=1 nc-provision offer-worker` s `mock`; poté (volitelně) `claude` s testovacím klíčem a tvrdým rozpočtem |
| S7 | SSE | desktop/web dostanou živé `analysis.started`, `proposal.ready` (N12) i replay po reconnectu bez duplicit |
| S8 | Gateway | zóna gateway: nepodepsaný požadavek 401, podepsaný (test vector) 2xx, routa mimo allowlist 404, X-Forwarded-For ignorován |
| S9 | WG zóny | `deploy/linux/tests/network_isolation.sh` scénáře N1–N12; desktop přes wg-nc, admin přes wg-nc-admin; superadmin mimo admin zónu odmítnut |
| S10 | Přístupová oprávnění | bezpečnostní scénáře F0/D-10: tenant A nevidí data B; firemní admin jen vlastní firmu; purge fotky s auditem a ledgerem |
| S11 | Záloha a obnova | `scripts/backup.sh` → `ops/restore.sh` na čistý stroj; `verify_restore.sh`; kontrola konzistence úložiště |
| S12 | Rate limity | po nasazení čítače od nuly (O8); 429 po překročení limitu loginu |

## 7. Rollback

| Situace | Postup |
|---|---|
| Před merge | zavřít PR; nic se nenasadilo |
| Po merge, před nasazením | revert merge commitu PR (merge-commit → `git revert -m 1`) |
| Nasazení selže před migrací | ponechat předchozí release v `/opt/novuconstruct` (doporučeno: release do vedlejšího adresáře a přepnutí symlinkem), `systemctl restart nc-core.target` |
| Nasazení selže po migraci 0057–0059 | DB vrátit z pg_dump, který `nc-migrate` udělal před upgrade (`/var/backups/novuconstruct`); downgrade 0059 odmítne běžet při fotkách ve stavu `purge_pending` – proto obnova ze zálohy, ne downgrade |
| Problém jen s offer workerem | `systemctl disable --now nc-offer-worker` (ostatní služby nedotčeny) |
| Problém se živým SSE (N12) | klienti mají fallback na replay outboxu; revert jediného commitu `0302694` |
| Refaktor (cesty) | starý release s `python-backend/` + jeho venv; jednotky systemd z téhož release (`.nc-bak` zálohy) + `daemon-reload` |

Před produkcí: tag `pre-f0-merge` na `origin/master`, záloha DB a konfigurace `/etc/novuconstruct`.

## 8. Úklid lokálního prostředí

| Položka | Stav |
|---|---|
| Kontejnery `nc-refactor-pg`, `nc-refactor-redis` (+ anonymní volumes), image `nc-refactor-backend:b8` | odstraněny |
| `novutrade-backend` a ostatní projekty | **nedotčeny** (Docker Desktop běží; byl spuštěn během refaktoru, NovuTrade kontejner se rozběhl vlastní restart policy) |
| `J:/tmp/nc_webtest` | **nesmazáno** (ochrana nástroje proti mazání mimo repozitář) – nejdřív `rmdir J:\tmp\nc_webtest\node_modules` (junction), pak složku |
| Pomocný worktree a scratch soubory | odstraněny / mimo repozitář |

## Příloha A – texty PR (k potvrzení)

### PR 1 – Security hardening F0–F6
> **Base:** `master` ← `fix/f0-rbac-tenant-isolation`
>
> Bezpečnostní fáze F0–F6 podle `docs/security/IMPLEMENTATION_PLAN.md`: RBAC a tenant izolace (SA-01..SA-04), trusted client IP (SA-05), tenant RBAC + soft delete fotek (SA-06), vlastnictví a trvalé mazání fotek s ledgerem (F0.3), síťové zóny + exposure guard + zónové JWT (F3), podpis gateway (F3.4), device binding (F3.6), firemní správa uživatelů (D-10), bare-metal Private Core/Public Edge a idempotentní provisioning (F6, F6.2).
> Migrace 0057–0059 (nevratný downgrade 0059 při `purge_pending`). Obsahuje i dříve nepushnutý `docs-cleanup` (dokumenty obnoveny v `dcf210f`).
> Lokálně: pytest 1786 passed, migration_tests 17/17, deploy-linux ✔. Detail: `docs/architecture/INTEGRATION_PLAN.md`.

### PR 2 – Modulární monolit (src/backend, src/frontend, src/desktop, src/contracts)
> **Base:** `fix/f0-rbac-tenant-isolation` (po merge PR 1 → `master`)
>
> Modulární refaktor (Fáze B, `docs/architecture/MODULAR_ARCHITECTURE.md`): repozitář v `src/`, backend jako modulární monolit (11 modulů s `public.py`, `platform`, `composition`), hranice vynucené import-linterem a `tests/architecture`, sdílené kontrakty v `src/contracts`, frontend bez duplicitní business logiky. **API, DB schéma, migrace, pořadí rout a bezpečnostních middlewarů beze změny** (zmrazené baseline). Opravy nálezů v samostatných commitech: N10 (web build), N2/N2b/N2c (offer worker, sweeper, bezpečný provider), N12 (živé SSE), N4 (desktop admin URL), N1 (ochranné testy).
> Lokálně: pytest 1811 passed, migration_tests 19/19, živé sondy ✔, buildy web/desktop/image ✔, deploy-linux ✔. Report: `docs/architecture/PHASE_B_REPORT.md`, `INTEGRATION_REPORT.md`.

### PR 3 – N9: ORM metadata = schéma z migrací
> **Base:** `refactor/modular-architecture`
>
> Modely doplněny o 97 server defaultů, 15 indexů a model `reconciler_events` přesně podle migrací; test vyžaduje nulový rozdíl autogenerate. Bez nové migrace – produkční schéma ani data se nemění. Lokálně: pytest 1819 passed, migration_tests 19/19. **Blokér nasazení.**
>
> 🤖 Generated with [Claude Code](https://claude.com/claude-code)
