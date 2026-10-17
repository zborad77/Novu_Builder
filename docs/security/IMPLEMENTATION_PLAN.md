# NovuConstruct – Implementační plán (bezpečnost a private-first infrastruktura)

| | |
|---|---|
| **Datum** | 17. 10. 2026 |
| **Stav** | **NÁVRH ke schválení.** Nic se zatím neimplementuje. |
| **Vstupy** | [SECURITY_AUDIT.md](SECURITY_AUDIT.md) · [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md) · [API_EXPOSURE_MATRIX.md](API_EXPOSURE_MATRIX.md) · [WG_NETWORK_DESIGN.md](WG_NETWORK_DESIGN.md) |
| **Pravidla** | Každý úkol = samostatná větev a PR. Nemění stávající API kontrakty. Migrace jsou expand/contract. Žádný deploy bez schválení. Commity dle `docs/CHANGE_CONTROL.md`. |

## Přehled fází

```
F0 Stabilizace repa ──► F1 Critical/High ──► F2 Medium + testy izolace ──► F3 Zóny v backendu
                                                                              │
                     F6 Infrastruktura (lze začít paralelně po F0) ◄──────────┤
                                                                              ▼
                                                    F4 Gateway/BFF + web ──► F5 MFA a sessions
                                                                              │
                                              F7 Desktop přes WG ◄────────────┤
                                              F8 NovuAdmin modul ◄────────────┘
                                                          │
                                                          ▼
                                    F9 Provoz, zkouška obnovy, pentest, go-live
```

| Fáze | Cíl | Závisí na | Odhad |
|---|---|---|---|
| F0 | Repo v releasovatelném stavu | – | 1–2 dny |
| F1 | Odstranit Critical/High | F0 | 2–3 dny |
| F2 | Medium nálezy, matice rolí, cross-tenant testy | F1 | 4–6 dní |
| F3 | Zónový model, `aud`, tři instance API | F2 | 3–4 dny |
| F4 | Gateway/BFF, web na cookies, streamování médií | F3 | 6–8 dní |
| F5 | MFA, správa sessions | F4 | 4–5 dní |
| F6 | Hetzner infrastruktura bez Dockeru | F0 (paralelně) | 4–6 dní |
| F7 | Desktop přes WG, enrollment | F3, F6 | 5–7 dní |
| F8 | Modul NovuConstruct v NovuAdminu | F3, F6 | dle NovuAdminu (mimo repo) |
| F9 | Provozní připravenost a go-live | vše | 3–5 dní |

Odhady jsou orientační, pro jednoho vývojáře, a nezahrnují dokončení webového UI pro uživatele (B5).

**Minimum pro pilot s reálnými daty:** F0 + F1 + F2 + F3 + F6 (varianta B, jeden server) + F9.1–F9.3. Do dokončení F4 web v pilotu nebude, používá se jen desktop přes WG.

---

## F0 – Stabilizace repozitáře (release blokery)

| ID | Úkol | Hotovo, když | Testy |
|---|---|---|---|
| F0.1 | **B1:** opravit commit `docs-cleanup`. Obnovit `BACKUP_RESTORE.md` a dokumenty, na které vedou odkazy, nebo odkazy a test upravit. Rozhodnout, které dokumenty se opravdu ruší. | Na `master` žádný mrtvý odkaz (`CLAUDE.md`, `DEPLOY.md`, `RELEASE_CHECKLIST.md`, `docs/STAGING_ACCEPTANCE.md`, `ops/alerting/alerts.yml`, `scripts/generate_*.py`); push bez mazání cizí práce | `test_restore_preserves_db_only_contract_and_production_dr_non_claim` zelený; skript na kontrolu odkazů v CI |
| F0.2 | **B2:** vrátit fail-open throttle v `auth.py`, nebo ho podmínit flagem `AUTH_THROTTLE_DEV_FAIL_OPEN`, zakázaným ve strict prostředích | Bez flagu fail-closed ve všech prostředích | 3× `test_r08_account_throttle` zelené; nový test: flag + `APP_ENV=production` → start selže |
| F0.3 | **SA-13:** `APP_ENV` povinné, bez defaultu | Start bez `APP_ENV` skončí chybou s jasnou hláškou | test konfigurace |
| F0.4 | **B3:** opravit `web/tsconfig.node.json` (`vite.config.ts`), `noEmit`, `npm ci` | `npm run typecheck`, `lint` a `build` zelené | CI job web |
| F0.5 | CI proti PostgreSQL a Redisu zelené na `master` | Plná sada testů zelená v CI (dnes lokálně 87 selhání, převážně kvůli prostředí) | CI |
| F0.6 | Doplnit `pip-audit` a `npm audit` do CI | High/Critical blokuje merge | CI |

