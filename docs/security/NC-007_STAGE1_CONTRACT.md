# NC-007 – Etapa 1: kontrakt mezi Gateway, Core, Webem a provozem

| | |
|---|---|
| **Datum** | 22. 10. 2026 |
| **Větev** | `feat/nc-007-secure-web-platform` (z `fix/n9-orm-migration-parity` 04076a1) |
| **Navazuje na** | [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md) kap. 4–5 · [GATEWAY_CORE_CONTRACT.md](GATEWAY_CORE_CONTRACT.md) · [API_EXPOSURE_MATRIX.md](API_EXPOSURE_MATRIX.md) kap. 1 a 11 · [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) F4.1–F4.6, F4.8 |
| **Rozsah** | Vše, co jde udělat **bez databázové migrace**. MFA, pozvánky, ověření e-mailu, obnova hesla a vynucená změna hesla patří do etapy 2 (vyžaduje schválení migrací). |

Tento dokument je závazná dohoda mezi paralelně pracujícími rolemi. Kdo potřebuje kontrakt změnit, změní nejdřív tento dokument.

## 1. Vlastnictví souborů (paralelní práce)

| Role | Smí měnit | Nesmí měnit |
|---|---|---|
| **Gateway** | `src/gateway/**` | cokoli jiného |
| **Core (soubory + bezpečnostní události)** | `src/backend/**`, `src/contracts/**`, `docs/security/gateway-allowlist.json`, `docs/security/API_EXPOSURE_MATRIX.md` | `src/gateway`, `src/frontend`, `deploy` |
| **Frontend** | `src/frontend/**` | cokoli jiného (vygenerované typy přegeneruje až koordinátor po Core) |
| **DevOps** | `deploy/**`, `docker-compose*.yml` | aplikační kód |

## 2. Veřejné endpointy gateway (edge, stejný origin jako SPA)

Všechny odpovědi jsou JSON. Chyba má tvar `{"detail": "<obecná zpráva>", "requestId": "<id>"}`. Interní důvod jde jen do logu.

| Metoda | Cesta | Session | CSRF | Volá core | Odpověď |
|---|---|---|---|---|---|
| GET | `/bff/health` | ne | ne | nic | `{"status":"ok"}` (nic o core) |
| POST | `/bff/auth/login` | ne | ne (Origin ano) | `POST /api/v1/auth/login` | 200 `{"user": AuthUserRead, "csrfToken": "…"}` + `Set-Cookie`; 401 jednotně `{"detail":"Invalid credentials."}` |
| POST | `/bff/auth/logout` | ano | ano | `POST /api/v1/auth/logout` | 204, `Set-Cookie` s `Max-Age=0` (i když core neodpoví) |
| POST | `/bff/auth/logout-all` | ano | ano | `GET /api/v1/auth/sessions` + `DELETE /api/v1/auth/sessions/{id}` pro všechny + `POST /api/v1/auth/logout` | 204; gateway smaže **všechny** své sessions uživatele |
| GET | `/bff/session` | volitelně | ne | `GET /api/v1/auth/me` | 200 `{"authenticated": true, "user": AuthUserRead, "csrfToken": "…", "expiresAt": iso, "idleExpiresAt": iso}` nebo 200 `{"authenticated": false}` |
| * | `/bff/api/<cesta>` | ano | u mutací | `/api/v1/<cesta>` | odpověď core (viz 4) |

Vše ostatní na gateway vrací **404**: `/api/*`, `/docs`, `/openapi.json`, `/metrics`, `/admin*`.

### 2.1 Průchozí allowlist `/bff/api`

