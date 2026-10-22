# NovuConstruct Web Gateway / BFF (`nc_gateway`)

Samostatná webová gateway (Backend-for-Frontend) pro webové SPA podle
[NC-007 etapa 1](../../docs/security/NC-007_STAGE1_CONTRACT.md) a
[kontraktu Gateway ↔ Core](../../docs/security/GATEWAY_CORE_CONTRACT.md).

- Prohlížeč dostane jen neprůhlednou cookie `__Host-nc_sid`. JWT z core zůstávají
  v šifrované session v Redisu a do prohlížeče nikdy nejdou (ani v těle loginu).
- Každý požadavek na core je podepsaný HMAC (`X-NC-Gateway-*`, unikátní nonce, čas).
- Gateway **nemá** `JWT_SECRET_KEY` a JWT nikdy neověřuje ani nevyrábí. `exp`
  a `sid` z access tokenu čte bez ověření jen jako nápovědu pro obnovu tokenu.
- Z `src/backend` nic neimportuje (D-02). Jediný sdílený soubor je
  `docs/security/gateway-allowlist.json`.

## Spuštění

```powershell
# jednorázově (Windows; na Linuxu python3.13 -m venv .venv)
J:/Github/Novu_Builder/src/backend/.venv/Scripts/python.exe -m venv src/gateway/.venv
src/gateway/.venv/Scripts/python.exe -m pip install -r src/gateway/requirements-dev.txt

# běh (z adresáře src/gateway, konfigurace jen z proměnných prostředí)
cd src/gateway
.venv/Scripts/python.exe -m nc_gateway
```

Neplatná nebo chybějící konfigurace znamená okamžitý konec s kódem 2 a
záznamem `gateway_config_invalid` v logu. Nic se nespustí.

### Testy a kontroly

```powershell
src/gateway/.venv/Scripts/python.exe -m pytest src/gateway/tests -q
cd src/gateway; .venv/Scripts/python.exe -m ruff check .; .venv/Scripts/python.exe -m mypy
```

Testy, které potřebují Redis, používají skutečný Redis na
`redis://localhost:56379/5` (přepíše ho `NC_GATEWAY_TEST_REDIS_URL`). Databázi 5
před testem a po něm vyprázdní (`FLUSHDB`). Když Redis neběží, tyto testy se
přeskočí (skip) s uvedeným důvodem. Core v testech nahrazuje `httpx.MockTransport`,
který ověřuje HMAC podpis vlastní implementací napsanou podle kontraktu.

## Proměnné prostředí

Povinné jsou ve **všech** prostředích, včetně developmentu. Žádné výchozí klíče
ani paměťová náhrada Redisu neexistují.

| Proměnná | Povinná | Popis |
|---|---|---|
| `NC_ENV` | ano | `development`, `test`, `staging`, `production` |
| `NC_BFF_PUBLIC_ORIGIN` | ano | origin SPA a gateway, např. `https://app.novuconstruct.cz`. Mimo development jen `https://`. |
| `NC_BFF_CORE_URL` | ano | `http://10.50.0.1:8200` (core přes WG), `http://127.0.0.1:8200` (jeden server) nebo `http+unix:///run/nc/api-gateway.sock`. Bez cesty. |
| `NC_GATEWAY_HMAC_KEY` | ano | `kid:secret`, secret ≥ 32 B (stejná hodnota jako jeden klíč v `NC_GATEWAY_HMAC_KEYS` na core) |
| `NC_BFF_SESSION_KEYS` | ano | `kid:base64(32 B)[,kid:base64(32 B)…]`. První šifruje, ostatní jen dešifrují (rotace). |
| `NC_BFF_REDIS_URL` | ano | Redis gateway, **oddělený** od Redisu core (vlastní instance nebo ACL uživatel na `nc:bff:*`), `maxmemory-policy noeviction` – viz níže |
| `NC_BFF_ALLOWLIST_PATH` | ano | cesta k `gateway-allowlist.json`. Chybějící, nečitelný nebo prázdný soubor = proces nenastartuje. |
| `NC_BFF_TRUSTED_PROXY` | ne | přesně jedna IP lokálního nginx (nebo `unix`). Jen od této adresy se čte `X-Forwarded-For` (poslední hodnota). |
| `NC_BFF_DEV_INSECURE_COOKIE` | ne | `1` = cookie `nc_sid_dev` bez `Secure`. **Jen** pro `NC_ENV=development`, jinak proces nenastartuje. |
| `NC_BFF_IDLE_TIMEOUT_SECONDS` | ne | idle limit session, výchozí 1800 |
| `NC_BFF_ABSOLUTE_TIMEOUT_SECONDS` | ne | absolutní limit session, výchozí 43200 (obnovou tokenu se neprodlužuje) |
| `NC_BFF_LISTEN_HOST` / `NC_BFF_LISTEN_PORT` | ne | výchozí `127.0.0.1:8090` |
| `NC_BFF_CORE_TIMEOUT_SECONDS` | ne | timeout běžného volání core, výchozí 30 (connect 5 s) |
| `NC_BFF_SSE_IDLE_TIMEOUT_SECONDS` | ne | idle limit pro `text/event-stream` (SSE `…/activity/stream`), výchozí 300 |
| `NC_BFF_UPLOAD_ROUTES` | ne | seznam `POST /api/v1/…` (šablony z allowlistu), kde je povolen `multipart/form-data` do 25 MiB. Výchozí: `POST …/images` a `POST …/upload*`. |

