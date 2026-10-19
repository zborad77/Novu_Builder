# Kontrakt Gateway ↔ Private Core (F3.4)

| | |
|---|---|
| **Datum** | 17. 10. 2026 |
| **Stav** | Implementováno v core (`app/platform/http/gateway_auth.py`), nenasazeno. Gateway (F4) ho bude implementovat podle tohoto dokumentu. |
| **Navazuje na** | [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md) kap. 3, 4.5 a 6 · [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) F3.4 · [API_EXPOSURE_MATRIX.md](API_EXPOSURE_MATRIX.md) |

## 1. Co kontrakt zaručuje

| Otázka | Odpověď core | Kde |
|---|---|---|
| **Kdo volá?** | Jen držitel klíče gateway. Instance `nc-api@gateway` bez platného podpisu odpoví **401** na *každý* požadavek, a to ještě před exposure guardem. Nepodepsaný volající tak nezjistí ani to, které routy existují. | `GatewaySignatureMiddleware` |
| **Odkud požadavek pochází?** | Adresu klienta (pro audit a rate limit) bere core **jen** z podepsané `X-NC-Client-IP`. `X-Forwarded-For`, `X-Real-IP`, `Forwarded` i `X-Forwarded-Proto` instance gateway odstraní a nečte. | dtto |
| **Je požadavek nezměněný a jednorázový?** | Podpis pokrývá metodu, cestu, query, tělo (SHA-256), `Authorization` (SHA-256), adresu klienta, čas a nonce. Okno je ±30 s. Nonce jde použít jen jednou (Redis `SET NX`, sdílené mezi workery). | dtto |
| **Co smí?** | O oprávnění rozhoduje **jen** core: exposure matrix (zóna `gateway`, deny-by-default), JWT `aud=nc-web`, RBAC a izolace firem. Podpis potvrzuje původ, nikdy neuděluje práva. | `exposure.py`, `auth_service`, `rbac.py` |
| **Co ostatní zóny?** | `desktop`, `admin` a `dev` hlavičky `X-NC-*` zahodí (aplikace i nginx). Podvržená `X-NC-Client-IP` nemá nikde žádný účinek. | middleware + `nginx/snippets/nc-proxy.conf` |

Zóna je vlastnost procesu (`NC_ZONE`). Klíče mají jen instance `nc-api@gateway` (systemd drop-in `nc-api@gateway.service.d/10-gateway-hmac.conf`).

## 2. Hlavičky

Gateway posílá na každém požadavku právě jeden výskyt každé hlavičky:

| Hlavička | Formát | Význam |
|---|---|---|
| `X-NC-Gateway-Key` | `[A-Za-z0-9._-]{1,32}` | id klíče (rotace) |
| `X-NC-Gateway-Ts` | unixový čas v sekundách, jen číslice | čas podpisu |
| `X-NC-Gateway-Nonce` | `[A-Za-z0-9_-]{16,128}` | jednorázová hodnota, např. 24 B náhodných dat v base64url |
| `X-NC-Client-IP` | IPv4 nebo IPv6 v **kanonickém** tvaru (`str(ipaddress.ip_address(x))`, IPv4-mapped IPv6 jako IPv4) | adresa prohlížeče, jak ji vidí edge |
| `X-NC-Gateway-Sig` | 64 hex znaků malými písmeny | `HMAC-SHA256(secret, canonical)` |

Dvojí výskyt kterékoli z nich, nebo dvojí `Authorization`, vrací 401.

## 3. Kanonický řetězec

Deset polí oddělených `\n` (bez koncového `\n`), kódování UTF-8:

```
NC-GW-1
<X-NC-Gateway-Key>
<X-NC-Gateway-Ts>
<X-NC-Gateway-Nonce>
<METODA velkými písmeny>
<cesta přesně tak, jak jde v HTTP požadavku na core, bez query (percent-encoding beze změny)>
<query string bez úvodního ?, beze změny (prázdný řetězec, když chybí)>
<X-NC-Client-IP>
<sha256 hex těla požadavku (prázdné tělo = e3b0c442…b855)>
<sha256 hex hodnoty hlavičky Authorization (chybějící = sha256 prázdného řetězce)>
```