- Zdroj: `docs/security/gateway-allowlist.json` (generuje `python -m scripts.export_gateway_allowlist` z `exposure.py`, zóna `gateway`). Gateway ho načte při startu. Chybějící, nečitelný nebo prázdný soubor znamená, že proces nenastartuje.
- Průchozí množina = allowlist **minus** cesty pod `/api/v1/auth/` a `/api/v1/internal/`. Ty volá jen gateway ze svých handlerů, prohlížeč je nedostane ani se session.
- Shoda je (METODA, šablona). Parametr šablony odpovídá jednomu segmentu `[A-Za-z0-9._~-]{1,128}`. Segmenty `.`, `..`, prázdné segmenty, `%2F`, `%5C`, `%00` a zpětná lomítka znamenají 404.
- Metoda `HEAD`, `OPTIONS`, `TRACE` a `CONNECT` znamená 404 (CORS se nepovoluje).

## 3. Session a cookie

| Prvek | Hodnota |
|---|---|
| Cookie | `__Host-nc_sid`, 32 B z `secrets.token_urlsafe`, `HttpOnly; Secure; SameSite=Strict; Path=/`, bez `Domain`, bez `Max-Age` (session cookie) |
| Vývoj přes http | jen `NC_ENV=development` + explicitní `NC_BFF_DEV_INSECURE_COOKIE=1`: jméno `nc_sid_dev`, bez `Secure`. Mimo development proces s touto volbou **nenastartuje**. |
| Store | Redis, klíč `nc:bff:sess:<sha256(sid) hex>`, hodnota AES-256-GCM (klíč `NC_BFF_SESSION_KEYS` = `kid:base64(32 B)[,…]`, první šifruje, ostatní jen dešifrují), AAD = klíč záznamu. Index uživatele `nc:bff:user:<user_id>` (set hashů). |
| Obsah | access a refresh JWT z core, `userId`, `organizationId`, `role`, `csrfSecret`, `createdAt`, `lastSeenAt`, `ipHash`, `uaHash`, `coreSessionId` (pokud je v JWT `sid`) |
| Platnost | idle 30 min (`NC_BFF_IDLE_TIMEOUT_SECONDS`), absolutně 12 h (`NC_BFF_ABSOLUTE_TIMEOUT_SECONDS`). Absolutní limit se obnovou neprodlužuje. |
| Fixation | při přihlášení se vždy vytvoří **nové** `sid`, příchozí cookie se ignoruje a její záznam se smaže |
| Obnova access tokenu | gateway volá `POST /api/v1/auth/refresh`, když do expirace access tokenu zbývá < 60 s, nebo po 401 z core (jednou, se zámkem `nc:bff:lock:<hash>`). Při neúspěchu session zahodí → 401 klientovi. |
| Revokace | core 401 na access i refresh = session smazána, cookie zrušena |
| Redis nedostupný | **503**, fail closed. Žádná paměťová náhrada. |

## 4. Povinné kontroly na `/bff/api` (pořadí)

1. allowlist → jinak 404 + bezpečnostní událost `allowlist_miss`,
2. velikost těla: JSON max 256 KiB, `multipart/form-data` max 25 MiB a jen na routách s nahráváním (`POST …/images`, `POST …/upload*`, konfigurovatelný seznam) → jinak 413,
3. `Content-Type` u těla jen `application/json` nebo `multipart/form-data` → jinak 415,
4. session → jinak 401,
5. u `POST/PUT/PATCH/DELETE`: `Origin` přesně rovný `NC_BFF_PUBLIC_ORIGIN` (chybějící Origin → `Sec-Fetch-Site: same-origin`, jinak 403) a `X-CSRF-Token` rovný `csrfSecret` (`hmac.compare_digest`) → jinak 403 + `csrf_failure`/`origin_failure`. Tělo je pevné: CSRF `{"detail":"CSRF validation failed.","code":"CSRF_FAILED","requestId":…}`, Origin `{"detail":"Origin not allowed.","code":"ORIGIN_REJECTED","requestId":…}`. Web opakuje požadavek jen u `CSRF_FAILED`,
6. rate limit (Redis): na session 300/min, na IP 600/min; `/bff/auth/login` IP 20/5 min a e-mail 10 neúspěchů/15 min → 429 + `Retry-After` + `rate_limited`,
7. hlavičky do core: jen `Content-Type`, `Accept`, `If-None-Match`, `Range`, `If-Range`. Gateway nastaví `Authorization: Bearer <access>`, `X-Request-Id` a hlavičky `X-NC-*` podle [GATEWAY_CORE_CONTRACT.md](GATEWAY_CORE_CONTRACT.md). Adresu klienta bere **jen** ze spojení (`NC_BFF_TRUSTED_PROXY`: přesně jedna adresa lokálního nginx; `X-Forwarded-For` se čte jen tehdy, když spojení přichází z této adresy, a použije se poslední hodnota),
8. odpověď core se streamuje beze změny těla, bez bufferování. U `text/event-stream` (SSE `/cases/{case_id}/activity/stream`) neplatí krátký read timeout (jen idle limit spojení, výchozí 300 s). Hlavičky jen z allowlistu: `Content-Type`, `Content-Length`, `Content-Disposition`, `Content-Range`, `Accept-Ranges`, `ETag`, `Last-Modified`, `Cache-Control`, `Retry-After`, `X-Request-Id`. 5xx se nahradí `{"detail":"Upstream error.","requestId":…}` se stejným kódem. Core nedostupný → 502.