---

## F1 – Critical a High

| ID | Úkol | Hotovo, když | Testy |
|---|---|---|---|
| F1.1 | **SA-01:** migrace odstraní řádky `manager` z `role_permissions`. Všechny `/admin/*` vyžadují superadmina. Enum rolí (`superadmin`, `manager`, `technician`), oprava defaultu `dispatcher`. Zákaz změny vlastní role. Zákaz operací nad superadminem pro ne-superadmina. | Manažer dostane 403 na každém `/admin/*`. Reprodukce z auditu selže. | Nové testy: manažer → reset hesla superadmina (403), manažer → PATCH vlastní role (403), manažer → POST user do cizí firmy (403), neplatná role (422), migrace up/down |
| F1.2 | **SA-04:** heslo přes `PATCH /admin/users` jde cestou resetu (síla hesla, `token_version`, revokace sessions, security-critical audit s `password_changed`) | Slabé heslo vrací 400; staré tokeny cíle dostanou 401 | `test_admin_patch_password_*` |
| F1.3 | **SA-02:** `update_project` ověřuje `client_belongs_to_org` | Cizí `clientId` vrací 404 nebo 422 | cross-tenant test PATCH `clientId` |
| F1.4 | **SA-03:** samostatná `key_func` (jen IP) pro `/auth/*` | 12 pokusů s podvrženou hlavičkou → 429 po 10 | regresní test z auditu |
| F1.5 | **SA-05:** slowapi `storage_uri=REDIS_URL`; uvicorn `--proxy-headers --forwarded-allow-ips=<proxy>` | Limit platí napříč workery; audit vidí skutečnou IP klienta | test se 2 workery (integrační) |

**Exit F1:** žádný otevřený Critical ani High. Znovu proveden audit admin modulu.

---

## F2 – Medium nálezy, matice rolí, izolace firem

| ID | Úkol | Hotovo, když | Testy |
|---|---|---|---|
| F2.1 | Matice rolí po endpointech (schválit podle API_EXPOSURE_MATRIX) a doplnit `require_manager` (**SA-06**). `auto_review_bypass`/`auto_send` jen pro mgr. | Technik dostane 403 na všech mgr routách | parametrizovaný test: každá route × role → očekávaný kód |
| F2.2 | **SA-07, SA-08, SA-23:** validace vnořených ID (`defaultSupplierId`, `referenceImageId`, `analysisJobId`, `photo_ids`), limit `polygon`, kontrola zámku u `POST measurements`, 404 místo 500 | Cizí ID vždy 404 nebo 422, nikdy 500 | cross-tenant test pro každé vnořené ID |
| F2.3 | **Generický cross-tenant test:** pro každou route s `{…_id}` vytvoří objekt ve firmě B a volá jako firma A | Pokrytí 100 % rout s ID (kontroluje meta-test) | `tests/test_tenant_isolation_matrix.py` |
| F2.4 | **SA-09:** `/mock-storage`, odmítat `..`, ID zakázky z normalizované cesty | Traversal vrací 404 | test traversal |
| F2.5 | **SA-10, SA-18:** reuse refresh tokenu revokuje session; kontrola `access_jti` | Replay starého refresh tokenu zneplatní i nejnovější | testy rotace a reuse |
| F2.6 | **SA-11:** validace obrázků v `asyncio.to_thread`, `MAX_IMAGE_PIXELS` 40 Mpx, kontrola rozměrů před `load()`, max 20 souborů na request | Upload 200 PNG 10k×10k neblokuje `/alive` (latence < 200 ms) | zátěžový test |
| F2.7 | **SA-12:** SSE re-validace session každých 60 s, limit 5 streamů na uživatele a 500 globálně, vlastní Redis pool | Logout ukončí stream do 60 s | test SSE + logout |
| F2.8 | **SA-14:** admin zápisy security-critical; audit admin GET, neúspěšných loginů a stahování exportů; `REVOKE UPDATE, DELETE ON audit_logs` | Každá admin operace má řádek v auditu; UPDATE z aplikační role selže | testy auditu + DB test práv |
| F2.9 | **SA-15:** impersonační token se `sid`, revokovatelný, re-validace impersonátora, zákaz `/auth/sessions/*`; web impersonaci odstranit (D-11) | Revokace okamžitě zneplatní token | testy impersonace |
| F2.10 | **SA-17, SA-24:** `openapi_url=None` mimo debug, CORS odmítá `*`, `REQUIRE_HTTPS` ve strict prostředí, TrustedHost, Sentry `before_send`, `/api/v1/` bez `APP_ENV` | Simulovaná produkce: `/openapi.json` vrací 404 | testy konfigurace |
| F2.11 | **SA-19:** progresivní zpoždění místo tvrdého zámku, klíč IP + účet | Útočník z jiné IP nezablokuje oběť | test |
| F2.12 | **SA-21, SA-22:** nová ID jako plné UUID (stará zůstávají); strip EXIF při příjmu (originál bez GPS) | Nová fotka nemá EXIF GPS | test uploadu s EXIF |
| F2.13 | **SA-25:** dev seed hesla náhodná, odstranění ze skriptů | `git grep` nenajde výchozí heslo | CI secret scan |