Gateway podepisuje přesně ty bajty, které odešle. Mezi gateway a core nesmí nic měnit cestu, query, tělo ani `Authorization`. nginx core proto pro zónu gateway používá `snippets/nc-proxy-gateway.conf`.

## 4. Odpovědi core

| Situace | Kód | Tělo |
|---|---|---|
| chybí podpis, neznámý klíč, špatný formát, mimo časové okno, neplatný podpis, opakované nonce | 401 | `{"detail": "Invalid gateway signature."}` |
| tělo větší než `NC_GATEWAY_MAX_BODY_BYTES` (výchozí 26 MiB) | 413 | |
| úložiště nonce (Redis) nedostupné | 503 | (fail closed) |
| podpis platný, route mimo zónu gateway | 404 | běžné chování exposure guardu |

Důvod odmítnutí jde jen do logu: `SECURITY_EVENT: gateway_signature_rejected reason=…`. Klientovi se nevrací.

Nonce se spotřebuje až po ověření podpisu. Nepodepsané požadavky tak nemohou zablokovat nonce, které gateway teprve použije.

## 5. Testovací vektor

Gateway (samostatný adresář `gateway/`, D-02, bez importu z `python-backend`) musí pro tyto vstupy dát stejný podpis. Kontroluje to `tests/test_f34_gateway_signature.py::test_signature_matches_the_published_test_vector`.

| Pole | Hodnota |
|---|---|
| key id | `gw-test` |
| secret | `0123456789abcdef0123456789abcdef` (ASCII bajty) |
| ts | `1792224000` |
| nonce | `AAAAAAAAAAAAAAAAAAAAAAAA` |
| metoda, cesta, query | `POST`, `/api/v1/org/users`, prázdná |
| client IP | `203.0.113.10` |
| tělo | `{"email":"novak@firma.cz"}` |
| Authorization | `Bearer eyJ.test.token` |
| **X-NC-Gateway-Sig** | `834a1b955a9ac25a806c4c77dc4eeda33381fa89c2633ca6d9791251d80ef91f` |

## 6. Konfigurace

| Proměnná | Kde | Výchozí |
|---|---|---|
| `NC_GATEWAY_HMAC_KEYS` | `kid:secret[,kid:secret]`, secret ≥ 32 znaků. Přes `LoadCredential` jen pro `nc-api@gateway`. Mimo development je pro `NC_ZONE=gateway` povinná, jinak proces nenastartuje. | – |
| `NC_GATEWAY_SIG_MAX_SKEW_SECONDS` | okno platnosti podpisu (5–300) | 30 |
| `NC_GATEWAY_MAX_BODY_BYTES` | strop těla. Core tělo před handlerem celé načte a zahashuje. | 26 MiB |

Generování: `deploy/linux/bin/nc-gen-secrets` zapíše `/etc/novuconstruct/secrets/NC_GATEWAY_HMAC_KEYS` ve tvaru `gw-<RRRRMMDD>:<64 hex>` (0640 root:novuconstruct). Stejnou hodnotu dostane gateway.

## 7. Rotace klíče (90 dní, bez výpadku)

1. Na core připojit nový klíč: `gw-old:…,gw-new:…`, pak `systemctl restart nc-api@gateway`.
2. Gateway přepnout na podepisování klíčem `gw-new`.
3. Po ověření (žádné `reason=unknown_key` v logu) starý klíč z core odebrat a znovu restartovat.

Při podezření na kompromitaci gateway se postupuje podle runbooku v [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md) kap. 6: klíč gateway odebrat okamžitě, bez kroku 1.

## 8. Co kontrakt neřeší

- **Autorizaci uživatele.** Platí jen JWT, RBAC a izolace firem.
- **Kompromitaci samotné gateway.** Útočník s klíčem gateway může podepsat cokoli z allowlistu zóny gateway, ale stále jen s platným uživatelským tokenem `nc-web`. Viz SECURITY_ARCHITECTURE kap. 6.
- **Šifrování přenosu.** To zajišťuje WireGuard, v jednoserverové variantě unix socket s právy jen pro nginx.
