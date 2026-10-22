# NC-007 – vyhodnocení etapy 1

| | |
|---|---|
| **Datum** | 22. 10. 2026 |
| **Větev** | `feat/nc-007-secure-web-platform` (lokální, nepushnutá), základ `fix/n9-orm-migration-parity` 04076a1 |
| **Commity** | `aaed357` core soubory + bezpečnostní události · `460bf1b` gateway · `b87abf7` web · `0f08256` provoz · `e7f166a` kontrakt a návrh migrací · `36ece50` opravy z review |
| **Celkový stav NC-007** | **PARTIAL.** Etapa 1 (gateway, sessions, CSRF, soubory, web bez tokenů, provozní konfigurace) je hotová a otestovaná. MFA, pozvánky, ověření e-mailu a obnova hesla jsou **BLOCKED**: potřebují migraci, kterou zadání bez schválení zakazuje. Vizuální podoba webu je **BLOCKED**: chybí HTML mockup. |

## 1. Co etapa 1 dodala

| Oblast | Výsledek |
|---|---|
| Web Gateway/BFF | Samostatný proces `src/gateway` (D-02, žádný import z backendu). Používá HMAC kontrakt F3.4 a striktní allowlist generovaný z exposure matrix bez `/auth`, `/internal` a `/admin`. Neznámé routy vrací 404 a pravidla nikdy nebere z klientských hlaviček. |
| Sessions | Server-side v Redisu: AES-256-GCM s rotací klíčů, cookie `__Host-nc_sid` (HttpOnly, Secure, SameSite=Strict), nové `sid` při loginu (ochrana proti fixation), idle 30 min, absolutně 12 h, logout, logout-all, odhlášení v core při expiraci, rate limity a audit. |
| JWT | Zůstává v session gateway. Do prohlížeče se nedostane (tělo, hlavičky ani Web Storage). Gateway nemá klíč k podepisování JWT. Superadmin se přes gateway nepřihlásí (ověřeno E2E). |
| CSRF | Synchronizer token + Origin/Sec-Fetch-Site, pevné kódy chyb `CSRF_FAILED` / `ORIGIN_REJECTED` |
| Soubory | Nové `GET /files/images/{id}/{variant}` a `GET /files/exports/{id}` (zóny G, D). Kontrolu session, role a firmy dělá core. Data se streamují, podporují Range, mají bezpečné hlavičky a ochranu proti path traversal v úložišti. Smazaná fotka okamžitě vrací 404. Audit stažení exportu. Odpovědi API už neobsahují URL úložiště. Testy běží na lokálním adaptéru, produkční úložiště se nevybíralo. |
| Audit | `POST /internal/security-events` (jen zóna G, bez `Authorization`). Události gateway končí v `audit_logs`, ověřeno E2E. |
| Web | Volá jen `/bff/*`, bez tokenů v JS. Má odhlášení a „Odhlásit všude“. Admin sekce a impersonace jsou odstraněné (D-11), obnova hesla je skrytá do etapy 2. ESLint zakazuje XSS sinky a Web Storage. Typy jsou generované z `src/contracts`. |
| Provoz | `nc-gateway.service` s vlastním uživatelem a sandboxem, oddělený Redis gateway s ACL, nginx edge (CSP bez `unsafe-*`, `/api` a `/admin` vrací 404), generování a rotace secrets, provisioning jen s explicitním potvrzením, runbook. Nic není nasazené. |
| Desktop | Bez změny kódu. Relativní `/api/v1/files/...` URL skládá s kořenem API a posílá `Authorization` (ověřeno čtením, viz QA). |
| NovuAdmin | Kontrakt zóny admin se nezměnil: `security_surface` baseline a exposure testy prošly beze změny admin rout. Nové routy nejsou v zóně A. |

## 2. Akceptace NC-007