**Exit F2:** žádný otevřený Medium v backendu (kromě těch, které řeší F3 a F4). Zelená matice rolí a izolace firem.

---

## F3 – Zónový model v backendu

> **Stav 17. 10. 2026:** F3.1–F3.3 a F3.5 jsou implementované ve větvi `fix/f0-rbac-tenant-isolation` a nejsou nasazené.
> - Nezařazená route je blokovaná i v zóně admin (upřesnění oproti F3.1).
> - F3.4 (podepsaná IP z gateway) a F3.6 (vazba zařízení) zůstávají otevřené.

| ID | Úkol | Hotovo, když | Testy |
|---|---|---|---|
| F3.1 | `app/core/exposure.py`: tabulka (metoda, šablona) → zóny, default `admin` | Všech 113 rout je zařazeno | `test_route_exposure.py`: žádná nezařazená route; množina G se rovná schválenému seznamu |
| F3.2 | Middleware `exposure_guard` (nejvnější), zóna z `NC_ZONE` procesu; mimo zónu 404 | `/admin/*` v instanci gateway vrací 404 ještě před autentizací | test na každou zónu × route |
| F3.3 | JWT: `iss`, `aud` podle zóny, `iat`, validace algoritmu, access 10 min. Instance přijímá jen svůj `aud`. Superadmin login jen v zóně admin. | Token `nc-web` v instanci desktop vrací 401 | testy `aud` |
| F3.4 | **Samostatná fáze, až po návrhu Gateway.** `X-NC-Client-IP` a HMAC `X-NC-Gateway-Sig` v instanci gateway (jen audit a rate limit). Navazuje na `TrustedProxyMiddleware` (SA-05, hotovo). Instance gateway přestane číst `X-Forwarded-For` a IP převezme jen z podepsané hlavičky na gateway socketu. | Požadavek bez platného HMAC v zóně gateway vrací 401; podvržené `X-NC-Client-IP` bez podpisu se ignoruje | test |
| F3.5 | Generátor `gateway/allowlist.json` z `exposure.py` | Allowlist neobsahuje `/admin`, `/metrics`, `/health/internal` | test generátoru |
| F3.6 | Vazba zařízení ↔ firma v zóně desktop (příprava, aktivní až v F7) | flag `NC_DEVICE_BINDING` | test |

**Kompatibilita:** v `APP_ENV=development` běží jedna instance se zónou `dev`, ve které jsou dostupné všechny routy. Lokální vývoj se tím nemění.

---

## F4 – Gateway/BFF a webové rozhraní

| ID | Úkol | Hotovo, když | Testy |
|---|---|---|---|
| F4.1 | Nový adresář `gateway/` (D-02): login, logout, session, CSRF, allowlist proxy, limity těla, odstraňování hlaviček, rate limit, bezpečnostní události | Gateway nepustí route mimo allowlist (404) | unit + integrační proti core v testovacím režimu |
| F4.2 | Session store: Redis na edge, AES-GCM, idle 30 min, absolutně 12 h, rotace `sid` | Cookie `__Host-nc_sid` HttpOnly, Secure, SameSite=Strict | testy cookies, expirace, rotace |
| F4.3 | CSRF: synchronizer token + kontrola Origin | Mutace bez tokenu vrací 403 | testy CSRF |
| F4.4 | Web: odstranit `tokenStorage` (localStorage), `apiClient` → `/bff/api`, přidat tlačítko pro odhlášení, SSE přes BFF (cookie) | V localStorage ani sessionStorage nejsou žádné tokeny | e2e (Playwright): login, práce, logout, stream |
| F4.5 | CSP pro SPA (SECURITY_ARCHITECTURE 4.7), nginx edge s hlavičkami v include (SA-34), `server_tokens off` | securityheaders.com: A; CSP bez `unsafe-*` | test hlaviček |
| F4.6 | **SA-16 / D-03:** streamovací endpointy `/files/*` v core, `previewUrl`/`downloadUrl` na ně (tvar polí beze změny), audit stahování exportů | Žádná odpověď API neobsahuje URL MinIO | test: grep odpovědí na `X-Amz-` / `:9000` |
| F4.7 | AI pipeline: obrázky Anthropic API inline (base64) místo URL | Analýza funguje s MinIO jen na loopbacku | integrační test s mock providerem |
| F4.8 | Odstranit `web/src/pages/Admin*` a admin routy z webu (D-11) | Web nemá admin sekci | – |

