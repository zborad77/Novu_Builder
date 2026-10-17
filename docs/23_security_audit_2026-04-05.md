# BEZPEČNOSTNÍ AUDIT — NOVU Builder

**Dokument č.:** 23  
**Datum auditu:** 2026-04-05  
**Rozsah:** Celý backend (`python-backend/app/`) — kompletní kód  
**Metodologie:** Manuální audit kódu, analýza datových toků, útokové scénáře  
**Status dokumentu:** ZÁVAZNÝ — platí pro pilot i produkci

---

## A) CELKOVÝ BEZPEČNOSTNÍ STAV

**PILOT-SAFE s jednou podmínkou (viz P0-1)**

Systém má nadstandardně propracovanou bezpečnostní architekturu — timing protection, fail-closed design, token rotation, multi-layer path traversal ochrana. Jeden kritický nález musí být odstraněn před pilotem.

---

## B) KRITICKÁ RIZIKA — P0 (blokují produkci)

### P0-1 — `.env.production` soubor v repozitáři

**Soubor:** `python-backend/.env.production`

Produkční env soubor je commitnutý v repozitáři. Pokud obsahuje reálné credentials (DATABASE_URL, JWT_SECRET, Redis heslo, API klíče), každý s přístupem k repo vidí produkční secrets.

**Útočný vektor:**

1. Útočník získá přístup k repozitáři (GitHub leak, ex-zaměstnanec, misconfigured repo)
2. Otevře `.env.production` → má DATABASE_URL, JWT_SECRET, Redis credentials
3. Podepíše libovolný JWT token → přístup jako jakýkoliv user
4. Přímý přístup k databázi → dump všech dat

**Dopad:** Kompletní kompromitace produkce.

**Požadovaná akce:**

- Okamžitě ověřit obsah souboru
- Pokud obsahuje reálné secrets → rotovat všechna credentials
- Přidat do `.gitignore`
- Smáznout z git history (`git filter-branch` nebo BFG Repo Cleaner)

---

## C) VYSOKÁ RIZIKA — P1 (blokují škálování / větší klienty)

### P1-1 — Chybějící rate limiting na čtecích endpointech

Autentizovaný uživatel může provádět neomezený počet requestů na:

- `GET /cases`, `GET /cases/{id}`
- `GET /pricebooks`, `GET /suppliers`
- `GET /material-catalog`
- Všechny measurement endpointy

**Útočný vektor:**

1. Útočník získá platný JWT (legitimním přihlášením nebo kompromitací)
2. Spustí paralelní smyčku requestů na `GET /cases` → tisíce requestů/sec
3. Backend a databáze jsou přetíženy → DoS pro ostatní tenanty

**Dopad:** Výpadek služby pro všechny klienty.

**Požadovaná akce:** Přidat `@limiter.limit(settings.rate_limit_read)` (např. `120/minute`) na list endpointy, `60/minute` na detail.

### P1-2 — Seed bootstrap hesla v kódu

**Soubor:** `python-backend/app/db/bootstrap.py` — řádky 231, 260, 275

```python
password_hash=hash_password("NovuAdmin2024!")   # superadmin
password_hash=hash_password("demo1234")          # manager
password_hash=hash_password("tech1234")          # technician
```

Seed guard správně blokuje `DB_SEED_ON_STARTUP=true` mimo `APP_ENV=development`. Neexistuje však mechanismus, který by detekoval, zda seed byl spuštěn a výchozí hesla nebyla změněna.

**Útočný vektor:** Útočník zkusí `NovuAdmin2024!` na superadmin login → pokud seed byl spuštěn a heslo nebylo změněno → plný přístup.

**Požadovaná akce:** Přidat startup check detekující aktivní seed účty s výchozím heslem hashem a zalogovat CRITICAL varování.

---

## D) STŘEDNÍ RIZIKA — P2 (neblokují pilot, opravit do 30 dní)

### P2-1 — ILIKE wildcard injection v admin audit logu

**Soubor:** `python-backend/app/api/routes/admin.py` — řádek 553

```python
if action:
    query = query.where(AuditLog.action.ilike(f"%{action}%"))
```

Parametr `action` z query stringu bez escapování LIKE metacharakterů (`%`, `_`). Není SQL injection (SQLAlchemy parametrizuje), ale útočník může manipulovat výsledky vyhledávání.