| # | Kritérium | Stav | Doklad |
|---|---|---|---|
| 1 | Samostatná Web Gateway, HMAC, striktní allowlist | **PASS** | gateway `tests/` (238), E2E 13/13 proti živému core |
| 2 | Server-side sessions (HttpOnly, Secure, SameSite, CSRF, regenerace, expirace, revokace, logout všude, fixation, rate limit, audit) | **PASS** | `test_auth.py`, `test_proxy.py`, `test_review_fixes.py`, E2E |
| 3 | JWT core nedostupný JS, gateway bez podpisového klíče | **PASS** | E2E `test_login_sets_an_opaque_httponly_cookie_and_never_returns_a_jwt`, `test_gateway_app_has_no_jwt_secret`, frontend testy Storage spy |
| 4 | MFA (TOTP, recovery kódy, re-auth, povinné pro firemní adminy) | **BLOCKED** | vyžaduje migraci 0060, viz [NC-007_STAGE2_MIGRATION_PROPOSAL.md](NC-007_STAGE2_MIGRATION_PROPOSAL.md) R1, R4, R5 |
| 5 | Registrace pozvánkou, ověření e-mailu, reset hesla, vynucená změna hesla, SMTP | **BLOCKED** | migrace 0060 (R1, R2) a rozhodnutí D-05 / SMTP účet (R3). Samoregistrace firmy zůstává blokovaná (beze změny). |
| 6 | Frontend: funkce, generované typy, stavy, bez business logiky | **PARTIAL** | Funkční a bezpečnostní vrstva je hotová (login, logout, session, fotky, stavy 401/403/prázdno/chyba). Vizuál BLOCKED (chybí mockup), dashboard, správa uživatelů firmy a nastavení firmy v UI dosud nejsou. |
| 7 | Secure file access přes Core a Gateway | **PASS** | `test_nc007_file_streaming.py` (52), E2E upload a stream |
| 8 | Desktop přes WG (aud nc-desktop, RBAC, tenant, device binding) bez F7 | **PASS (beze změn)** | stávající F3 testy v plné sadě, relativní URL ověřené čtením. Desktop build nespuštěn (NOT RUN). |
| 9 | NovuAdmin: stabilní API kontrakt | **PASS** | admin routy v baseline beze změny, F8.2 (generovaný výřez OpenAPI) zůstává otevřený |
| 10 | Testy (allowlist, HMAC, replay, audience, sessions, CSRF, tenant, org users, admin API, upload/download, soft delete, nedostupný Redis/Core, chybná env, IP spoofing) | **PASS** pro etapu 1 | MFA a registrační testy čekají na etapu 2 |
| 11 | Build a integrace (PG16, Redis7, full suite, gateway, frontend, kontrakty, boundary, ruff/mypy/bandit, audit závislostí, nginx/systemd/WG config) | **PASS s výhradou** | viz kap. 3. Audit závislostí hlásí zranitelnosti, které na větvi byly už před NC-007 (Pillow, seroval). |

## 3. Ověření (skutečně spuštěno koordinátorem nebo nezávislou QA)

| Příkaz | Výsledek |
|---|---|
| backend plná sada (PG 16 + Redis 7, coverage) | **1896 passed, 1 skipped**, 76 % (kap. 3.1) |
| `pytest migration_tests` | 19 passed (core role); ORM×migrace beze změny, žádná migrace |
| `ruff`, `mypy app/` (224 souborů), `bandit -ll -ii`, `lint-imports` | 0 chyb; 1 kept / 0 broken |
| `scripts.export_contracts --check`, `export_gateway_allowlist --check` | OK (změny kontraktu jsou explicitní, viz commit `aaed357`) |
| gateway `pytest tests` (skutečný Redis 7) | **238 passed** |
| gateway `ruff`, `ruff format --check`, `mypy --strict` | OK |
| E2E `tests_e2e/run_e2e.sh` (core v zóně gateway + worker + gateway + PG + Redis) | **13 passed** |
| web `typecheck`, `lint`, `dep-cruise`, `test` (27), `build`, `check:contracts` | vše OK |
| `deploy/linux/tests/validate-configs.sh` (ubuntu 24.04) | **ALL CHECKS PASSED** (106 kontrol) |
| `pip-audit` gateway | bez zranitelností |
| `pip-audit` backend, `npm audit --omit=dev` | Pillow 12.3.0 (24 GHSA) a seroval 1.5.2 (1 critical). Obojí bylo na větvi už před NC-007. |