## 5. Gateway → core

- Spojení: `NC_BFF_CORE_URL` (např. `http://10.77.0.1:8101` přes WG, nebo `http+unix://` v jednoserverové variantě). Podpis HMAC přesně podle [GATEWAY_CORE_CONTRACT.md](GATEWAY_CORE_CONTRACT.md) kap. 3, klíč `NC_GATEWAY_HMAC_KEY` ve tvaru `kid:secret`. Gateway musí projít testovacím vektorem z kap. 5.
- Gateway **nemá** `JWT_SECRET_KEY` a JWT nikdy neověřuje ani nevyrábí. `exp` access tokenu čte jen jako nápovědu pro obnovu (bez ověření podpisu, nikdy pro autorizaci).
- Bezpečnostní události posílá dávkově na `POST /api/v1/internal/security-events` (viz 6). Selhání odeslání se zaloguje a request uživatele neblokuje.

## 6. Nové endpointy core (aditivní)

### 6.1 `GET /api/v1/files/images/{image_id}/{variant}` (zóny G, D)

- `variant` ∈ `original`, `preview`, `ai-input`; jiná hodnota → 404.
- Oprávnění: přihlášený uživatel, fotka musí patřit jeho firmě a nesmí být smazaná (soft delete) ani purgnutá. Cizí firma, smazaná fotka i neexistující fotka vrací stejné **404**. Varianta, která ještě není hotová, vrací 404.
- Streamuje z aktivního úložiště po blocích (výchozí 64 KiB), žádné přesměrování a žádná URL úložiště.
- `Range: bytes=a-b` → 206 + `Content-Range`; neplatný rozsah → 416. `Accept-Ranges: bytes`.
- Hlavičky: `Content-Type` z uloženého MIME (allowlist `image/jpeg`, `image/png`, `image/webp`, `image/heic`; jinak `application/octet-stream`), `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`, `Content-Security-Policy: default-src 'none'; sandbox`, `Content-Disposition: inline; filename="<bezpečné jméno>"` (u `original` `attachment`).
- Klíč úložiště se bere jen z DB, nikdy z požadavku. Úložiště odmítne klíč s `..`, absolutní cestou nebo zpětným lomítkem.

### 6.2 `GET /api/v1/files/exports/{export_id}` (zóny G, D)

- Role podle dnešní matice exportů (stejná kontrola jako `GET /exports/{id}`). Jen `status=completed`, neexpirovaný a nesmazaný export, jinak 404.
- Streamování, `Range`, stejné bezpečnostní hlavičky, `Content-Disposition: attachment`.
- Audit: `export.downloaded` (uživatel, firma, export, IP).

### 6.3 Tvar polí URL v odpovědích se nemění, mění se hodnota