Korektní implementace existuje v `python-backend/app/repositories/project_repository.py`:

```python
search.replace(_LIKE_ESCAPE_CHAR, _LIKE_ESCAPE_CHAR * 2)
     .replace("%", _LIKE_ESCAPE_CHAR + "%")
     .replace("_", _LIKE_ESCAPE_CHAR + "_")
```

**Požadovaná akce:** Aplikovat stejný escape pattern na `admin.py:553` a `material_catalog_repository.py:21`.

### P2-2 — Material catalog nepoužívá `resolve_org_id()`

**Soubor:** `python-backend/app/api/routes/material_catalog.py` — řádek 18

```python
items = await service.list_material_catalog(
    organization_id=current_user.organizationId, ...
)
```

Pro superadmina je `organizationId` `None`, což může vracet nefiltrovná data přes celou tabulku. Ostatní routy konzistentně volají `resolve_org_id(current_user)`.

**Požadovaná akce:** Nahradit `current_user.organizationId` za `resolve_org_id(current_user)` ve všech handlerech v tomto souboru.

### P2-3 — Permisivní CORS konfigurace

**Soubor:** `python-backend/app/main.py` — řádky 325–326

```python
allow_methods=["*"],
allow_headers=["*"],
```

**Požadovaná akce:**

```python
allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
```

---

## E) ÚTOKOVÉ SCÉNÁŘE

### Scénář 1 — Account Takeover přes credential stuffing

1. Útočník vezme databázi uniklých hesel
2. Zaútočí na `POST /auth/login` se seznamem kombinací
3. **Blokováno:** IP rate limiting (10/min slowapi) + account-level throttle (10 pokusů/15min v Redis)
4. **Blokováno:** Fail-closed — při výpadku Redis vrací 503, ne bypass
5. **Výsledek:** Útok je efektivně zastaven

### Scénář 2 — Tenant Escape přes IDOR

1. Útočník přihlášen jako user v org A, získá `case_id` jiné organizace
2. Zavolá `GET /cases/{case_id}` s vlastním JWT
3. **Blokováno:** `resolve_org_id()` → service vrátí případ jen pokud patří stejné org
4. **Blokováno:** `log_cross_tenant_denied()` zaloguje pokus
5. **Výsledek:** Cross-tenant přístup zablokován, incident zaznamenán

### Scénář 3 — Replay / Token Abuse

1. Útočník zachytí platný refresh token (XSS, network, phishing)
2. Pokusí se ho použít opakovaně
3. **Blokováno:** Token rotation — první použití invaliduje token, druhé selže
4. **Blokováno:** JTI tracking v Redis — každý token je unikátní
5. **Výsledek:** Zneužití zachyceného refresh tokenu limitováno na jedno použití

### Scénář 4 — Job Queue Poisoning

1. Útočník autentizovaný jako manager vytvoří analysis job s malformovaným payloadem
2. Job vstoupí do fronty
3. **Blokováno:** `_validate_worker_payload()` v `runner.py` validuje payload před zpracováním
4. **Výsledek:** Nevalidní job odmítnut s `WorkerPayloadValidationError`

### Scénář 5 — Path Traversal přes File Upload

1. Útočník nahraje soubor s názvem `../../etc/passwd`
2. **Blokováno:** `_normalize_relative_storage_key()` detekuje `..` segmenty → odmítne
3. **Blokováno:** `_resolve_storage_path()` → `.relative_to(STORAGE_ROOT)` → ValueError → 404
4. **Výsledek:** Útok zachycen ve dvou nezávislých vrstvách

### Scénář 6 — DoS přes neomezené read endpointy (**EXPLOITABLE — viz P1-1**)

1. Útočník se legitimně přihlásí (nebo kompromituje jeden tenant účet)
2. Spustí 1000 paralelních requestů na `GET /cases`
3. **Neblokováno:** Žádný rate limit na těchto endpointech
4. **Dopad:** Přetížení DB connection pool → degradace pro ostatní tenanty
5. **Výsledek:** EXPLOITABLE — dokud není P1-1 opraveno

### Scénář 7 — User Enumeration přes Login Timing