### 3.1 Plná sada backendu

Nad `36ece50`, PostgreSQL 16 + Redis 7, izolovaná databáze: **1896 passed, 1 skipped, 0 failed**, coverage **76 %** (práh 40 %). Audit mocků (`tools/refactor/check_patch_targets.py`) OK.

### NOT RUN

| Co | Proč |
|---|---|
| Start `nc-gateway.service` pod systemd, `nc-provision gateway/smoke`, `network_isolation.sh` | vyžaduje Linux host se systemd (staging). Ověřeno jen `systemd-analyze verify/security`, `nginx -t`, shellcheck. |
| S3/MinIO streamování živě | produkční úložiště je nerozhodnuté (S-1). Ověřeno jednotkově s mockem boto3. |
| Desktop build a smoke | bez změny kódu desktopu. Ověřeno čtením. |
| CSP SPA v prohlížeči, Playwright e2e webu | Playwright v projektu není. Ověřeno staticky nad `dist`. |
| Gateway za skutečným nginx | jen validační kontejner s gateway stubem |

## 4. Review a QA

- **Security Review** (nezávislý, živé pokusy): žádný nález Critical ani High. Medium M1 a M2 a Low L1, L4, L5, L6 a L8 jsou opravené v `36ece50`. Zbylé Low jsou v navazujících taskách.
- **QA** (nezávisle spuštěné sady, konzistence komponent, akceptace bod po bodu): bez blokujících nálezů. F-1 (`Last-Event-ID`), F-2, F-3, F-4, F-5 a F-6 jsou opravené v `36ece50`. F-7 až F-10 jsou v navazujících taskách.

## 5. Navazující tasky (návrhy, nejsou založené)

| ID | Priorita | Task | Závislost |
|---|---|---|---|
| NC-007-S2 | P0 | Etapa 2: MFA TOTP, `login/start` + `login/mfa`, re-auth, MFA politika firmy, pozvánky a ověření e-mailu, obnova hesla, vynucená změna hesla, SMTP adaptér, BFF endpointy a web | schválení R1–R5 |
| NC-007-UI | P1 | Vizuální implementace webu (dashboard, zakázky, nabídky, katalogy, správa uživatelů firmy, nastavení firmy, CZ/EN) | HTML mockup |
| NC-007-RL | P1 | Rate limity core per routu, ne per URL (`Limiter(key_style="endpoint")`), přehodnotit všechny limity (review L2) | – |
| NC-007-AUD | P2 | Audit stažení exportu: Range auditovat jednou, rozhodnout fail-open / security-critical (review L3) | – |
| NC-007-SK | P2 | Neposílat `storageKey` do webu (review L7). Změna kontraktu. | schválení změny API |
| F4.7 | P1 | AI pipeline a offer worker: obrázky inline místo podepsaných URL | – |
| F8.2 | P2 | Generovaný výřez OpenAPI zóny admin jako artefakt pro NovuAdmin | – |
| F7 | P1 | Desktop přes WG (MFA v desktopu, device enrollment) | R4 |
| DEP-1 | P1 | Aktualizace Pillow → 13.x a `@tanstack/react-router` (seroval) | – |
| OPS-1 | P1 | Staging: start gateway pod systemd (`MemoryDenyWriteExecute` s cryptography), nginx edge, smoke, `network_isolation.sh`, nastavení burst pro `/bff/api/files/` (QA F-9) | staging server, schválení |
| OPS-2 | P3 | Deduplikace bezpečnostních hlaviček gateway/nginx (QA F-7) | – |