- `ProjectPhotoRead.url`, `variants.*.url` → `/api/v1/files/images/{id}/{variant}` (relativní cesta, `null` beze změny pravidel).
- `ExportRead.downloadUrl` → `/api/v1/files/exports/{id}`.
- Žádná odpověď API už neobsahuje URL úložiště (`X-Amz-`, `:9000`, `/storage/`). Ověřuje test.
- Desktop relativní cestu už dnes skládá s kořenem API a posílá `Authorization` (`resolveApiUrl` v `imagesapi.cpp` a `exportsapi.cpp`). Web převádí prefix `/api/v1/` na `/bff/api/`.
- Interní použití podepsaných URL (AI pipeline, offer worker) tato etapa nemění. Je to F4.7, navazující task.

### 6.4 `POST /api/v1/internal/security-events` (jen zóna G)

- Vyžaduje platný podpis gateway (jako vše v zóně G) **a zároveň nesmí mít hlavičku `Authorization`**. Požadavek s ní dostane 404, takže se na endpoint nedá dostat s uživatelským tokenem.
- Tělo: `{"events": [{"type": "...", "occurredAt": iso, "clientIp": "…", "userId": "…"|null, "organizationId": "…"|null, "sessionRef": "<prvních 16 hex sha256(sid)>"|null, "requestId": "…"|null, "detail": {…}}]}`, max 50 událostí, `detail` max 2 KiB po serializaci.
- `type` ∈ `login_success`, `login_failure`, `logout`, `logout_all`, `session_expired`, `session_revoked`, `csrf_failure`, `origin_failure`, `allowlist_miss`, `rate_limited`, `upstream_unavailable`. Jiný typ → 422.
- Zápis do `audit_logs`: `action = "gateway.<type>"`, `resource_type = "web_session"`, `ip`, `user_id`, `org_id`, `detail`. Bez migrace (tabulka to unese).
- Odpověď 202 `{"accepted": n}`. Limit 120/min na klíč gateway.

## 7. Web (SPA)

- Žádný token v JS, `localStorage` ani `sessionStorage`. Klient volá jen `/bff/*` s `credentials: "same-origin"`.
- CSRF token se drží jen v paměti (z `GET /bff/session` nebo z odpovědi loginu) a posílá se jako `X-CSRF-Token` u mutací.
- 401 z `/bff/api` → stav „odhlášeno“ a přesměrování na login. 403 s CSRF chybou → jednou znovu načíst `/bff/session` a požadavek zopakovat.
- Odhlášení a „odhlásit všude“ jsou v UI.
- Odstraněno: `pages/Admin*`, `features/impersonation` a admin routy (D-11). Stránky obnovy hesla se v etapě 1 nezobrazují (core vrací 410, žádné falešné akce). Vrátí se v etapě 2.
- Vizuální redesign je **BLOCKED**: v repozitáři není HTML mockup, je jen `design/NovuBuilder.png`. Etapa 1 mění jen funkční a bezpečnostní vrstvu a stávající vzhled.

## 8. Provoz

- `nc-gateway.service` (systemd, uživatel `nc-gateway`, bez přístupu k `/etc/novuconstruct/secrets` core). Credentials `NC_GATEWAY_HMAC_KEY` a `NC_BFF_SESSION_KEYS` přes `LoadCredential`. Redis gateway je **oddělený** od Redisu core (vlastní instance nebo ACL uživatel s prefixem `nc:bff:*`).
- nginx edge: `/bff/` → gateway, `/` → statické soubory SPA s CSP (SECURITY_ARCHITECTURE 4.7), `/api/`, `/docs`, `/openapi.json`, `/metrics`, `/admin` → 404. `server_tokens off`.
- Gateway odmítne start mimo development, když chybí kterákoli povinná proměnná, klíč je kratší než 32 B, `NC_BFF_PUBLIC_ORIGIN` není `https://…` nebo chybí allowlist.

## 9. Mimo etapu 1 (etapa 2, vyžaduje schválení migrací)

TOTP MFA a recovery kódy, `POST /auth/login/start` + `/auth/login/mfa`, re-autentizace citlivých operací, MFA politika firmy, pozvánky a ověření e-mailu, obnova hesla e-mailem (D-05), vynucená změna hesla po admin resetu, SMTP adaptér.