1. Útočník zkouší existující vs neexistující username na `POST /auth/login`
2. **Blokováno:** Aplikace provádí dummy bcrypt hash i pro neexistující uživatele (`auth_service.py:294-295`)
3. **Blokováno:** Odpověď je identická bez ohledu na existenci účtu
4. **Výsledek:** Timing side-channel je eliminován

---

## F) DOPAD NA KLIENTY

| Scénář                 | Tenant A ovlivní Tenant B? | Únik dat? | Ztráta dat? | Neautorizovaný přístup? |
| ---------------------- | -------------------------- | --------- | ----------- | ----------------------- |
| Auth brute-force       | Ne — per-account throttle  | Ne        | Ne          | Blokováno               |
| IDOR na cases          | Ne — org_id filtrování     | Ne        | Ne          | Blokováno               |
| DoS via read endpointy | **ANO** — sdílená DB       | Ne        | Ne          | Ne, ale výpadek         |
| .env.production leak   | **ANO** — global JWT       | **ANO**   | **ANO**     | **ANO**                 |
| Cache poisoning        | Ne — versioned envelope    | Ne        | Ne          | Blokováno               |
| Worker job poisoning   | Ne — payload validace      | Ne        | Ne          | Blokováno               |
| Token replay           | Ne — single-use refresh    | Ne        | Ne          | Blokováno               |

---

## G) VERDICT

| Úroveň               | Stav         | Podmínka                                                                                                   |
| -------------------- | ------------ | ---------------------------------------------------------------------------------------------------------- |
| **Pilot-ready**      | ✅ ANO       | Po ověření / rotaci `.env.production` credentials                                                          |
| **Enterprise-ready** | ⚠️ PODMÍNĚNĚ | Po opravě P1-1 (rate limiting na read endpoints)                                                           |
| **100k-scale safe**  | ❌ NE        | Vyžaduje: distributed rate limiting (Redis-backed), per-tenant request quotas, circuit breakers na DB pool |

---

## H) POZITIVNÍ BEZPEČNOSTNÍ NÁLEZY

Systém má nadstandardní design v těchto oblastech:

| Oblast             | Nález                                                     | Soubor                           |
| ------------------ | --------------------------------------------------------- | -------------------------------- |
| Fail-closed auth   | Redis výpadek → 503, ne bypass                            | `auth.py:176-185`                |
| Token rotation     | Refresh token rotation s JTI tracking                     | `auth_service.py:389-427`        |
| Timing ochrana     | Dummy bcrypt hash pro neexistující uživatele              | `auth_service.py:294-295`        |
| Timing floor       | 4ms/12ms floor pro tenant-sensitivní operace              | `tenant_timing.py`               |
| Path traversal     | Dvojitá ochrana: normalize + resolve+relative_to          | `local_photo_storage.py:195-224` |
| Cache envelope     | Versioned + tagged envelope zabraňuje poisoningu          | `cache.py:107-115`               |
| Impersonace        | Short-lived token, audit, nemůže impersonovat superadmina | `admin.py:594-662`               |
| Session management | Per-session revokace přes JTI                             | `auth_service.py`                |
| Config hardening   | Fail-fast pro slabé secrets, placeholders, debug flagy    | `config.py:650-675`              |
| Password policy    | Min 10 znaků, uppercase, lowercase, digit, special        | `auth_service.py`                |

---

## I) PRIORITIZOVANÝ AKČNÍ PLÁN

### Ihned (před pilotem)

- [ ] **P0-1:** Ověřit `python-backend/.env.production` → rotovat secrets → přidat do `.gitignore` → vymazat z git history

### Do 14 dní (před první produkční zakázkou)

- [x] **P1-1:** Rate limiting na všechny list/detail endpointy — HOTOVO 2026-04-05
- [ ] **P1-2:** Přidat startup check pro výchozí seed hesla

### Do 30 dní

- [ ] **P2-1:** Opravit ILIKE escapování v `admin.py:553` a `material_catalog_repository.py:21`
- [ ] **P2-2:** Nahradit `current_user.organizationId` za `resolve_org_id()` v `material_catalog.py`
- [ ] **P2-3:** Zpřísnit CORS `allow_methods` a `allow_headers`

---

_Dokument vygenerován na základě kompletního auditu zdrojového kódu. Platnost: do další major verze backendu nebo security incidentu._
