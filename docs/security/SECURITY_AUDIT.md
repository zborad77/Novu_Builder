# NovuConstruct – Security Audit (skutečný stav)

| | |
|---|---|
| **Datum** | 17. 10. 2026 |
| **Rozsah** | `python-backend`, `web`, `desktop-qt`, `novu-mobile` (okrajově), `nginx/`, `docker-compose.yml`, `ops/`, `scripts/`, env šablony |
| **Stav repozitáře** | `master` @ `904ac05` (merge `origin/master` + lokální nepushnutý commit `5b7a278 docs-cleanup`) |
| **Charakter** | Read-only audit. Žádný kód nebyl změněn, nic nebylo nasazeno ani pushnuto. |
| **Navazující dokumenty** | [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md) · [API_EXPOSURE_MATRIX.md](API_EXPOSURE_MATRIX.md) · [WG_NETWORK_DESIGN.md](WG_NETWORK_DESIGN.md) · [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) |

> **Tento dokument netvrdí, že je systém bezpečný.** Popisuje, co bylo ověřeno, co bylo nalezeno a co ověřeno nebylo (kapitola 7).

## Metodika a značení

| Značka | Význam |
|---|---|
| **[RUN]** | Ověřeno spuštěním: lokálně, proti kopii vývojové DB nebo v simulované produkční konfiguraci. |
| **[READ]** | Ověřeno čtením kódu, nespuštěno. |
| **[SUSP]** | Podezření, které je potřeba potvrdit za běhu. |

| Závažnost | Kritérium |
|---|---|
| **Critical** | Převzetí platformy nebo přístup k datům cizí firmy bez zvláštních předpokladů |
| **High** | Únik citlivých dat nebo obejití bezpečnostní kontroly s reálným scénářem |
| **Medium** | Oslabení obrany, DoS nebo chyba, která zesiluje jiné nálezy |
| **Low / Info** | Hardening, hygiena, dokumentace |

Čísla řádků odpovídají `904ac05`.

---

## 1. Souhrn

- **1 Critical:** manažer libovolné firmy může převzít účet superadmina a tím celou platformu (SA-01). Ověřeno end-to-end.
- **3 High:** únik osobních údajů klientů cizí firmy (SA-02), obejití IP rate limitu na přihlášení (SA-03), změna hesla přes admin PATCH bez revokace sessions (SA-04).
- **~20 Medium**, zbytek Low/Info.
- **Síťová izolace v backendu neexistuje.** Backend nemá žádný koncept síťových zón. Vše za nginx je dostupné z internetu a odděluje to jen autentizace. Cílovou architekturu popisuje [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md).
- **Silné stránky:**
  - role, firma a `is_active` se načítají z DB při každém požadavku,
  - refresh token se rotuje,
  - produkční validátory konfigurace odmítnou slabé secrets,
  - SQL injection ani SSRF nenalezeny,
  - validace uploadů je kvalitní,
  - impersonace je auditovaná fail-closed.

### Stav oprav (aktualizováno 17. 10. 2026)

