# NovuConstruct – Cílová bezpečnostní architektura

| | |
|---|---|
| **Datum** | 17. 10. 2026 |
| **Stav** | **NÁVRH ke schválení.** Nic z toho není implementováno. |
| **Platforma** | Hetzner, Ubuntu 24.04 LTS / Debian 12, PostgreSQL 16, Redis, MinIO (lokální disk), Python backend + worker, nginx, TLS, systemd, WireGuard. Bez Dockeru a bez AWS. |
| **Vzor** | Private-first model NovuServeru (`J:\Github\NovuServer\docs\SECURITY_NETWORK_BOUNDARY.md`): zóny, aplikační exposure guard, 404 místo 403, default-deny. |
| **Související** | [SECURITY_AUDIT.md](SECURITY_AUDIT.md) · [API_EXPOSURE_MATRIX.md](API_EXPOSURE_MATRIX.md) · [WG_NETWORK_DESIGN.md](WG_NETWORK_DESIGN.md) · [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) |

---

## 1. Principy

1. **Private-first.** Backend API, PostgreSQL, Redis a MinIO nemají žádný port na veřejném rozhraní. Z internetu je dosažitelné jen nginx na edge (443/80) a handshake WireGuardu (UDP).
2. **WireGuard je síťová hranice, ne autorizace.** Každý požadavek v privátní zóně dál vyžaduje platný token, roli a kontrolu firmy, stejně jako dnes.
3. **Obrana ve více vrstvách.** Každé omezení platí na síti (nftables a Hetzner Cloud Firewall), v nginx (bind a allowlist) a v aplikaci (zónový guard). Selhání jedné vrstvy samo nic neotevře.
4. **Default-deny.** Route, kterou nikdo nezařadil do zóny, je blokovaná ve **všech** produkčních zónách včetně admin (upřesněno při implementaci F3, 17. 10. 2026). CI selže na každé nezařazené route.
5. **Gateway není proxy.** Pouští jen explicitní seznam operací (metoda + šablona cesty) z [API_EXPOSURE_MATRIX.md](API_EXPOSURE_MATRIX.md). Nemá JWT signing secret ani přístup k DB, Redisu core ani MinIO.
6. **Token je vázaný na kanál.** Token vydaný přes web nefunguje na desktopu ani v adminu a naopak (claim `aud`).
7. **Browser nikdy nevidí JWT.** Dostane jen opaque session cookie (HttpOnly, Secure, SameSite=Strict).
8. **Stávající API kontrakty se nemění.** Nové funkce (MFA, zóny, enrollment zařízení) se přidávají jako nové endpointy nebo nové hodnoty polí, ne jako změna tvaru odpovědí.

---

## 2. Schéma