**Exit F4:** web funguje přes gateway; útok XSS nemá token, který by mohl ukrást (ověří pentest F9.5).

---

## F5 – MFA a správa sessions

| ID | Úkol | Hotovo, když | Testy |
|---|---|---|---|
| F5.1 | TOTP v core: `/auth/mfa/totp` (enroll, verify, disable s re-auth), šifrovaný seed, recovery kódy jako hash | Uživatel aktivuje a deaktivuje MFA | unit + e2e |
| F5.2 | `POST /auth/login/start` + `/auth/login/mfa`; `/auth/login` beze změny | Uživatel s MFA se přes gateway bez TOTP nepřihlásí | testy obou cest |
| F5.3 | Politika: MFA povinné pro `manager` a `superadmin` (konfigurovatelné) | Manažer bez MFA je po loginu přesměrován na enrollment, API vrací `mfaEnrollmentRequired` | test |
| F5.4 | Web: přehled a revokace vlastních sessions (`/auth/sessions`), změna hesla | Revokace z UI ukončí jinou session | e2e |
| F5.5 | Throttle MFA: 5 pokusů na ticket, 20 za hodinu na účet | 6. pokus vrací 429 | test |
| F5.6 | Obnova hesla (jen pokud D-05 = ano): SMTP, token 30 min, revokace sessions | Reset funguje; odpověď vždy 202 | testy + test enumerace |

---

## F6 – Infrastruktura Hetzner (bez Dockeru)

> **Stav 17. 10. 2026:** F6.1–F6.3 a F6.5 jsou připravené v [`deploy/linux/`](../../deploy/linux/README.md) a nejsou nasazené.
> - Pilot běží na jednom serveru (varianta B), cílová produkce na dvou (varianta A).
> - Konfigurace ověřuje CI job `deploy-linux-config`.
> - Zbývá provisioning skript F6.2 (kroky jsou zatím ručně v README), F6.4 (reconciler peerů), F6.6 (`deploy.sh`) a F6.7 (LUKS).

| ID | Úkol | Hotovo, když | Testy |
|---|---|---|---|
| F6.1 | `deploy/linux/`: systemd jednotky (`nc-api@.service`, `nc-worker`, `nc-gateway`) se sandboxingem (SECURITY_ARCHITECTURE 8.1) | `systemd-analyze security nc-api@gateway` < 3.0 | review + skript |
| F6.2 | Provisioning skript (idempotentní): uživatelé, PostgreSQL 16 (role `nc_owner`/`nc_app`/`nc_admin`, `scram-sha-256`, jen socket), Redis (ACL users, `requirepass`, bind loopback), MinIO (systemd, loopback, KMS, uživatel s policy jen na bucket, **SA-33**), nginx, certbot | Čistý Ubuntu 24.04 → běžící stack | smoke test |
| F6.3 | WireGuard `wg-nc` a `wg-nc-admin` + nftables + Hetzner Cloud Firewall podle WG_NETWORK_DESIGN | Scénáře N1–N12 projdou | N1–N12 |
| F6.4 | Reconciler desktopových peerů (DB → `wg set`), vzor NovuServer `modules/netpeers` | Přidání a revokace peeru se projeví do 60 s | N8 |
| F6.5 | Secrets: `/etc/novuconstruct/*.env` 0640 + `LoadCredential`, generátor secrets, šablona `EnvironmentFile` (místo `.env.production.example`, **SA-37**) | Žádný secret v repu, unit souboru ani logu | `git grep` + kontrola journald |
| F6.6 | `deploy.sh <tag>`: ověření tagu, záloha, `alembic upgrade head` (`nc_owner`), postupný restart, smoke test všech zón, rollback kódu | Deploy a rollback ověřené na stagingu | test deploye |
| F6.7 | LUKS na datovém volume core | Data PostgreSQL a MinIO jsou na šifrovaném volume | kontrola `lsblk`/`cryptsetup status` |

---

## F7 – Desktop přes WireGuard