Tajné hodnoty lze předat i přes systemd `LoadCredential=`: když proměnná chybí
a existuje soubor `$CREDENTIALS_DIRECTORY/<JMÉNO_PROMĚNNÉ>`, načte se z něj.

Generování klíče session: `python -c "import base64,os;print('s1:'+base64.b64encode(os.urandom(32)).decode())"`.

### Lokální vývoj přes Vite proxy (`http://localhost:5173`)

Prohlížeč přes `http://` neuloží cookie s atributem `Secure` (a tedy ani
`__Host-` cookie). Vývoj přes Vite dev server proto jde **jen** takto:

```powershell
$env:NC_ENV = "development"
$env:NC_BFF_PUBLIC_ORIGIN = "http://localhost:5173"
$env:NC_BFF_DEV_INSECURE_COOKIE = "1"      # cookie nc_sid_dev bez Secure
$env:NC_BFF_CORE_URL = "http://127.0.0.1:8200"   # core v zóně gateway
$env:NC_GATEWAY_HMAC_KEY = "gw-dev:<stejný secret jako NC_GATEWAY_HMAC_KEYS na core>"
$env:NC_BFF_SESSION_KEYS = "s1:<base64 32 B>"
$env:NC_BFF_REDIS_URL = "redis://localhost:6379/5"
$env:NC_BFF_ALLOWLIST_PATH = "../../docs/security/gateway-allowlist.json"
.venv/Scripts/python.exe -m nc_gateway
```

Vite proxy přeposílá `/bff` na gateway `http://127.0.0.1:8090` (výchozí `NC_BFF_LISTEN_PORT`) a musí zachovat hlavičku
`Origin` (`changeOrigin: false`), jinak gateway odmítne mutace (403 `ORIGIN_REJECTED`).
`http://` origin bez `NC_BFF_DEV_INSECURE_COOKIE=1`, nebo `NC_BFF_DEV_INSECURE_COOKIE=1`
mimo `NC_ENV=development`, znamená, že proces nenastartuje.

## Endpointy

| Metoda | Cesta | Popis |
|---|---|---|
| GET | `/bff/health` | `{"status":"ok"}`, nic o core ani Redisu |
| POST | `/bff/auth/login` | Origin, JSON, limity IP 20/5 min a e-mail 10 neúspěchů/15 min. 200 `{"user","csrfToken"}` + cookie, jinak jednotná 401 `Invalid credentials.` |
| POST | `/bff/auth/logout` | session + CSRF. Volá core logout. 204 + `Max-Age=0` (i když core neodpoví) |
| POST | `/bff/auth/logout-all` | session + CSRF. Revokuje ostatní sessions v core, odhlásí aktuální a smaže **všechny** sessions uživatele v gateway |
| GET | `/bff/session` | `{"authenticated":true,"user","csrfToken","expiresAt","idleExpiresAt"}` nebo `{"authenticated":false}` |
| * | `/bff/api/<cesta>` | proxy na `/api/v1/<cesta>` podle allowlistu |