```
                         INTERNET
                            │
        ┌───────────────────┼─────────────────────────────────────┐
        │ TCP 443/80        │ UDP 51830 (wg-nc)  UDP 51831 (wg-nc-admin)
        ▼                   │                                     │
┌──────────────────────────────────┐                              │
│  PUBLIC EDGE  (server "edge")    │                              │
│                                  │                              │
│  nginx :443  app.<doména>        │                              │
│   ├─ /             → SPA (static)│                              │
│   ├─ /bff/auth/*   → gateway     │  veřejné auth služby         │
│   ├─ /bff/api/*    → gateway     │  allowlist operací           │
│   └─ vše ostatní   → 404         │                              │
│  nginx :443  www.<doména> → info │                              │
│                                  │                              │
│  nc-gateway (BFF)  unix socket   │                              │
│   ├─ session store (lokální Redis, šifrované refresh tokeny)    │
│   ├─ CSRF, Origin check, rate limit, audit bezp. událostí       │
│   └─ klient core API: jen přes WG → 10.50.0.1:8200              │
│                                  │                              │
│  wg-nc 10.50.0.2 ───────────────────────────────┐               │
└──────────────────────────────────┘              │               │
                                                  │ WireGuard     │
                     ┌────────────────────────────┼───────────────┼──────────┐
                     │  PRIVATE CORE  (server "core")             │          │
                     │                            ▼               ▼          │
                     │  wg-nc 10.50.0.1        wg-nc-admin 10.51.0.1         │
                     │    │                         │                        │
                     │  nginx (bind jen na WG adresy, nastaví zónu)          │
                     │   :8200 zóna GATEWAY  ← jen peer 10.50.0.2            │
                     │   :8210 zóna DESKTOP  ← peery 10.50.16.0/20           │
                     │   :8220 zóna ADMIN    ← peery 10.51.0.0/24            │
                     │    │                                                  │
                     │  nc-api@gateway  nc-api@desktop  nc-api@admin         │
                     │  (3 instance FastAPI, každá vlastní unix socket       │
                     │   a pevně nastavená zóna; stejný kód)                 │
                     │    │                                                  │
                     │  nc-worker (AI pipeline, exporty, fronta)             │
                     │    │                                                  │
                     │  PostgreSQL 16 :5432   Redis :6379   MinIO :9000      │
                     │  (vše jen 127.0.0.1 / unix socket)                    │
                     │                                                       │
                     │  SSH :22 jen z wg-nc-admin                            │
                     └───────────────────────────────────────────────────────┘
                                   ▲                        ▲
                                   │ wg-nc                  │ wg-nc-admin
                         Desktop NovuConstruct        NovuAdmin (modul
                         (Qt, vlastní WG peer)        NovuConstruct)
                                                      + monitoring peer

    Odchozí z core: jen Anthropic API (HTTPS), SMTP relay, Hetzner Storage Box (zálohy).
```

