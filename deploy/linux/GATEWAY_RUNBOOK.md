# Web Gateway (BFF) – provozní runbook

| | |
|---|---|
| **Kontrakt** | [NC-007_STAGE1_CONTRACT.md](../../docs/security/NC-007_STAGE1_CONTRACT.md) kap. 2–5 a 8 · [GATEWAY_CORE_CONTRACT.md](../../docs/security/GATEWAY_CORE_CONTRACT.md) · [SECURITY_ARCHITECTURE.md](../../docs/security/SECURITY_ARCHITECTURE.md) kap. 4.7, 6, 8 |
| **Stav** | Připraveno a ověřeno staticky (`tests/validate-configs.sh`). **Nenasazeno.** |
| **Kde běží** | Varianta A: edge server. Varianta B (pilot): stejný server jako core, ale vlastní uživatel, vlastní Redis, vlastní target. |

Všechny příkazy se spouštějí jako root. `P=/opt/novuconstruct/deploy/linux/provision/nc-provision`, `G=/opt/novuconstruct/deploy/linux/bin/nc-gen-secrets`.

## 1. Jak to je poskládané

```
prohlížeč ──443──► nginx (nc-edge-webapp.conf)
                     ├─ /            → /var/www/novuconstruct/app (SPA, CSP bez unsafe-*)
                     ├─ /bff/        → 127.0.0.1:8300  nc-gateway.service (uživatel nc-gateway)
                     │                    ├─ session store: nc-gateway-redis.service
                     │                    │    unix socket /run/nc-gateway-redis/redis.sock, ACL ~nc:bff:*
                     │                    └─ core: A http://10.50.0.1:8200 (WG) │ B http://127.0.0.1:8200
                     └─ /api/ /docs /openapi.json /metrics /admin → 404
```

| Co | Kde | Práva |
|---|---|---|
| Konfigurace (bez secrets) | `/etc/nc-gateway/gateway.env` (+ vlastní úpravy v `gateway.env.local`) | `0640 root:nc-gateway` |
| Secrets gateway | `/etc/nc-gateway/secrets/{NC_GATEWAY_HMAC_KEY, NC_BFF_SESSION_KEYS, NC_BFF_REDIS_URL, REDIS_GATEWAY_PASSWORD}` | adresář `0700 root:root`, soubory `0600 root:root`; čte je jen systemd (`LoadCredential`) |
| ACL Redisu gateway | `/etc/nc-gateway-redis/users.acl` (credential jednotky Redis) | `0600 root:root` |
| Konfigurace Redisu gateway | `/etc/nc-gateway-redis/redis.conf` | `0644`, bez secrets |
| Data Redisu gateway | `/var/lib/nc-gateway-redis` (jen šifrované sessions) | `0700 nc-gw-redis` |
| Secrets core | `/etc/novuconstruct/secrets` | `nc-gateway` do nich nevidí (není ve skupině `novuconstruct`, jednotka je má navíc v `InaccessiblePaths`) |

### Proč vlastní Redis

Zvolena **samostatná instance** (`nc-gateway-redis.service`), ne ACL uživatel v Redisu core:

- Varianta A ho potřebuje tak jako tak (edge nemá Redis core). Varianta B se tak od A neliší a přechod A↔B nic nemění.
- Gateway nemá síťovou cestu k Redisu core vůbec: Redis gateway nemá TCP port (`port 0`, `PrivateNetwork=yes`), socket má skupinu `nc-gw-redis`, kde je jen `nc-gateway`. Kompromitovaná gateway tak nemůže ani zkoušet hesla proti Redisu core, ani zahltit jeho paměť (fronty a limity core mají `noeviction`).
- Restart nebo vyčištění session store neovlivní core (fronta jobů, nonce HMAC, rate limit core).
- ACL i tak: `default` vypnutý, `nc-gateway` smí jen klíče `nc:bff:*`, bez `@dangerous` (FLUSHALL, KEYS, CONFIG, DEBUG, ACL, SHUTDOWN) a bez pub/sub.

Cena: jeden proces Redis navíc (~10 MB RAM, limit 128 MB).

## 2. Instalace

### 2.1 Varianta B (jeden server, pilot)