Vše ostatní vrací 404 (`/api/*`, `/docs`, `/openapi.json`, `/metrics`, `/admin*`,
metody `HEAD`, `OPTIONS`, `TRACE`, `CONNECT`, websockety se zavřou).

## Bezpečnostní model

**Kontroly na `/bff/api` (v tomto pořadí):**

0. rate limit na IP (600/min) **před** allowlistem, takže neautentizovaný provoz nejde zesílit do auditu,
1. allowlist (METODA + šablona, parametr = jeden segment `[A-Za-z0-9._~-]{1,128}`). Mimo něj, cesty pod `/api/v1/auth/` a `/api/v1/internal/`, `.`/`..`, prázdné segmenty, jakékoli percent-encoding (`%2F`, `%5C`, `%00`, `%2E`…) a zpětné lomítko → 404 + `allowlist_miss` (agregovaně: nejvýš 1 událost na IP za 10 s, v `detail.previousWindowCount` počet za předchozí okno),
2. velikost těla jen z deklarované `Content-Length` (tělo se ještě nečte): JSON max 256 KiB, multipart max 25 MiB jen na upload routách → 413,
3. `Content-Type` těla jen `application/json` nebo `multipart/form-data` (multipart jen na upload routách) → 415,
4. session → 401 `Not authenticated.`,
5. mutace: `Origin` == `NC_BFF_PUBLIC_ORIGIN` (bez Origin musí být `Sec-Fetch-Site: same-origin`) → 403 `{"detail":"Origin not allowed.","code":"ORIGIN_REJECTED"}`; `X-CSRF-Token` == `csrfSecret` (`hmac.compare_digest`) → 403 `{"detail":"CSRF validation failed.","code":"CSRF_FAILED"}`,
6. rate limit na session 300/min → 429 + `Retry-After`,
   - **tělo se čte až teď** (po session a CSRF), s průběžným limitem (i chunked bez `Content-Length`) a s průběžným SHA-256 do `SpooledTemporaryFile` (do 1 MiB v paměti, pak na disku). Do core se streamuje ze souboru po 64 KiB s explicitní `Content-Length`. Upload tak nikdy neleží celý v paměti,
7. do core jdou jen `Content-Type`, `Accept`, `If-None-Match`, `Range`, `If-Range` a u SSE `Last-Event-ID` (max 64 znaků `[0-9A-Za-z:._-]`, jinak se zahodí). Gateway přidá `Authorization: Bearer <access>`, vlastní `X-Request-Id`, `Accept-Encoding: identity` a podpis `X-NC-*`. Cookie, `X-Forwarded-*`, `X-NC-*`, `Authorization` ani nic dalšího z prohlížeče do core nejde,
8. odpověď core se streamuje bez bufferu a beze změny těla. Projdou jen hlavičky `Content-Type`, `Content-Length`, `Content-Disposition`, `Content-Range`, `Accept-Ranges`, `ETag`, `Last-Modified`, `Cache-Control`, `Retry-After`, `X-Request-Id` a `Content-Security-Policy`. Když core CSP nepošle, gateway nastaví `default-src 'none'; frame-ancestors 'none'; sandbox`. 5xx se nahradí `{"detail":"Upstream error.","requestId"}` se stejným kódem. Core nedostupný → 502.

**Session:** `sid` = `secrets.token_urlsafe(32)`. V Redisu je jen `sha256(sid)`
(`nc:bff:sess:<hash>`). Hodnota je AES-256-GCM (`v1.<kid>.<base64url(nonce‖ciphertext)>`),
AAD = klíč záznamu, takže záznam nejde přesunout pod jiné `sid`. Při každém
loginu vzniká nové `sid` a záznam příchozí cookie se smaže (ochrana proti fixation).
Index `nc:bff:user:<id>` slouží pro „odhlásit všude“. Úpravy záznamu jdou přes
`WATCH/MULTI`, takže souběžný požadavek nevrátí do Redisu starý refresh token.