Varianta s jedním serverem je popsaná v [WG_NETWORK_DESIGN.md](WG_NETWORK_DESIGN.md#6-varianty-nasazení). Gateway tam s core komunikuje přes unix socket a místo síťové izolace platí izolace procesů.

---

## 3. Zóny a aplikační guard

### 3.1 Zóny

| Zóna | Kdo se do ní dostane | Účel | `aud` tokenu |
|---|---|---|---|
| `public` | internet → edge nginx | statická SPA, informační web, `/bff/auth/*` (implementuje gateway, ne core) | – |
| `gateway` | jen WG peer gateway | operace, které webový uživatel smí provést přes BFF | `nc-web` |
| `desktop` | WG peery zařízení (enrollované) | desktopová aplikace | `nc-desktop` |
| `admin` | WG peery administrátorů (NovuAdmin), monitoring peer | admin API, metriky, interní health | `nc-admin` |
| `dev` | jen `APP_ENV=development` | `/docs`, `/redoc`, `/openapi.json`, `/mock-storage` | – |

**Core nemá žádnou veřejnou zónu.** Veřejné autentizační služby z požadavku implementuje gateway. Ta je jediný, samostatně navržený veřejný vstup, a na core volá jen operace své zóny.

### 3.2 Jak se určuje zóna (nelze podvrhnout)

Každá zóna má vlastní instanci API: systemd šablona `nc-api@.service` a `NC_ZONE=%i`.

- Každá instance poslouchá na vlastním unix socketu: `/run/novuconstruct/api-gateway.sock`, `api-desktop.sock` a `api-admin.sock`.
- Práva k socketu má jen nginx.
- Zóna je **vlastnost procesu**, žádná hlavička ani IP adresa ji neurčuje.

Tím se obejde slabé místo modelu podle hlaviček: i kdyby se útočník dostal k nginx konfiguraci jedné zóny, aplikace v té instanci pořád pustí jen routy své zóny.

> Alternativa: jeden proces s `NC_ZONE_PORTS` podle NovuServeru. Spotřebuje méně paměti, ale zónu určuje lokální port a správnost bindů. Doporučujeme tři instance, protože admin instance pak běží s jinými právy (viz 3.4).

### 3.3 Exposure guard (port vzoru NovuServeru)

- `app/core/exposure.py` obsahuje tabulku `(metoda, šablona cesty) → množina zón`, generovanou a kontrolovanou proti [API_EXPOSURE_MATRIX.md](API_EXPOSURE_MATRIX.md).
- Middleware `exposure_guard` je **nejvnější** vrstva. Rozhodne ještě před autentizací, dependencies a rate limitem a nepovolenou route vrátí jako **404**, ne 403.
- Nezařazená route je blokovaná ve všech produkčních zónách, i v `admin` (default-deny). Dostupná je jen v zóně `dev` (lokální vývoj).
- `tests/test_route_exposure.py` selže na:
  - jakékoli nezařazené route,
  - změně množiny `gateway` bez úpravy schváleného seznamu v testu.
- Token se přijme jen s `aud` odpovídajícím zóně instance.
  - Superadmin se smí přihlásit **jen** v zóně `admin`. Přihlášení v `gateway` i `desktop` vrátí obecné 401.
  - Na kompromitované gateway se tak superadmin nikdy nepřihlašuje.

### 3.4 Oddělení oprávnění procesů na core

| Proces | Systémový uživatel | DB role | Redis ACL | MinIO |
|---|---|---|---|---|
| `nc-api@gateway`, `nc-api@desktop` | `nc-api` | `nc_app` (DML na aplikační tabulky, `INSERT`/`SELECT` na `audit_logs`) | user `api`: klíče aplikace, pubsub `case:*`, `offer:*` | user `nc-app`: policy `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` jen na bucket |
| `nc-api@admin` | `nc-admin-api` | `nc_admin` (navíc čtení napříč firmami podle admin endpointů) | user `admin` | user `nc-app` |
| `nc-worker` | `nc-worker` | `nc_app` | user `worker`: fronta | user `nc-worker` |
| Alembic migrace | `nc-migrate` (jen při deployi) | `nc_owner` (DDL), jinak nepoužívaná | – | – |

`audit_logs`: `REVOKE UPDATE, DELETE` pro všechny aplikační role (SA-14). Retenci provádí jen `nc_owner` přes cron.

---

## 4. Webové rozhraní: Browser ↔ Gateway ↔ WG ↔ Backend

### 4.1 Rozhodnutí o JWT

**JWT zůstává interním tokenem mezi core a jeho klienty. Do prohlížeče se už nedostane.**

| Varianta | Hodnocení |
|---|---|
| A) Browser drží JWT (dnešní stav) | ❌ Token v localStorage ukradne každé XSS (SA-27). S BFF to nejde dohromady. |
| B) Gateway vydává vlastní tokeny a core jim věří | ❌ Gateway by musela mít signing secret, takže její kompromitace znamená falšování identity kohokoli. |
| **C) Core vydává JWT (`aud=nc-web`), gateway je drží v server-side session, browser má opaque cookie** | ✅ Doporučeno. Gateway nemůže vyrobit token. Kompromitace odhalí jen právě aktivní webové sessions. |

**Úpravy JWT** (aditivní, tvar odpovědí `/auth/*` se nemění):
- přidat `iss`, `aud` a `iat`,
- validovat `JWT_ALGORITHM`,
- access TTL zkrátit na **10 min** (dnes 60), refresh pro web na **12 h absolutně** (session gateway), pro desktop ponechat 30 dní s rotací,
- `get_user_by_token` porovná `session.access_jti` (SA-18),
- reuse refresh tokenu zruší celou session (SA-10),
- impersonační token dostane `sid` a `aud=nc-web`, takže pracuje jen přes gateway pod dohledem a jde revokovat (SA-15).

### 4.2 Session a cookies