1. `/etc/novuconstruct/provision.conf`: `NC_ENABLE_GATEWAY_ZONE=1`, `NC_ENABLE_GATEWAY=1`, `NC_APP_DOMAIN=app.<doména>`, `NC_DOMAIN=<doména>`.
2. `$P install` – založí účty `nc-gateway` a `nc-gw-redis`, vygeneruje secrets gateway (klíč HMAC zkopíruje z `NC_GATEWAY_HMAC_KEYS` core), připraví venv, `gateway.env`, jednotky, Redis gateway a nginx. **Nic nespustí.**
3. `$P tls` – certifikát pro `NC_DOMAIN` i `NC_APP_DOMAIN`.
4. SPA: obsah `src/frontend/dist` zkopírovat do `/var/www/novuconstruct/app` (vlastník root, `0755`/`0644`).
5. `$P start` – mimo jiné spustí `nc-api@gateway` (zóna gateway na core).
6. `NC_CONFIRM_GATEWAY=1 $P gateway` – kontroly (secrets, allowlist, venv, doména, vhost), pak `enable` + start `nc-gateway-redis`, `nc-gateway` a `nc-edge.target`, čekání na `/bff/health`, `nginx -t` a reload.
7. `$P smoke`.
8. `$P firewall` – pravidla `nc-single-server.nft` obsahují i pravidla gateway (8300 jen pro nginx, 127.0.0.1:8200 jen pro `nc-gateway`).

### 2.2 Varianta A (dva servery)

Core: `NC_VARIANT=core`, `NC_ENABLE_GATEWAY_ZONE=1`, `$P install`, `$P start` (nginx zóny gateway na `10.50.0.1:8200`, jen peer `10.50.0.2`).

Edge: `NC_VARIANT=edge`, `NC_ENABLE_GATEWAY=1`, `NC_APP_DOMAIN=…`, `$P install`. Instalátor vypíše varování, že chybí `NC_GATEWAY_HMAC_KEY`, protože klíč vzniká na core. Předání jde jen přes admin kanál (SSH ve `wg-nc-admin` / `wg-edge-admin`), nikdy e-mailem ani chatem:

```sh
# na core: vypíše JEDEN záznam kid:secret (nejnovější); nikam ho neukládej
$G --export-gateway-hmac
# na edge: hodnotu vlož na stdin (ne jako argument – byla by vidět v `ps` a historii)
$G --gateway --hmac-stdin
```

Pak na edge kroky 3, 4, 6, 7 a 8 z varianty B (`nc-edge.nft`).

## 3. Rotace klíče HMAC gateway (90 dní, bez výpadku)

Podle [GATEWAY_CORE_CONTRACT.md](../../docs/security/GATEWAY_CORE_CONTRACT.md) kap. 7:

1. **Core:** přidat nový klíč a restartovat zónu gateway (core teď přijímá starý i nový):
   ```sh
   $G --add-gateway-hmac
   systemctl restart nc-api@gateway
   ```
2. **Gateway přepnout na nový klíč:**
   - B: `$G --gateway --hmac-from-core` (vezme nejnovější záznam core),
   - A: `$G --export-gateway-hmac` na core → `$G --gateway --hmac-stdin` na edge.

   Pak `systemctl restart nc-gateway`.
3. Ověřit, že v logu core není `gateway_signature_rejected reason=unknown_key` a že `/bff/session` funguje.
4. **Core:** odebrat starý klíč. Kid je část před dvojtečkou, vypíšeš ho bez hodnoty: `tr ',' '\n' < /etc/novuconstruct/secrets/NC_GATEWAY_HMAC_KEYS | cut -d: -f1`.
   ```sh
   $G --drop-gateway-hmac <starý-kid>
   systemctl restart nc-api@gateway
   ```

Při podezření na kompromitaci gateway se krok 1 vynechá: nový klíč, okamžitě odebrat starý, restart core, pak gateway (SECURITY_ARCHITECTURE kap. 6). Navíc zneplatnit WG klíč edge a provést kap. 5.

## 4. Rotace session klíčů (`NC_BFF_SESSION_KEYS`)

Formát `kid:base64(32 B)[,kid:base64(32 B)]`. První klíč šifruje, ostatní jen dešifrují.

**Plánovaná rotace (uživatelé zůstanou přihlášení):**
```sh
$G --gateway --rotate-session-key      # nový klíč první, dosavadní první zůstane jen pro dešifrování
systemctl restart nc-gateway
```
Starší klíče se zahodí. Session žije nejvýš 12 h, takže dva klíče pokryjí rotaci v intervalu ≥ 12 h. Rotovat znovu dřív než za 12 h by odhlásilo sessions zašifrované nejstarším klíčem.

**Heslo Redisu gateway:** `$G --gateway --rotate-redis-password` a `systemctl restart nc-gateway-redis nc-gateway`.

## 5. Odhlášení všech webových sessions

Desktop a NovuAdmin se to netýká (nepoužívají gateway).

**a) Okamžitě a bez závislosti na Redisu – zneplatnit šifrovací klíč:**
```sh
$G --gateway --revoke-session-keys     # jediný nový klíč, staré zahozeny
systemctl restart nc-gateway
```
Žádný existující záznam už nejde dešifrovat. Gateway takovou session zahodí a vrátí 401.