**Obnova tokenu:** když do `exp` zbývá < 60 s, nebo po 401 z core (jednou),
se zámkem `nc:bff:lock:<hash>` (TTL = timeout core + 5 s). Souběžné požadavky na zámek
počkají a použijí nový token. Když se token ani po čekání nezmění, vrátí se 503
(session se neruší a starý token se neopakuje). Když core odmítne i refresh (400/401/403), session se smaže
(`session_revoked`) a klient dostane 401 se zrušenou cookie. Výpadek core (síť, 5xx) session nemaže, vrací 502.

**Klientská IP:** jen ze spojení. `X-Forwarded-For` se čte jen od
`NC_BFF_TRUSTED_PROXY` (poslední hodnota). uvicorn běží s `proxy_headers=False`.
IP jde do core v kanonickém tvaru v podepsané `X-NC-Client-IP`.

**Fail closed:** Redis nedostupný → 503 (žádná náhrada v paměti). Core nedostupný → 502.

**Redis gateway musí běžet s `maxmemory-policy noeviction`.** Při jiné politice by
Redis mohl tiše vyhodit sessions, čítače rate limitu nebo zámky. Plný Redis s
`noeviction` odmítne zápis, gateway to vyhodnotí jako nedostupný store a vrací **503**
(fail closed), nikdy nepustí požadavek bez kontroly.

**Login:** pořadí Origin → `application/json` → velikost → validace těla (400) → IP limit
20/5 min (klíč vzniká až po validaci) → limit neúspěchů na e-mail 10/15 min. Pokus se na
e-mail započítá atomicky **před** voláním core (souběžné pokusy limit nepřeskočí) a odečte
se, když neskončí špatnými údaji (úspěch, 429/5xx/výpadek core).

**Expirace:** při idle nebo absolutní expiraci gateway session smaže (`session_expired`)
a na pozadí zavolá core `POST /api/v1/auth/logout` s tokeny ze záznamu (best effort,
neblokuje požadavek).

**Odhlásit všude:** když core některou revokaci nepotvrdí, gateway své sessions i cookie
stejně zruší a vrátí 502 `{"detail":"Logout on other devices was not confirmed.","code":"LOGOUT_ALL_PARTIAL","requestId":…}`.

**Bezpečnostní události** (`login_success`, `login_failure`, `logout`, `logout_all`,
`session_expired`, `session_revoked`, `csrf_failure`, `origin_failure`,
`allowlist_miss`, `rate_limited`, `upstream_unavailable`) jdou okamžitě do
strukturovaného logu (JSON na stdout, `msg = "SECURITY_EVENT"`). Na pozadí se po
dávkách max 50 kusů posílají na `POST /api/v1/internal/security-events`
(podepsaně, bez `Authorization`). Když odeslání selže přechodně (síť, 5xx, 401, 429),
dávka se vrátí do fronty (max 10 000 položek); při 429 se další odeslání odloží podle
`Retry-After` (max 300 s). Jiná 4xx dávku zahodí, záznam zůstává v logu. Při plné frontě
se zahazují jen nízkoprioritní `allowlist_miss` a `rate_limited` (ty se také zahodí po
3 neúspěšných pokusech o doručení), nikdy `login_*`, `session_*`, `logout*`,
`csrf_failure` ani `origin_failure`. `rate_limited` je agregovaná stejně jako `allowlist_miss`.
Odesílání nikdy neblokuje požadavek uživatele.

**Hlavičky odpovědí gateway:** `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Cache-Control: no-store`
(vlastní odpovědi gateway včetně `/bff/auth/*` a `/bff/session`; u proxy, když ho core neposlal).
U SSE navíc `X-Accel-Buffering: no`.

**Co gateway nedělá:** nerozhoduje o oprávnění (to dělá jen core: exposure matrix, JWT `aud`, RBAC, izolace firem), nepovoluje CORS a nevydává tokeny.