| Nález | Stav | Kde |
|---|---|---|
| SA-01, SA-04 | Opraveno ve větvi `fix/f0-rbac-tenant-isolation`, nevydáno | `app/core/rbac.py`, `app/api/routes/admin.py`, migrace `20261017_0057`, [RBAC_ROLE_MATRIX.md](RBAC_ROLE_MATRIX.md) |
| SA-02 | Opraveno, navíc stejná chyba u `POST /offer-requests` | `project_service.update_project`, `offer_processing/service.py` |
| SA-03 | Opraveno | `core/limiter.py` (`client_ip_rate_limit_key`) |
| B2 | Fail-open jen s explicitním `AUTH_THROTTLE_DEV_FAIL_OPEN=true` v developmentu | `core/config.py`, `api/routes/auth.py` |
| SA-05 | Opraveno pro současné prostředí: IP klienta jen od `TRUSTED_PROXY_IPS`, uvicorn `--no-proxy-headers`, rate limit v Redisu (fail-closed 503). Podepsaná identita z Gateway je samostatná fáze. | `core/client_ip.py`, `core/limiter.py`, `docker-compose.yml`, `DEPLOY.md` |
| SA-06 | Opraveno podle varianty A, včetně soft delete fotek s obnovou | [RBAC_ROLE_MATRIX.md](RBAC_ROLE_MATRIX.md) §2.5, migrace `20261017_0058` |
| B1 | Obnoveno všech 51 dokumentů z `origin/master` | |
| Ostatní | Otevřené, viz [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | |

---

## 2. Release blokery z předchozího auditu

Tyto položky blokují nasazení bez ohledu na novou architekturu.

| ID | Blokér | Důkaz | Doporučení |
|---|---|---|---|
| **B1** | Commit `5b7a278 docs-cleanup` maže ~50 dokumentů, které na `origin/master` existují, včetně `BACKUP_RESTORE.md`, `README.md`, `ARCHITECTURE.md`, `RUNBOOK.md` a `OPERATIONS.md`. | Test `tests/test_config_production_hardening.py:901` padá na `FileNotFoundError`. Na smazané soubory dál odkazují `DEPLOY.md:236`, `RELEASE_CHECKLIST.md:134`, `docs/STAGING_ACCEPTANCE.md:168`, `CLAUDE.md:21,75`, `ops/alerting/alerts.yml` a `scripts/generate_{pdf,docx}.py`. | Commit nepushovat v tomto stavu. Obnovit `BACKUP_RESTORE.md` a referencované soubory, nebo opravit odkazy i test. |
| **B2** | Stejný commit mění `app/api/routes/auth.py`: při `APP_ENV=development` a nedostupném Redisu se přeskočí throttle přihlášení (fail-open). | `auth.py:188-195, 247-255, 267-285` [RUN]. Padají 3 testy `test_r08_account_throttle`. Odporuje pravidlu „no fail-open“ z `docs/NOVU_CONSTITUTION.md`. | Změnu vrátit, nebo ji podmínit explicitním flagem (viz SA-13). |
| **B3** | Build webu padá. | `web/tsconfig.node.json` odkazuje na neexistující `vite.config.placeholder.ts` (TS18003). `tsc -b` bez `noEmit` generuje `.js` soubory do `src/`. Lokálně chybí `fflate` (vyřeší `npm ci`). | Opravit `include` na `vite.config.ts` a doplnit `noEmit`. |
| **B4** | Podepsané URL z MinIO nejsou dosažitelné pro klienty ani pro AI providera. | Viz SA-16. | Řeší architektura (kap. 5 v SECURITY_ARCHITECTURE). |
| **B5** | Frontendová administrace neexistuje. Všech 5 admin stránek je prázdná kostra. Prázdné jsou i seznam zakázek, katalogy, nastavení a reset hesla. | `web/src/pages/Admin*.tsx`, `AdminLayout.tsx` | Admin přesune do NovuAdminu (viz SECURITY_ARCHITECTURE kap. 7). Web UI pro uživatele dokončit. |
| **B6** | Verze v0.8.6 není vydaná: nemá tag, protokol stagingu je prázdný a chybí záznam o zkoušce obnovy. | `CHANGELOG.md:5`, `docs/PROJECT_STATE.md` | Dokončit podle `docs/STAGING_ACCEPTANCE.md`. |
| **B7** | Web se volá s fallbackem `'/api'`, backend ale běží na `/api/v1`. | `web/src/shared/lib/apiClient.ts:81` | V BFF architektuře zaniká, base URL bude vždy gateway. |

---

## 3. Nálezy – backend

### SA-01 · CRITICAL · Manažer firmy převezme superadmina a ostatní firmy [RUN]

**Kde:**
- `python-backend/alembic/versions/20260326_0018_add_role_permissions.py:23-31` seeduje `("manager","admin:read")` a `("manager","admin:write")`.
- `python-backend/app/api/deps.py:250-300`: `require_admin_capability` povolí přístup podle tabulky `role_permissions`. Nijak neomezuje na firmu volajícího.
- `python-backend/app/api/routes/admin.py`:
  - `create_company` :70,
  - `patch_company` :105,
  - `create_user` :153 (libovolné `organizationId` i `role`),
  - `patch_user` :196,
  - `reset_user_password` :222-241 (načte libovolného uživatele přes `session.get(User, user_id)`, superadmina nevylučuje).
- `python-backend/app/schemas/company.py:53-66`: `role` je volný řetězec.

**Reprodukce na kopii DB:**
1. Manažer `demo@novu.local` zavolá `POST /api/v1/admin/users/usr_novu_admin/reset-password` → 204.
2. Přihlášení jako superadmin s novým heslem → 200, `isSuperAdmin=true`.
3. Alternativně `PATCH /admin/users/{vlastní id} {"role":"superadmin"}` → 200. Řetězec role `superadmin` pak přes `role_permissions` získá `admin:jobs` a `admin:impersonate` a projde i `require_manager` (`deps.py:335`).

**Dopad:** úplné převzetí platformy a přístup ke všem firmám. Testy (`tests/test_admin_phase2.py`) cestu přes manažera vůbec nepokrývají.

**Řešení:**
1. Nová migrace odstraní řádky `manager` z `role_permissions`.
2. Pokud volající není superadmin, každou admin akci omezit na `current_user.organizationId`, nebo admin API pro ne-superadminy úplně zakázat.
3. Zakázat jakoukoli operaci, jejímž cílem je superadmin, pokud ji nevolá superadmin.
4. Zakázat změnu vlastní role.
5. Validovat `role` proti enumu.
6. Přidat regresní testy pro manažera, technika a cizí firmu.

### SA-02 · HIGH · Únik PII klientů cizí firmy přes `PATCH /cases/{id}` `clientId` [READ]

**Kde:** `app/services/project_service.py:625-651` (`update_project`) mapuje `clientId` přímo na `client_id`. `create_project` (:427-428) přitom `client_belongs_to_org` volá.

**Scénář:**
1. Manažer firmy A nastaví na své zakázce `clientId` klienta firmy B. ID ve tvaru `cli_1` jsou odhadnutelná, viz SA-28.
2. `GET /cases/{id}` vrátí jméno, firmu, e-mail a telefon klienta (`project_service.py:229-237`, `project_repository.py:108`).
3. Údaje se propíší i do exportů (PDF, DOCX).

**Řešení:** v `update_project` volat `client_belongs_to_org` a přidat regresní test.

### SA-03 · HIGH · Podvržená hlavička Authorization obejde IP rate limit loginu [RUN]

**Kde:** `app/core/limiter.py:19-57`. `_rate_limit_key` bere `org`/`sub` z **neověřeného** JWT. Na `/auth/login`, `/auth/refresh` a `/auth/logout` hlavičku nic předem neověřuje.

**Měření:**
- 12 pokusů bez hlavičky: 429 po desátém.
- 12 pokusů s náhodným podvrženým `org`: 429 se nikdy neobjevil.

**Dopad:** password spraying bez IP limitu. Zůstává jen per-account throttle v Redisu.

**Řešení:** pro `/auth/*` použít klíč podle IP (samostatná `key_func`), nebo před použitím claimů ověřit podpis.

### SA-04 · HIGH · `PATCH /admin/users/{id}` mění heslo bez kontroly síly a bez revokace sessions [RUN]

**Kde:** `app/services/company_service.py:203-217`, `admin.py:205-214`.

- Nastavení hesla `"a"` vrátí 200.
- `token_version` se nezvýší a sessions se nerevokují.
- Audit vynechá `password`, takže změna hesla v auditu není vidět.

**Řešení:** změnu hesla přes PATCH vést stejnou cestou jako `reset-password`:
- `enforce_password_strength`,
- `invalidate_user_token_state` a `revoke_all_user_sessions`,
- security-critical audit s `password_changed: true`.

### SA-05 · MEDIUM · Rate limit je per proces a vidí IP proxy [READ/SUSP]

**Kde:**
- `app/core/limiter.py:83`: `Limiter(...)` nemá `storage_uri`, čítače jsou v paměti každého workeru.
- `python-backend/docker-entrypoint.sh:10` spouští uvicorn bez `--proxy-headers --forwarded-allow-ips`.
- `docker-compose.yml` má `FORWARDED_ALLOW_IPS: "*"`.

**Dopad:**
- N workerů znamená N× vyšší limit.
- Všichni anonymní klienti mohou sdílet jeden bucket IP adresy proxy, což umožňuje DoS loginu.
- Audit IP adres a allowlist `/metrics` vidí proxy místo klienta.
- Uvnitř compose sítě jde IP podvrhnout.

**Řešení:**
- `storage_uri=REDIS_URL`,
- uvicorn s `--proxy-headers --forwarded-allow-ips=<přesná IP proxy>`.

### SA-06 · MEDIUM · Chybějící kontroly rolí na zápisech v rámci firmy [READ]

Tyto endpointy kontrolují jen firmu, ne roli, takže je může volat i technik:

| Endpoint | Kde |
|---|---|
| `PATCH /offer-requests/{id}` (schválení nabídky) | `offer_requests.py:209` |
| `POST /pricebooks` | `pricebooks.py:76` |
| `PATCH /suppliers/{id}` | `suppliers.py` |
| `PATCH /material-catalog/{id}` | `material_catalog.py` |
| `PUT /work-catalog/work-types/{code}/settings` | `work_catalog.py:254` |
| `POST /analysis-jobs/{id}/cancel` | `analysis_jobs.py` |
| `POST /cases/{id}/measurements` | `measurements.py` |
| `POST`/`DELETE /markers` | `markers.py` |
| `GET /exports/{id}` | `exports.py` |

Navíc `POST /offer-requests` přijímá od klienta `auto_review_bypass` a `auto_send` (`app/schemas/offer_requests.py:27-28`). Zatím je nic nespotřebovává, jde o latentní bypass.

**Řešení:** doplnit `require_manager` podle business pravidel a bypass flagy přijímat jen od manažera. Nejprve je potřeba sepsat matici rolí (kap. 6 v SECURITY_ARCHITECTURE).

### SA-07 · MEDIUM · K materiálu lze připojit dodavatele cizí firmy [READ]

**Kde:** `app/repositories/material_catalog_repository.py:61-67` uloží `defaultSupplierId` bez kontroly. `get_supplier_name` (:55-59) používá `session.get(Supplier, id)` bez filtru firmy, takže v odpovědi vrátí jméno cizího dodavatele. Rozdíl mezi chybou FK a úspěchem navíc prozradí, jestli ID existuje.

**Řešení:** před zápisem ověřit `get_supplier_in_org`.

### SA-08 · MEDIUM · `referenceImageId` u měření není vázané na zakázku ani firmu; zámek jde obejít [READ]

**Kde:** `app/api/routes/measurements.py:70-73, 111-113` → `app/repositories/analysis_repository.py:779-780`. Dále `POST /cases/{id}/measurements` nekontroluje `_SELECTION_LOCKED`, ačkoli `PATCH` a `confirm` ano.

**Řešení:**
- validovat foto v rámci zakázky,
- aplikovat kontrolu zámku,
- odlišit 404 od 500 (dnes slouží jako orákulum existence ID).

### SA-09 · MEDIUM (dev) / N/A (prod) · Path traversal v `/mock-storage` [READ]

**Kde:** `app/api/routes/storage.py:36-51` bere ID zakázky z `Path(file_path).parts[1]` ještě **před** normalizací cesty.

**Příklad:** `GET /mock-storage/projects/<vlastní>/../<cizí>/preview/IMG_0001.jpg`.

V produkci se route nemontuje (`config.py:1222` odmítne lokální storage). Riziko je na vývojových a pilotních instancích.

**Řešení:** odmítat segmenty `..` a ID zakázky brát z normalizované cesty.

### SA-10 · MEDIUM · Opakované použití refresh tokenu se detekuje, ale session se nezruší [READ]

**Kde:** `app/services/auth_service.py:375-387`. Starý refresh token vrátí `revoked_or_reused_token`, session a nejnovější refresh token ale zůstanou platné až 30 dní.

**Řešení:** při detekci reuse revokovat celou session (rodinu tokenů).

### SA-11 · MEDIUM · Dekódování uploadu blokuje event loop (DoS) [READ]

**Kde:** `app/storage/local_photo_storage.py:367-380`: async validace volá synchronně `img.load()` a `verify()`. `app/api/routes/images.py:112-141` iteruje přes všechny soubory v requestu.

Jeden 25MB multipart request může obsahovat stovky malých, silně komprimovaných PNG s velkými rozměry. Každý se dekóduje do paměti až do ~89 Mpx, tedy ~270 MB RGB.

**Řešení:**
- `asyncio.to_thread`,
- nižší `Image.MAX_IMAGE_PIXELS`,
- kontrola rozměrů před `load()`,
- limit počtu souborů v jednom requestu.

### SA-12 · MEDIUM · SSE: bez re-autorizace během streamu a bez limitů spojení [READ]

**Kde:** `app/api/routes/case_events.py`, `app/api/routes/offer_events.py`, `app/core/redis_client.py:122`.

**Pozitivní:**
- token jde v hlavičce `Authorization`, ne v URL,
- firma se ověřuje před subscribe,
- jméno kanálu skládá server.

**Nedostatky:**
- logout, reset hesla ani deaktivace neukončí otevřený stream,
- neexistuje limit spojení na uživatele ani globálně,
- každý stream otevírá pubsub spojení ze sdíleného neomezeného poolu, který používá i fronta a auth cache.

**Řešení:**
- periodicky (každých N heartbeatů) znovu ověřit `token_version` a session,
- zavést limity spojení na uživatele a globálně,
- dát SSE vlastní Redis pool.

### SA-13 · MEDIUM · `APP_ENV` má výchozí hodnotu `development` [RUN]

**Kde:** `app/core/config.py:354`, `app/core/limiter.py:15`.

Nasazení, kterému chybí `APP_ENV`, dostane všechny vývojové defaulty:
- JWT secret `change-me-in-production`,
- `create_all` schématu,
- `/mock-storage`,
- po commitu `5b7a278` i fail-open throttle loginu (B2).

**Řešení:** `APP_ENV` povinné bez defaultu. Jakákoli fail-open výjimka jen přes explicitní flag (např. `AUTH_THROTTLE_DEV_FAIL_OPEN=true`) a zákaz takového flagu ve strict prostředích.

### SA-14 · MEDIUM · Neúplný audit trail [READ]

**Kde:** `app/core/audit.py:369-420, 518`; `admin.py:213`; `app/models/domain.py:700`.

- Vytvoření a změny firem a uživatelů a retry jobů se zapisují přes provozní, fail-open `write_audit_log`.
- GET požadavky se neauditují, takže admin čtení napříč firmami (uživatelé, joby, logy, audit) nezanechá stopu.
- Neúspěšná přihlášení a refreshe jdou jen do logů a metrik, ne do `audit_logs`.
- Stahování exportů se neaudituje [SUSP].
- `AuditLog` je v kódu označen jako „immutable“, na úrovni DB to ale nic nevynucuje.

**Řešení:**
- admin zápisy přepnout na security-critical,
- auditovat admin GET, neúspěšné loginy a stahování exportů,
- `REVOKE UPDATE, DELETE ON audit_logs` pro aplikační roli.

### SA-15 · MEDIUM · Nedostatky impersonace [READ]

**Kde:** `admin.py:622-690`; `web/src/app/providers/ImpersonationProvider.tsx:24-36`.

**Pozitivní:**
- platnost 15 minut,
- superadmina nelze impersonovat,
- audit fail-closed,
- admin routy impersonovaný token odmítnou.

**Nedostatky:**
- token nemá `sid`, takže ho nelze vylistovat ani revokovat,
- stav impersonátora (aktivní, superadmin) se při použití tokenu znovu neověřuje,
- impersonovaný token může mazat sessions cílového uživatele přes `DELETE /auth/sessions/*`,
- web impersonuje jen na klientovi a backend nevolá, což je zavádějící,
- v kombinaci se SA-01 může povýšený manažer impersonovat kohokoli kromě superadmina.

### SA-16 · MEDIUM · Nedosažitelné podepsané URL; AI provider dostává privátní URL [READ]

**Kde:**
- `app/storage/s3_photo_storage.py:59-61, 92-103`: podepisuje stejným `S3_ENDPOINT_URL`, jaký používá backend interně (`http://minio:9000`).
- Tyto URL se posílají Anthropic API: `app/worker/offer_runner.py:192`, `app/ai/analysis_service.py:70`. Obrázky se tam tiše zahodí.

**Riziko:** operátor „opraví“ problém tím, že MinIO vystaví do internetu.

**Pozitivní:**
- bucket je privátní,
- TTL je nejvýše 3600 s,
- URL platí pro jeden konkrétní klíč.

**Řešení:** viz SECURITY_ARCHITECTURE kap. 5. Médiím pro web slouží gateway, AI dostává obsah inline (base64), ne URL.

### SA-17 · LOW · `/openapi.json` je v produkci veřejné [RUN]

**Kde:** `app/main.py:348-358`. `/docs` a `/redoc` jsou vypnuté, `openapi_url` ale ne. Simulovaná produkce vrací 200 a 170 KB schéma.

**Řešení:** `openapi_url=None` mimo debug.

### SA-18 · LOW · Starý access token platí i po refreshi [READ]

**Kde:** `auth_service.py:348-352`. Kontroluje se jen existence session, ne shoda `session.access_jti == jti`. Předchozí access token tak platí až 60 minut.

### SA-19 · LOW · DoS zablokováním účtu [READ]

**Kde:** `app/services/account_limiter.py:113-114`. Po 10 neúspěších za 15 minut vrací 429 i pro správné heslo, takže kdokoli může zablokovat libovolný známý e-mail.

**Řešení:** klíč IP + účet, progresivní zpoždění nebo CAPTCHA na gateway.

### SA-20 · LOW · JWT bez `iss`/`aud`/`iat`; algoritmus se nevaliduje [READ]

**Kde:** `auth_service.py`, `config.py:754-780`. HS256 s validovaným secretem (≥32 znaků, ne placeholder) je v pořádku. Chybějící `aud` ale znemožňuje oddělit tokeny podle kanálu (web, desktop, admin), což cílová architektura potřebuje.

### SA-21 · LOW · Nízká entropie ID [READ]

Většina ID je `uuid4().hex[:8]`, tedy 32 bitů: zakázky, fotky, firmy, uživatelé, exporty i joby. Seed ID jsou čitelná (`cli_1`, `sup_dek`, `usr_novu_admin`). Zesiluje to SA-02, SA-07 a SA-08.

**Řešení:** nová ID generovat jako plné UUID. Stávající ID ponechat beze změny API kontraktu.

### SA-22 · LOW · Originály fotek si ponechávají EXIF a GPS [READ]

Originály se ukládají bajt po bajtu. Náhledy i AI varianty jsou bez EXIF, originál ale vidí všichni uživatelé firmy, dostává ho AI provider a je i v ZIP exportu (`app/services/export_service.py:793-801`).

**Řešení:** odstranit metadata při příjmu, nebo je uložit odděleně.

### SA-23 · LOW · Další neověřená vnořená ID a neomezené vstupy [READ]

- `analysisJobId` ve vision detekcích (`work_catalog_service.py:2257`).
- `polygon` v `patch_analysis_selection` (`analysis_jobs.py:150, 181-187`, `body: dict`) není validovaný ani velikostně omezený.
- Seznamy `photo_ids` nemají limit.

### SA-24 · LOW · Konfigurační hardening [READ]

| Kde | Nedostatek |
|---|---|
| `config.py:1300-1342` | Validátor CORS neodmítá `*`, i když `allow_credentials=True`. |
| `config.py:493` | `REQUIRE_HTTPS` je ve výchozím stavu `False` a ve strict prostředí se nevynucuje. |
| — | Chybí `TrustedHostMiddleware`; nginx má `server_name _`. |
| `main.py:335-340` | Sentry nemá `before_send` a lokální proměnné ve stack traces mohou obsahovat secrets [SUSP]. |
| `GET /api/v1/` | Vrací `APP_ENV`. |
| `/health`, `/ready` | Spouští kontroly DB, Redisu a úložiště bez rate limitu. |

### SA-25 · INFO · Seed hesla jsou v repozitáři v plaintextu [READ]

**Kde:**
- `app/db/bootstrap.py:65-83`,
- `backend.bat:33`,
- `scripts/run-operational-load-rehearsal.py:250`,
- `python-backend/scripts/test_storage_persistence.py:52`.

Hodnoty zde záměrně neuvádíme.

**Mitigace:** `DB_SEED_ON_STARTUP` je mimo development zakázané (`config.py:722-729`).

**Řešení:** dev hesla generovat náhodně a ze skriptů je odstranit.

### SA-26 · INFO · Backend nemá koncept síťových zón [READ]

**Kde:** `app/main.py`, `nginx/nginx.conf`.

Backend nerozlišuje veřejnou, VPN a admin zónu. Jediná síťová hranice je allowlist RFC1918 v nginx pro `/metrics` a `/health/internal`. Za load balancerem v privátní síti by ale „interní“ byl každý klient.

**Řešení:** zónový guard podle vzoru NovuServeru. Viz SECURITY_ARCHITECTURE kap. 3.

---

## 4. Nálezy – klienti

### SA-27 · MEDIUM · Web drží tokeny v localStorage a odhlášení session neruší [READ]

**Kde:** `web/src/shared/lib/apiClient.ts:25-71` (`nb_access_token` na 60 min, `nb_refresh_token` na 30 dní); `web/src/app/providers/AuthProvider.tsx:49-52`.

- Jakýkoli skript na stránce ukradne 30denní session. XSS sinky nalezeny nebyly (žádné `dangerouslySetInnerHTML`, `innerHTML` ani `eval`), ochrana tak stojí jen na React escapování.
- Odhlášení jen smaže localStorage a nikdy nezavolá `POST /auth/logout`. V UI navíc chybí tlačítko pro odhlášení.

**Řešení:** BFF s HttpOnly cookies (SECURITY_ARCHITECTURE kap. 4).

### SA-28 · MEDIUM · SPA nemá CSP ani definici hostingu [READ]

**Kde:** `web/index.html`, `nginx/nginx.conf:21`.

- `web/index.html` nemá CSP.
- nginx má `default-src 'none'`, což sedí pro API, ale SPA by tím rozbilo.
- Web nemá žádnou deployment cestu.

### SA-29 · MEDIUM · Desktop drží tokeny v plaintextu a povoluje http [READ]

**Tokeny:** `desktop-qt/src/state/sessionstate.cpp:37-49` a `mainwindow.cpp:81` ukládají access i refresh token do QSettings, na Windows tedy do registru HKCU.

**HTTP:** výchozí URL je `http://localhost:8000/api/v1` (`mainwindow.cpp:38`) a `serversetupdialog.cpp:52` nabízí příklad `http://192.168.x`.

**TLS:** výchozí ověřování certifikátů je zachované (žádné `ignoreSslErrors`). Pinning chybí.

**Řešení:**
- tokeny do Windows Credential Manageru nebo DPAPI (QtKeychain),
- v cílovém stavu provoz jen přes WireGuard a odmítnutí jakékoli jiné URL.

### SA-30 · LOW · Mobilní klient povoluje http [READ]

**Kde:** `novu-mobile/src/services/api.ts:33`. Tokeny jsou v `expo-secure-store` a odhlášení session ruší (OK). Projekt je zmražený.

---

## 5. Nálezy – deployment a provoz

| ID | Sev. | Nález | Kde | Řešení |
|---|---|---|---|---|
| SA-31 | MEDIUM | Zálohy nejsou šifrované: plaintext pgdump a tar s hashi hesel a PII. Skript nenastavuje `umask` ani `chmod`. Offsite rsync používá `StrictHostKeyChecking=accept-new`. | `scripts/backup.sh:264-300, 468-472`; `ops/backup.sh:44-58` | `umask 077`, šifrování (restic/age) před odesláním, připnutý host key. Restore checksum ověřuje a vyžaduje potvrzení (OK). |
| SA-32 | MEDIUM | Skript retence audit logu nefunguje: chráněné akce mají jiná jména než skutečné (`auth.login`, `admin.impersonate`, …), výchozí DB je špatná, `ROW_COUNT()` v PostgreSQL neexistuje a chyby se umlčují. | `ops/cleanup_audit_logs.sh` | Opravit názvy, DB a počítání řádků; chyby nechat selhat nahlas. |
| SA-33 | MEDIUM | Aplikace používá root credentials MinIO. | `.env.production.example` (`S3_ACCESS_KEY_ID=minioadmin`) | Dedikovaný MinIO uživatel s policy jen na bucket. |
| SA-34 | LOW | nginx v bloku 443 přepíše `add_header`, takže na HTTPS se ztratí X-Frame-Options, nosniff, Referrer-Policy i CSP. Backend je posílá sám, dopad je tedy omezený. | `nginx/nginx.conf:16-21, 46` | Hlavičky do include souboru, `server_tokens off`. |
| SA-35 | LOW | `client_max_body_size 25M` platí globálně. SSE spojení se ukončí po 200 s `proxy_read_timeout` (heartbeat 30 s je v pořádku). | `nginx/nginx.conf:97` | 1M jako default, 25M jen pro upload lokace. |
| SA-36 | INFO | Docker: secrets se dostanou do image (`.dockerignore` nevylučuje `.env.*`), kontejner běží jako root a v runtime image je `gcc`. Cílová platforma Docker nepoužívá. Platí to jen, pokud by se compose dál používal. | `python-backend/.dockerignore`, `python-backend/Dockerfile` | Pro cílovou platformu irelevantní. |
| SA-37 | INFO | Šablona `.env.production.example` má zastaralé `APP_VERSION=0.6.003`. Některé proměnné (SMTP, `OPENAI_API_KEY`, `MAX_UPLOAD_SIZE_MB` …) compose do kontejneru nepředává. | `.env.production.example:29` | Pro systemd nasazení nová šablona `EnvironmentFile`. |

**Kontrola secrets [RUN, grep]:** v trackovaných souborech nebyly nalezeny žádné skutečné klíče ani certifikáty. Výjimkou jsou testovací a CI dummy hodnoty a seed hesla (SA-25).

---

## 6. Co funguje (pozitivní kontroly)

**Autentizace a sessions**
- PyJWT HS256. Strict prostředí odmítne slabý nebo placeholder secret.
- Access token platí 60 minut, refresh 30 dní. Refresh se rotuje.
- Denylist `revoked_tokens` s Redis cache a fallbackem do DB.
- Tabulka `user_sessions`.
- Odhlášení revokuje session i oba JTI.
- Změna hesla i admin reset zvyšují `token_version`, revokují všechny sessions a auditují se fail-closed.
- **Role, firma a `is_active` se načítají z DB při každém požadavku** (`auth_service.py:353-357`). Odebrání role nebo deaktivace platí okamžitě.
- bcrypt hashování, dummy hash proti timing enumeraci, jednotná 401.
- Self-service reset hesla je vypnutý (410).

**Data a vstupy**
- Izolace firem u zakázek, fotek, analýz, exportů, ceníků, dodavatelů, materiálů, položek prací i nabídek jde přes repository a service funkce `*_in_org`.
- SQL injection: žádné. Všechna `text()` používají bound parametry a LIKE je escapovaný.
- SSRF: žádné. Server nestahuje URL zadané uživatelem.
- Upload:
  - obsah se rozpoznává přes Pillow a deklarovaný typ musí odpovídat skutečným bajtům,
  - názvy souborů se kontrolují na traversal,
  - velikost je omezená,
  - decompression bomb se odmítne.

**Provoz a konfigurace**
- `/metrics` je chráněné tokenem přes `compare_digest`. Strict prostředí vypnutí metrik odmítne.
- Globální exception handler vrací generickou 500. `APP_DEBUG` je ve strict prostředí zakázaný.
- Logy mají redakční processor pro tokeny a hesla. Neúspěšný login loguje jen doménu e-mailu.
- Alembic má lineární řetězec 56 revizí s jedním headem `20261003_0056`.
- ruff, mypy i bandit jsou čisté.

---

## 7. Co nebylo ověřeno

**Testy a prostředí**
- Testy se nespouštěly proti PostgreSQL ani Redisu (lokálně nejsou). Běh na SQLite: 1378 passed, 70 failed, 17 errors. Selhání způsobilo hlavně prostředí a B1, B2.
- Nespuštěno: `pip-audit` a `npm audit`, tedy zranitelnosti závislostí.
- CI pro `904ac05` neověřeno (chybí `gh`).

**Za běhu neověřeno**
- runtime chování MinIO presigned URL,
- zálohy a obnova,
- TLS konfigurace na skutečném serveru,
- chování pod zátěží (SA-11, SA-12),
- IDOR v service vrstvě: zkontrolovány všechny route moduly, úplný trace každé service funkce ale proveden nebyl,
- desktop-qt aktuální build: binárka je starší než aktuální zdrojový kód.

**Mimo tento repozitář**
- NovuAdmin, NovuServer: jen identifikace rozhraní, žádný audit.