| Prvek | Hodnota |
|---|---|
| Session cookie | `__Host-nc_sid`: 256bit náhodná hodnota, `HttpOnly; Secure; SameSite=Strict; Path=/`, bez `Domain` |
| Session store | Redis na edge. Klíč je `sha256(sid)`. Hodnota (access a refresh JWT, user id, stav MFA, CSRF secret, IP/UA fingerprint pro audit) je šifrovaná AES-GCM klíčem gateway. |
| Platnost | idle 30 min, absolutně 12 h, rotace `sid` po přihlášení a po MFA |
| Odhlášení | gateway zavolá core `/auth/logout` (revokace session), smaže záznam a pošle `Set-Cookie` s `Max-Age=0` |
| Odhlášení všude | core `DELETE /auth/sessions/{id}` / `token_version++`. Gateway při dalším požadavku dostane 401 a session zahodí. |

### 4.3 CSRF

1. `SameSite=Strict` cookie.
2. Synchronizer token: `GET /bff/session` vrátí `csrfToken`. Každý `POST`/`PUT`/`PATCH`/`DELETE` musí poslat `X-CSRF-Token`, který se porovná s tajemstvím v session (konstantní čas).
3. Kontrola `Origin` / `Sec-Fetch-Site: same-origin` u mutací.
4. API přijímá jen `application/json` a `multipart/form-data`. CORS se nepovoluje (SPA i BFF jsou na stejném originu).

### 4.4 MFA

Backend MFA dnes nemá. Návrh:
- **TOTP (RFC 6238)** v core jako nové endpointy `/auth/mfa/*`:
  - seed šifrovaný v DB,
  - 10 recovery kódů uložených jako hash,
  - okno ±1 krok,
  - throttle.
- **Povinné** pro `superadmin` (admin zóna) a `manager`. Pro `technician` volitelné, v další fázi povinné.
- Přihlášení se dvěma kroky: nový endpoint `POST /auth/login/start` vrátí `mfaRequired` + krátkodobý ticket (2 min), pak `POST /auth/login/mfa`. **Stávající `POST /auth/login` se nemění.** Zůstává pro desktop zónu do doby, než desktop MFA podporuje, a v `gateway`/`admin` zóně se nevystavuje.
- WebAuthn/passkeys až ve druhé vlně.

### 4.5 Gateway: povinné kontroly na každém požadavku

1. Najít šablonu cesty v allowlistu (metoda + šablona). Když tam není, vrátit **404**.
2. Validovat parametry cesty (formát ID podle regexu) a maximální velikost těla podle route (JSON 256 KB, upload 25 MB jen na upload routách).
3. Ověřit session, CSRF a Origin.
4. Zahodit všechny příchozí hlavičky kromě allowlistu: `Content-Type`, `Accept`, `If-None-Match`, `X-Request-Id`. Nastavit `Authorization: Bearer <access>`, `X-Request-Id` a `X-NC-Client-IP`. Core tuto hlavičku bere jen z gateway socketu, a jen pro audit a rate limit, nikdy pro autorizaci.
5. Rate limit podle session a podle IP (Redis na edge). Pro `/bff/auth/*` přísnější, viz 4.7.
6. Odpověď z core předat, ale odstranit interní hlavičky. Chyby 5xx přeložit na obecnou chybu s `requestId`.
7. Zapsat bezpečnostní události: login ok/fail, MFA ok/fail, logout, CSRF fail, allowlist miss, rate limit. Jdou do journald a přes core endpoint do `audit_logs`.

### 4.6 Autorizace a izolace firem (server-side)

Gateway **nerozhoduje** o oprávnění. Všechny kontroly zůstávají v core:

| Role | Data | Typické operace |
|---|---|---|
| `technician` | jen vlastní firma | zakázky (čtení, vytvoření), fotky, měření (dokud zakázka není zamčená), markery, položky prací |
| `manager` | jen vlastní firma | vše výše + workflow (submit, approve, send), exporty, katalogy, ceníky, dodavatelé, nastavení typů prací, schválení nabídky. **Žádné admin API** (SA-01). |
| `superadmin` | všechny firmy | jen admin zóna (NovuAdmin). Ve `gateway` a `desktop` se nepřihlásí. |