| ID | Úkol | Hotovo, když | Testy |
|---|---|---|---|
| F7.1 | Core: tabulka `devices`, `POST /devices/enroll`, `GET/POST/DELETE /admin/devices`, schválení s MFA | Enrollment a revokace fungují | testy API + N8 |
| F7.2 | Desktop-qt: generování WG klíče, enrollment UI, WG tunel (vestavěný, vzor NovuHub `WireGuardTunnelBackend`/NovuAdmin), base URL pevně `10.50.0.1:8210` | Desktop bez WG se k API nepřipojí | e2e na Windows |
| F7.3 | **SA-29:** tokeny v Windows Credential Manageru (QtKeychain), zákaz http mimo WG | V registru nejsou tokeny | kontrola registru |
| F7.4 | Aktivovat `NC_DEVICE_BINDING` (firma zařízení = firma uživatele) | Uživatel firmy B na zařízení firmy A dostane 403 | test |

---

## F8 – Modul NovuConstruct v NovuAdminu

Implementace probíhá v repozitáři NovuAdmin. Zde je jen kontrakt (SECURITY_ARCHITECTURE kap. 7).

| ID | Úkol (v tomto repu) | Hotovo, když | Testy |
|---|---|---|---|
| F8.1 | Nová admin API: sessions uživatele, filtrovaný audit, system overview, revoke-all-web-sessions | Endpointy v zóně A, security-critical audit | API testy |
| F8.2 | Kontrakt API (OpenAPI výřez jen pro zónu admin) jako artefakt pro NovuAdmin | Generovaný soubor v `docs/security/` | CI generuje a porovná |
| F8.3 | Admin peer onboarding runbook (`wg-nc-admin`) | Runbook ověřený na stagingu | N9 |
| F8.4 | Volitelně `/org/users` pro manažery (D-10) | Scoped na firmu, matice rolí | cross-tenant testy |

---

## F9 – Provoz, ověření, go-live

| ID | Úkol | Hotovo, když | Testy |
|---|---|---|---|
| F9.1 | Zálohy: pgBackRest (WAL, PITR) + restic na Hetzner Storage Box, `umask 077`, připnutý host key, šifrování (**SA-31**). Opravit `ops/cleanup_audit_logs.sh` (**SA-32**). | Noční záloha + alert při selhání | kontrola posledního snapshotu |
| F9.2 | **Zkouška obnovy** na čistý server, protokol do `docs/` (B6) | RTO ≤ 4 h, RPO ≤ 15 min dosaženo a zdokumentováno | drill |
| F9.3 | Monitoring a alerty (SECURITY_ARCHITECTURE 8.5), externí uptime na `/bff/health` | Testovací alert dorazí | fire-drill |
| F9.4 | Staging acceptance podle `docs/STAGING_ACCEPTANCE.md`, rozšířený o N1–N12 | Vyplněný protokol | – |
| F9.5 | **Nezávislý penetrační test** (externí nebo interní red team): gateway, IDOR, auth, WG | Žádný otevřený Critical ani High | report |
| F9.6 | Incident runbooky: kompromitace gateway, ztráta zařízení, únik secretu, rotace JWT klíče | Runbooky v `docs/`, jeden z nich nacvičený | tabletop |
| F9.7 | Release tag a go-live checklist | Podepsaný tag, schválení vlastníkem | – |

---

## Rizika plánu

| Riziko | Dopad | Mitigace |
|---|---|---|
| Web UI pro uživatele je z velké části nedokončené (B5) | F4 bez obsahu, který by šel otestovat | pilot jen s desktopem; F4 současně s dokončením UI |
| Desktop WG klient (F7) je největší neznámá | posun pilotu | znovu použít WG backend z NovuHubu nebo NovuAdminu (stejná organizace, už existuje) |
| Tři instance API zvýší paměťovou náročnost | větší server | admin instance s 1 workerem; varianta jednoho procesu s `NC_ZONE_PORTS` |
| Změna `aud` a TTL odhlásí stávající uživatele | jednorázové odhlášení | provést při nasazení F3, oznámit předem |
| Kontrakt NovuAdminu závisí na jiném repozitáři | blokace F8 | kontrakt dodat jako soubor (F8.2); NovuAdmin implementuje nezávisle |

## Schvalovací body

1. Rozhodnutí D-01 až D-13 (SECURITY_ARCHITECTURE kap. 9, WG_NETWORK_DESIGN kap. 8).
2. Matice rolí v API_EXPOSURE_MATRIX (sloupec Role).
3. Pořadí fází a minimum pro pilot.
4. Teprve potom začne F0.