**b) Smazat záznamy v Redisu (uklidí i indexy uživatelů a zámky):**
```sh
export REDISCLI_AUTH="$(cat /etc/nc-gateway/secrets/REDIS_GATEWAY_PASSWORD)"
redis-cli --no-auth-warning -s /run/nc-gateway-redis/redis.sock --user nc-gateway \
  --scan --pattern 'nc:bff:sess:*' | xargs -r -n 500 redis-cli --no-auth-warning \
  -s /run/nc-gateway-redis/redis.sock --user nc-gateway unlink
# totéž pro 'nc:bff:user:*' a 'nc:bff:lock:*'; ostatní klíče nc:bff:* (rate limity) nech být
unset REDISCLI_AUTH
```
`FLUSHALL` uživatel `nc-gateway` nesmí, a to záměrně.

**Při kompromitaci** udělej obojí a navíc zneplatni refresh tokeny v core, protože gateway je mohla vynést: `token_version++` u uživatelů s webovou session (SECURITY_ARCHITECTURE kap. 6). Pak rotuj klíč HMAC (kap. 3, bez kroku 1).

Jednoho uživatele odhlásí jeho vlastní „Odhlásit všude“ (`/bff/auth/logout-all`). Ručně: členy množiny `nc:bff:user:<user_id>` (hashe) smazat jako `nc:bff:sess:<hash>`, pak smazat i množinu.

## 6. Diagnostika

| Příznak | Kde hledat |
|---|---|
| `nc-gateway` nenaběhne | `journalctl -u nc-gateway -b`. Gateway mimo development odmítne start, když chybí proměnná, klíč je < 32 B, origin není `https://` nebo chybí allowlist. Credentials: `systemctl show nc-gateway -p LoadCredential`, existence souborů v `/etc/nc-gateway/secrets`. |
| `/bff/*` vrací 502 z nginx | gateway neběží: `systemctl status nc-gateway`, `curl -s http://127.0.0.1:8300/bff/health`. |
| `/bff/api/*` vrací 502 z gateway | core nedostupný: B `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8200/api/v1/health` jako root (čekej **401**, protože požadavek není podepsaný); A totéž na `10.50.0.1:8200` z edge + `wg show wg-nc`. `systemctl status nc-api@gateway` na core. |
| core loguje `gateway_signature_rejected reason=…` | `unknown_key`: gateway má kid, který core nezná (kap. 3). Jiný důvod: zkontroluj čas na obou stranách (`timedatectl`, okno ±30 s) a to, že nic mezi gateway a core nemění cestu, query, tělo ani `Authorization` (nginx core musí používat `nc-proxy-gateway.conf`). |
| 503 ze všech `/bff/` s session | Redis gateway: `systemctl status nc-gateway-redis`, `journalctl -u nc-gateway-redis`. Plná paměť (`noeviction`) = 503 záměrně (fail closed). |
| 401 hned po přihlášení | cookie `__Host-nc_sid` vyžaduje HTTPS a přesný origin: `NC_BFF_PUBLIC_ORIGIN` v `gateway.env` musí být přesně `https://<NC_APP_DOMAIN>`. |
| 403 u mutací | Origin / CSRF: `journalctl -u nc-gateway \| grep -E 'csrf_failure\|origin_failure'`. Proxy nebo CDN před nginx, které mění `Origin`, nejsou podporované. |
| SPA se nenačte, chyby CSP v konzoli | build nesmí obsahovat inline skripty ani styly. CSP se **neuvolňuje** (`unsafe-*` je zakázané, hlídá ho `validate-configs.sh`). |
| 413 | nginx: JSON 256 KiB, login 16 KiB, upload (`…/images`, `…/upload*`) 25 MiB. Přesné limity drží gateway. |

Rychlá kontrola izolace na serveru:
```sh
$P smoke                                                     # služby, 404 na edge, CSP, ACL Redisu, práva
runuser -u nc-gateway -- cat /etc/novuconstruct/secrets/JWT_SECRET   # musí selhat
systemd-analyze security nc-gateway                          # cíl < 3.0
ss -ltnp | grep -E ':(8300|8200) '                           # 8300 jen 127.0.0.1; 8200 jen WG / 127.0.0.1
```

Logy nginx aplikace jsou bez query stringů: `/var/log/nginx/nc-app.access.log`.

## 7. Vypnutí gateway

```sh
systemctl disable --now nc-gateway nc-gateway-redis nc-edge.target
```
nginx pak na `/bff/` vrací 502 a SPA se nepřihlásí. Pro úplné stažení webu odeber `/etc/nginx/conf.d/nc-edge-webapp.conf` a `systemctl reload nginx`.