Matice rolí po jednotlivých endpointech je v [API_EXPOSURE_MATRIX.md](API_EXPOSURE_MATRIX.md). Opravy nálezů SA-02, SA-06, SA-07 a SA-08 jsou předpokladem.

Správu uživatelů vlastní firmy manažerem (dnes chybí) navrhujeme jako **nové** tenant-scoped endpointy `/org/users`, ne jako znovupovolení `/admin/*`. Rozhodnutí je v kap. 9 (D-10).

### 4.7 Ochrany podle typu útoku

| Hrozba | Opatření |
|---|---|
| XSS | CSP pro SPA: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`. Žádný token v JS. React escapování. ESLint pravidlo zakazující `dangerouslySetInnerHTML`. |
| CSRF | 4.3 |
| IDOR/BOLA | kontrola firmy v core (repository `*_in_org`), opravy SA-02/07/08/23, testy cross-tenant pro každou route (IMPLEMENTATION_PLAN F2) |
| SQL injection | stav OK, ponechat bound parametry; bandit + semgrep pravidlo na `text(f"...")` v CI |
| SSRF | core nestahuje uživatelské URL. AI dostává obsah inline. Odchozí nftables z core jen na allowlist (Anthropic, SMTP, Storage Box). |
| Brute force a stuffing | gateway: IP 20/5 min, účet 10 neúspěchů/15 min s progresivním zpožděním místo tvrdého zámku (SA-19). Core: slowapi na Redisu, klíč pro `/auth/*` jen IP (SA-03, SA-05). |
| Enumerace účtů | jednotná 401, dummy hash (už je); reset hesla vždy vrací 202 |
| Upload | limit na gateway (25 MB, max 20 souborů), v core validace v threadu, `MAX_IMAGE_PIXELS` 40 Mpx, odstranění EXIF (SA-11, SA-22) |
| Download | kap. 5 |

---

## 5. Soubory, fotky a exporty

**Cíl:** MinIO nikdy neposlouchá mimo `127.0.0.1` a jeho URL nikdy neopustí core.

| Kanál | Návrh |
|---|---|
| **Web** | Core vystaví nové streamovací endpointy, např. `GET /files/images/{id}/preview`, `GET /files/exports/{id}/download`. Každý požadavek ověří token, firmu a roli, zapíše audit (u exportů) a streamuje z MinIO. Gateway je má v allowlistu. Pole `previewUrl`/`downloadUrl` v odpovědích si **zachovají tvar**, jen budou obsahovat relativní cestu na tyto endpointy. Podepsané URL MinIO se klientům nevydávají. |
| **Desktop** | Stejné endpointy přes zónu `desktop`. |
| **AI provider** | Worker načte objekt z MinIO a pošle ho Anthropic API inline jako base64. Žádné URL (SA-16). |
| **Upload** | Browser → gateway (multipart, limity) → core → MinIO. Beze změny kontraktu. |

> Alternativa pro vyšší výkon: podepsané URL přes samostatný host `media.<doména>` na edge, proxy přes WG na MinIO, jen `GET` a jen požadavky s `X-Amz-Signature`. Nevýhoda: S3 API MinIO by bylo dosažitelné z gateway peeru. **Doporučujeme streamování (D-03).**

Šifrování v klidu: LUKS na datovém volume core (Hetzner Volume), MinIO SSE-S3 s KMS klíčem (`MINIO_KMS_SECRET_KEY`, uložený mimo zálohy dat).

---

## 6. Kompromitace gateway: co útočník získá a co ne

| Útočník **má** | Útočník **nemá** |
|---|---|
| aktivní webové sessions (access tokeny `nc-web` platné ≤10 min; refresh tokeny šifrované klíčem gateway, takže po získání klíče až 12 h) | JWT signing secret, takže nemůže vyrobit token |
| možnost volat operace z allowlistu zóny `gateway` jménem přihlášených uživatelů | admin API: zóna `gateway` je vrací jako 404, tokeny `nc-admin` gateway nikdy neviděla |
| hesla uživatelů, kteří se během kompromitace přihlásí | hesla superadminů, protože ti se přes web nepřihlašují |
| WG klíč gateway peeru | přístup k PostgreSQL, Redisu, MinIO a SSH core (nftables je pro peer 10.50.0.2 nepouští) |
| | desktop zónu (jiný port, allowlist IP 10.50.16.0/20) |

**Omezení dopadu:**
- krátké TTL tokenů,
- `aud` binding,
- MFA (útočník s heslem bez TOTP se nepřihlásí jinde),
- audit všech operací s `X-NC-Client-IP`,
- alert na anomálie (počet sessions, allowlist miss, 404 z core),
- runbook: zneplatnit WG klíč gateway, `token_version++` pro všechny uživatele s webovou session, rotovat klíč session store a service secret gateway.

**Service identita gateway vůči core:** WG peer (síťová vrstva) + HMAC hlavička `X-NC-Gateway-Sig` (sdílený secret, rotace 90 dní) na každém požadavku. Core instance `gateway` ji vyžaduje. Ochrana pro případ, že by se na socket dostal jiný lokální proces (varianta s jedním serverem). Implementováno v F3.4, přesný kontrakt (hlavičky, kanonický řetězec, testovací vektor, rotace) je v [GATEWAY_CORE_CONTRACT.md](GATEWAY_CORE_CONTRACT.md).

---

## 7. Integrace NovuAdmin

**Co víme (bez odhadu vnitřní implementace):**
- NovuAdmin je samostatný repozitář `J:\Github\NovuAdmin`, nativní Qt aplikace se sekcemi NovuServer a NovuTrade.
- Má vestavěný userspace WireGuard tunel a identitu zařízení (`src/admin/net/AdminDeviceIdentity.*`).
- Endpointy jsou nastavené při kompilaci.
- Mapování hostname na adresu dělá uvnitř vlastního transportu (viz hlavička `NovuServer/ops/nginx/novuserver-private.conf`).

**Návrh:** samostatný modul/sekce *NovuConstruct* v NovuAdminu. V tomto repozitáři definujeme jen **integrační kontrakt**.

| Kontrakt | Hodnota |
|---|---|
| Síť | vlastní WG profil `wg-nc-admin`, server `10.51.0.1`, UDP 51831. **Oddělený** od `wg-admin` NovuServeru (10.40.0.0/24), aby kompromitace jednoho admin peeru neotevřela druhý systém. |
| Endpoint | `http://10.51.0.1:8220/api/v1` (zóna `admin`; uvnitř WG bez TLS, stejně jako NovuServer; TLS volitelně jako defense-in-depth) |
| Autentizace | `POST /auth/login/start` + `/auth/login/mfa` v zóně `admin`, token `aud=nc-admin`, access 10 min, refresh 8 h, **jen `superadmin` s povinným MFA** |
| Autorizace | stávající `require_superadmin` / `require_admin_capability` (po opravě SA-01 výhradně superadmin) |
| Business logika | žádná duplikace, NovuAdmin volá výhradně HTTP API core |
| Audit | každé admin čtení i zápis jde do `audit_logs` jako security-critical (SA-14), s `actor`, `client=novuadmin` a ID WG peeru |

**Stávající admin API, které modul použije** (beze změny kontraktu):
- `/admin/companies` (GET, POST), `/admin/companies/{id}` (GET, PATCH)
- `/admin/users` (GET, POST), `/admin/users/{id}` (GET, PATCH), `/admin/users/{id}/reset-password` (POST)
- `/admin/jobs` (GET), `/admin/jobs/{id}` (GET), `/admin/jobs/{id}/retry` (POST), `/admin/jobs/{id}/reprocess` (POST)
- `/admin/logs` (GET), `/admin/audit` (GET)
- `/admin/impersonate/{id}` (POST)
- `/health/internal` (GET), `/ready` (GET), `/ready/processing` (GET)

**Nová API pro NovuAdmin** (aditivní, navrhujeme v IMPLEMENTATION_PLAN F7):

| Endpoint | Účel |
|---|---|
| `GET /admin/users/{id}/sessions`, `DELETE /admin/users/{id}/sessions` | přehled a revokace sessions uživatele |
| `GET /admin/audit?actor=&action=&org=&from=&to=&cursor=` | filtrovaný a stránkovaný audit (dnešní endpoint filtry nemá) |
| `GET/POST/DELETE /admin/devices` | správa WG peerů desktopových zařízení (enrollment, revokace) |
| `GET /admin/system/overview` | verze, migrace, stav fronty, úložiště, certifikáty |
| `POST /admin/security/revoke-all-web-sessions` | runbook pro kompromitaci gateway |

---

## 8. Provoz

### 8.1 systemd jednotky

**Core:**
- `nc-api@gateway`, `nc-api@desktop`, `nc-api@admin`, `nc-worker`
- `postgresql@16-main`, `redis-server`, `minio`, `nginx`
- `wg-quick@wg-nc`, `wg-quick@wg-nc-admin`

**Edge:**
- `nc-gateway`, `redis-server` (session store), `nginx`, `wg-quick@wg-nc`

Všechny aplikační jednotky mají:
```
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
CapabilityBoundingSet=
SystemCallFilter=@system-service
ReadWritePaths=<jen potřebné>
```
Gateway navíc `IPAddressDeny=any` + `IPAddressAllow=10.50.0.1 127.0.0.1`.

### 8.2 Secrets

- **Umístění:**
  - `/etc/novuconstruct/<služba>.env`, vlastník `root:<uživatel služby>`, `0640`,
  - nebo `LoadCredential=` u citlivých hodnot (JWT secret, DB heslo, HMAC gateway, KMS klíč MinIO).
  - Nikdy v repozitáři, v image ani v unit souboru.
- **Generování:** `openssl rand -hex 32`, jen na serveru.
- **Úschova:** do dokumentace se nezapisují. Offline kopii drží správce v password manageru.

| Secret | Rotace | Poznámka |
|---|---|---|
| JWT secret | 180 dní | dvoufázově s `kid` (podpora dvou klíčů) |
| HMAC gateway | 90 dní | |
| WG klíče | 1 rok, a vždy při ztrátě zařízení | |
| DB hesla | 1 rok | |

### 8.3 Migrace

- Explicitní krok deploye, nikdy při startu služby (to už platí od v0.8.6).
- **Pořadí:**
  1. záloha DB,
  2. `alembic upgrade head` pod rolí `nc_owner`,
  3. restart API.
- Migrace jsou expand/contract: nová verze kódu musí běžet nad starým i novým schématem, aby šel udělat rollback kódu bez rollbacku DB.
- Destruktivní migrace jen ve dvou releasech a s ručním schválením.

### 8.4 Zálohy a obnova

| Co | Jak | Kam | Retence |
|---|---|---|---|
| PostgreSQL | `pg_dump -Fc` každou noc + WAL archivace (pgBackRest) pro PITR | restic repozitář na Hetzner Storage Box (SFTP, šifrovaný klientem) | 7 denních, 4 týdenní, 6 měsíčních; WAL 7 dní |
| MinIO data | `restic backup /srv/minio` každou noc | stejný repozitář | stejná |
| Konfigurace | `/etc/novuconstruct`, nginx, WG **bez privátních klíčů** | stejný repozitář | 90 dní |
| Klíče (restic heslo, KMS, WG) | offline: password manager správce + tištěná obálka | mimo server | – |

- Host key Storage Boxu je připnutý a `umask 077` (SA-31).
- **Zkouška obnovy jednou měsíčně** na dočasný server s protokolem do `docs/` (doplní chybějící evidenci B6).
- Cíle: RPO ≤ 15 min (WAL), RTO ≤ 4 h.

### 8.5 Monitoring a alerting

- Prometheus na core (nebo na samostatném monitoring peeru v `wg-nc-admin`). Sbírá:
  - node_exporter (edge i core přes WG),
  - postgres_exporter, redis_exporter,
  - `/api/v1/metrics` (zóna admin, token),
  - metriky gateway.
- Alertmanager s e-mailem a push notifikacemi. Pravidla navazují na `ops/alerting/*.yml` a přidávají:
  - spike 404 z core v zóně gateway (allowlist miss),
  - nový WG handshake od neznámého peeru,
  - selhání zálohy, expirace certifikátu < 14 dní,
  - nárůst neúspěšných MFA.
- Externí uptime check jen na `https://app.<doména>/bff/health` (vrací jen `{"status":"ok"}`).
- **Logy:** journald s persistentním úložištěm (90 dní). nginx loguje bez query stringů. Redakce tokenů už v aplikaci je.

### 8.6 Aktualizace

- **OS:** `unattended-upgrades` jen pro security. Restart po kernel update ručně v okně údržby.
- **Aplikace:**
  1. release tag,
  2. skript `deploy.sh <tag>`: kontrola podpisu tagu, záloha, migrace, restart instancí po jedné, smoke test přes všechny zóny (ověří i to, že admin route v zóně gateway vrací 404),
  3. automatický rollback kódu při selhání smoke testu.
- **Závislosti:** `pip-audit` a `npm audit` v CI jako blokující krok pro High/Critical.

---

## 9. Otevřená rozhodnutí

| ID | Rozhodnutí | Doporučení |
|---|---|---|
| **D-01** | Jeden, nebo dva servery v produkci | **Dva** (edge CX22 + core CCX/CPX). Jeden server je přijatelný pro pilot. Kompromisy v [WG_NETWORK_DESIGN.md](WG_NETWORK_DESIGN.md#6-varianty-nasazení). |
| **D-02** | Technologie gateway | Python (FastAPI/Starlette) jako samostatný adresář `gateway/` a samostatný proces. Žádný import z `python-backend` kromě generovaného allowlistu. |
| **D-03** | Doručování médií | Streamování přes core (kap. 5) |
| **D-04** | Veřejná registrace | Dnes neexistuje. **Pozvánkami** (admin založí firmu a pozve manažera), bez otevřené registrace. |
| **D-05** | Obnova hesla e-mailem | Vyžaduje SMTP (dnes 410). Doporučeno zavést přes gateway s jednorázovým tokenem 30 min a revokací sessions po resetu. |
| **D-06** | MFA | TOTP povinné pro manager a superadmin, WebAuthn později |
| **D-07** | Enrollment desktopu do WG | Klíč se generuje na zařízení. Manažer firmy nebo superadmin zařízení schválí v NovuAdminu. Jednorázový enrollment kód přes gateway (`/bff/device-enrollment`). Detail v WG_NETWORK_DESIGN kap. 4. |
| **D-08** | Adresní rozsahy WG | `10.50.0.0/16` (wg-nc) a `10.51.0.0/24` (wg-nc-admin). Nekolidují s NovuServerem (`10.20.0.0/24`, `10.40.0.0/24`). Ověřit proti dalším sítím správce. |
| **D-09** | Monitoring | Prometheus na core vs. samostatný monitoring server |
| **D-10** | Správa uživatelů vlastní firmy | **Rozhodnuto 17. 10. 2026:** firemní admin (role `admin`) přes nové `/org/users` v zónách gateway a desktop, jen vlastní firma, bez superadminů a bez přidělení role `admin`. Systémová administrace jen NovuAdmin přes WG (zóna admin). |
| **D-11** | Webový admin `web/src/pages/Admin*` | Odstranit. Admin bude výhradně v NovuAdminu přes WG. |
