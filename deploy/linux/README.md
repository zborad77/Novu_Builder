# NovuConstruct – nasazení bez Dockeru (Ubuntu/Debian + systemd + nginx + WireGuard)

| | |
|---|---|
| **Fáze** | F3.1–F3.6 (zóny v backendu) + F6.1–F6.3, F6.5 a F6.2 bez objektového úložiště (infrastruktura) podle [IMPLEMENTATION_PLAN.md](../../docs/security/IMPLEMENTATION_PLAN.md) |
| **Stav** | Připraveno a ověřeno staticky (CI). **Nenasazeno.** |
| **Docker** | Jen lokální vývoj a CI. Produkce Docker nepoužívá. |

## 1. Architektura

```
                 INTERNET
                    │ 80/443                    UDP 51830 / 51831
                    ▼                                  │
┌────────────── Public Edge ─────────────┐             │
│ nginx: informační web (nc-edge-public) │             │
│ app.<doména>: SPA + /bff/ → nc-gateway │  (NC-007)   │
│ /api, /docs, /admin → 404 (bez proxy)  │             │
└────────────────────────────────────────┘             │
                                                       ▼
┌──────────────────────────── Private Core ──────────────────────────────────┐
│ wg-nc 10.50.0.1        nginx :8210 (desktop peery 10.50.16.0/20)           │
│ wg-nc-admin 10.51.0.1  nginx :8220 (admin peery), SSH :22                  │
│        │ unix socket            │ unix socket                              │
│  nc-api@desktop          nc-api@admin         (nc-api@gateway od F4)       │
│  NC_ZONE=desktop         NC_ZONE=admin                                     │
│        └─ PostgreSQL 16 (socket) · Redis · úložiště S3 jen 127.0.0.1 ─ worker │
└────────────────────────────────────────────────────────────────────────────┘
```

- **Pilot (varianta B):** Public Edge i Private Core na jednom serveru, pravidla `nftables/nc-single-server.nft`.
- **Produkce (varianta A):** dva servery, pravidla `nc-edge.nft` a `nc-core.nft`. Kód backendu je v obou variantách stejný. Mění se jen umístění nginx edge a pravidla firewallu.

## 2. Bezpečnostní principy

| Pravidlo | Kde se vynucuje |
|---|---|
| Zónu určuje proces (`NC_ZONE=%i` v systemd), nikdy požadavek | `systemd/nc-api@.service`, `app/platform/http/exposure.py` |
| Každá instance má vlastní unix socket. Připojit se smí jen nginx (skupina `nc-api-sock`) | systemd `RuntimeDirectory` + `UMask=0007` |
| Deny-by-default: route mimo zónu i nezařazená route vrací 404, a to i v admin zóně | `ExposureGuardMiddleware`, CI `tests/test_route_exposure.py` |
| JWT: ověřuje se podpis, `exp`, `iat`, `iss` a `aud` zóny. Token z jiné zóny vrací 401 | `auth_service.decode_token`, `tests/test_f3_jwt_zones.py` |
| Superadmin se přihlásí jen v admin zóně | `AuthService.login` / `get_user_by_token` |
| PostgreSQL jen na unix socketu, Redis a objektové úložiště jen na loopbacku, navíc blokované nftables | `provision/nc-provision`, `nftables/*.nft` |
| WireGuard peer = jedna adresa `/32`, žádný forwarding mezi peery | `wireguard/*.example`, `forward policy drop` |
| SSH jen přes `wg-nc-admin`. Nouzový přístup přes konzoli a dočasnou IP | [EMERGENCY_ACCESS.md](EMERGENCY_ACCESS.md) |
| Secrets mimo repo, unit soubory i `core.env` | `bin/nc-gen-secrets`, `LoadCredential` + `bin/nc-run` |

### Vývoj vs. produkce

| | Development (`APP_ENV=development`) | Produkce |
|---|---|---|
| `NC_ZONE` | výchozí `dev`: všechny routy | povinné `gateway`, `desktop` nebo `admin`. Bez něj se API nespustí a guard vrací 404 na vše. `dev` je zakázané. |
| JWT `aud` | `nc-dev` | `nc-web` / `nc-desktop` / `nc-admin` |
| Proxy hlavičky | `TRUSTED_PROXY_IPS` prázdné | `unix` (nginx přes socket) |
| Rate limit | v paměti | Redis, fail-closed |
| Ledger trvalých smazání | volitelný | povinný (`PHOTO_PURGE_LEDGER_PATH`) |

## 3. Adresy a porty

| Rozhraní | Síť | Port | Kdo |
|---|---|---|---|
| `wg-nc` | 10.50.0.0/16 (core 10.50.0.1, edge 10.50.0.2, desktopy 10.50.16.0/20) | UDP 51830; TCP 8210 (desktop), 8200 (gateway, F4) | desktopy, edge |
| `wg-nc-admin` | 10.51.0.0/24 (monitoring .5, správci .10–.99) | UDP 51831; TCP 8220, 22, 9100 | NovuAdmin, SSH, monitoring |

Rozsahy jsou ověřené proti ostatním sítím Novusion: 10.10/24 (legacy), 10.20/24 (platform), 10.30/24 (trade), 10.40/24 (admin), 10.251/24 (testy NovuAdmin) a výchozí Hetzner Cloud Network 10.0.0.0/16. Nic se nepřekrývá.

## 4. Instalace: `provision/nc-provision` (F6.2)

Instalátor je idempotentní a spouští se jako root na čistém Ubuntu 24.04 nebo Debianu 12. Release aplikace musí být v `/opt/novuconstruct`. Konfigurace se zadává v `/etc/novuconstruct/provision.conf` (vzor `provision/provision.conf.example`).

```sh
P=/opt/novuconstruct/deploy/linux/provision/nc-provision
$P preflight      # kontroly: systém, místo, porty, cizí PostgreSQL/Redis, firewall, SSH, čas, DNS
$P plan           # co by install změnil (nic nemění)
$P install        # balíčky, účty, adresáře, secrets, PostgreSQL, Redis, venv, core.env, systemd, nginx, WG klíče
$P migrate        # pg_dump záloha + alembic upgrade head jako nc_owner + práva (bin/nc-migrate)
$P start          # služby; vyžaduje připravené objektové úložiště
$P smoke          # služby, porty jen na loopbacku/socketu, ACL Redisu, práva v DB, health zón
$P offer-worker   # N2: vypíše backlog offer workeru (bin/nc-offer-backlog), ověří AI_OFFER_PROVIDER;
                 # zapne nc-offer-worker až s NC_CONFIRM_OFFER_BACKLOG=1 (není součástí nc-core.target)
$P firewall       # nftables: potvrzení APPLY-FIREWALL + automatický návrat do 120 s
$P ssh-harden     # SSH jen klíčem: potvrzení APPLY-SSH + automatický návrat
$P breakglass     # konzolový nouzový účet (EMERGENCY_ACCESS.md): potvrzení CREATE-BREAKGLASS
```

| Vlastnost | Jak |
|---|---|
| Opakovatelnost | Každý krok zjistí stav a mění jen rozdíl. Druhé spuštění `install` nic nezmění. |
| Nic destruktivního | Žádné `DROP`, žádné mazání dat ani secrets, žádná rotace. Cizí konfigurační soubor se nepřepíše: vznikne `<soubor>.nc-new`. Spravované soubory (evidence v `/var/lib/nc-provision/managed-files`, jen root) se aktualizují se zálohou `.nc-bak.<čas>`. |
| Firewall a SSH | Mění je jen samostatné příkazy. Je potřeba zadat potvrzovací slovo (terminál nebo `NC_PROVISION_CONFIRM`). Bez `KEEP` do 120 s systemd timer vrátí původní stav. Při nasazení firewallu se aktuální SSH adresa dočasně (2 h) přidá do `ssh_emergency`. Firewall mění jen tabulku `inet nc` (edge `inet nc_edge`), bez `flush ruleset`; záloha i návrat se týkají jen jí. Trvale se uloží do `/etc/nftables.d/novuconstruct.nft` a do `/etc/nftables.conf` se přidá jen `include`. Pozor: `policy drop` tabulky NovuConstructu zahodí i provoz, který povolují cizí tabulky (sdílený server řeší T5). |
| nginx 80/443 (T5.3) | Každý vhost NovuConstructu je samostatný soubor `/etc/nginx/conf.d/nc-*.conf`, cizí soubor se nepřepíše (`.nc-new`). `server_tokens off` je v každém vlastním `server` bloku (`snippets/nc-security-headers.conf`), `00-nc-http-common.conf` nemá žádné direktivy. `NC_NGINX_SHARED=0` (dedikovaný, výchozí): `nc-edge-default.conf` drží `default_server` na 80/443 (neznámý host → 444) a vypne distribuční `sites-enabled/default`. `NC_NGINX_SHARED=1` (nginx sdílený s NovuServerem): žádný `default_server`, `sites-enabled/default` i cizí vhosty zůstanou, vhosty odpovídají jen na `NC_DOMAIN` a `NC_APP_DOMAIN` (port 80: ACME + přesměrování) a drop-in nginx nemá `Requires=nftables.service`; `start` proto před načtením ověří, že nftables běží. Preflight blokuje, když nginx má cizí vhosty a `NC_NGINX_SHARED=0`. |
| PostgreSQL 16 | Jen unix socket (`listen_addresses = ''`), `scram-sha-256`. Role `nc_owner` (DDL, migrace), `nc_app` (služby), `nc_admin`. `pg_hba` pustí jen tyto role do `novuconstruct`, originál je v `pg_hba.conf.nc-orig`. Cluster s cizími databázemi instalátor nepřebírá. |
| Redis 7 | `bind 127.0.0.1 -::1`, ACL uživatelé `nc-api` a `nc-worker` (hesla jen jako SHA-256), `default` vypnutý, bez `@dangerous`, `noeviction`. |
| Migrace | `bin/nc-migrate`: jen `upgrade head`, nikdy downgrade. Odmítne databázi s revizí, kterou kód nezná. Neprázdnou DB před migrací zazálohuje (`/var/backups/novuconstruct`, 0600). `audit_logs` zůstane pro aplikační role jen pro přidávání. |
| Secrets | `bin/nc-gen-secrets` → `/etc/novuconstruct/secrets/*` (0640). Do služeb jdou jen přes `LoadCredential`. Klíč gateway má jen `nc-api@gateway`. |
| Data | PostgreSQL `/var/lib/postgresql`, stav aplikace `/var/lib/novuconstruct`, objektové úložiště `NC_DATA_ROOT` (samostatné LUKS volume, F6.7). Nic z toho není v `/opt/novuconstruct`. |

**Objektové úložiště:** open-source MinIO je archivovaný a `dl.min.io` vrací `410 Gone`. Náhrada čeká na rozhodnutí S-1 v [OBJECT_STORAGE_OPTIONS.md](../../docs/security/OBJECT_STORAGE_OPTIONS.md). Do té doby ho instalátor neinstaluje a `start` bez `NC_OBJECT_STORAGE_READY=1` služby API nespustí.

**Ručně zůstává:**
- WireGuard peery (instalátor vygeneruje klíče a šablony `*.conf.nc-new`),
- Hetzner Cloud Firewall (jen TCP 80/443 a UDP 51830/51831),
- skutečný `ANTHROPIC_API_KEY`,
- `nc-provision tls` s `NC_DOMAIN`.

**Desktop (pilot):** oficiální klient WireGuard pro Windows podle `wireguard/desktop-peer.conf.example`. V aplikaci se jako server nastaví `http://10.50.0.1:8210/api/v1`.

## 4a. Web Gateway / BFF (NC-007 etapa 1)

Kontrakt: [NC-007_STAGE1_CONTRACT.md](../../docs/security/NC-007_STAGE1_CONTRACT.md) kap. 8. Provoz, rotace klíčů a diagnostika: [GATEWAY_RUNBOOK.md](GATEWAY_RUNBOOK.md).

| Prvek | Soubor | Poznámka |
|---|---|---|
| Proces gateway | `systemd/nc-gateway.service` | uživatel `nc-gateway`, `python -m nc_gateway` z `src/gateway/.venv`, 127.0.0.1:8300, `IPAddressAllow=127.0.0.1 10.50.0.1`, `AF_UNIX AF_INET`, core cesty maskované |
| Session store | `systemd/nc-gateway-redis.service`, `redis/nc-gateway-redis.conf` | **samostatná** instance Redis, jen unix socket, ACL `nc-gateway` → `~nc:bff:*` |
| Target | `systemd/nc-edge.target` | edge, ne core; bez `Wants=` – jednotky se přidají až explicitním `nc-provision gateway` |
| Konfigurace | `env/gateway.env.example` → `/etc/nc-gateway/gateway.env` | bez secrets |
| Secrets | `bin/nc-gen-secrets --gateway` → `/etc/nc-gateway/secrets` (0700/0600 root) | jen `LoadCredential`; gateway nevidí secrets core, core nevidí session klíče gateway |
| nginx edge | `nginx/nc-edge-webapp.conf`, `nginx/snippets/nc-proxy-bff.conf` | `/` SPA s CSP bez `unsafe-*`, `/bff/` → gateway, `/api/`, `/docs`, `/openapi.json`, `/metrics`, `/admin` → 404 |
| Zóna gateway na core | `nginx/nc-core-gateway.conf` (A: 10.50.0.1:8200) / `nginx/nc-core-gateway-single.conf` (B: 127.0.0.1:8200) | jen s `NC_ENABLE_GATEWAY_ZONE=1` |

```sh
# provision.conf: NC_ENABLE_GATEWAY=1, NC_APP_DOMAIN=app.<doména> (+ na core NC_ENABLE_GATEWAY_ZONE=1)
$P install                          # připraví vše, NIC nespustí
NC_CONFIRM_GATEWAY=1 $P gateway     # kontroly → enable nc-gateway-redis + nc-gateway (nc-edge.target)
$P smoke
```

## 4b. Deploy a rollback: `deploy.sh` (F6.6, T8.1)

```sh
git -C /opt/novuconstruct-src.git fetch --quiet origin       # zdroj commitů (holý klon)
/opt/novuconstruct/deploy/linux/deploy.sh <sha>               # 7–40 hex, musí být jednoznačné
```

Release se nasazuje jako adresář `/opt/novuconstruct-releases/<plné SHA>` (vlastní venv) a `/opt/novuconstruct` je **symlink** na aktivní release. Jednorázový převod po `nc-provision install`: `mv /opt/novuconstruct /opt/novuconstruct-releases/<sha>` a `ln -s /opt/novuconstruct-releases/<sha> /opt/novuconstruct` (se zastavenými službami). Skript s adresářem místo symlinku odmítne pokračovat.

| Fáze | Co dělá |
|---|---|
| 1. Kontroly | root, zámek `/var/lib/nc-deploy/lock`, SHA existuje v repu, aktuální release je symlink, revize DB je novému kódu známá (`nc-migrate status` stagovaného releasu) |
| 2. Staging | `git archive` + venv do `/opt/novuconstruct-releases/<sha>`; běžící služby se nemění |
| 3. Stop | `nc-worker`, `nc-api@desktop`, `nc-api@admin` + běžící `nc-api@gateway`, `nc-offer-worker`, `nc-gateway` |
| 4. Záloha | **povinná** a i bez migrace: `pg_dump -Fc` ověřený `pg_restore --list` → `/var/backups/novuconstruct/pre-deploy-*.dump` (0600); volitelně hook `NC_DEPLOY_STORAGE_BACKUP <adresář> <čas>` pro úložiště, jeho selhání deploy zastaví |
| 5. Přepnutí | atomický symlink `/opt/novuconstruct` → nový release |
| 6. Migrace | `nc-migrate upgrade` (jen `upgrade head`, nikdy downgrade) |
| 7. Ověření | do `NC_DEPLOY_VERIFY_TIMEOUT` (120 s): `/api/v1/health` v zónách desktop a admin, `/api/v1/ready` v admin zóně (`"ready": true`), čerstvý (< 90 s) heartbeat **nového** procesu workeru `worker:heartbeat:<host>-<MainPID>`; starý klíč předchozího procesu kontrolu nesplní |
| 8. Záznam | `/var/lib/nc-deploy/deployed.env` (`NC_DEPLOYED_SHA`, `NC_DEPLOYED_ALEMBIC_REVISION` – skutečná revize DB, předchozí SHA, záloha) a řádek v `history.log` |

**Politika rollbacku (T8.1).** Backend se nespustí, pokud DB není přesně na head revizi jeho vlastního kódu (`app/main.py`). Předchozí kód proto po změně schématu nastartovat nemůže, a to ani u expand-only migrace.

| Situace | Postup | Exit |
|---|---|---|
| Selhání před přepnutím (SHA, staging, stop, záloha) | release se nemění, služby předchozího releasu se znovu spustí a ověří | 1 |
| Selhání, revize DB se **nezměnila** (selhaná transakční migrace, health, READY, heartbeat) | automatický návrat na předchozí release + ověření | 2 |
| Selhání, revize DB se **změnila** nebo ji nelze zjistit | **žádný automatický rollback ani restore**; nový release zůstává, skript vypíše zálohu, stav zapíše do `last-failure.env`. Vlastník rozhodne: oprava dopředu novým releasem, nebo ručně `pg_restore` zálohy a přepnutí symlinku na předchozí release | 3 |
| Selže i návrat | ruční zásah (záloha je vypsaná) | 4 |

Automatický downgrade (`alembic downgrade`) se nikdy nespouští. Destruktivní (contract) migrace patří až do releasu po ověřeném expand kroku (SECURITY_ARCHITECTURE §8.3).

## 4c. Monitoring a alerty (T7.2, F9.3)

Pravidla jsou v `ops/alerting/alerts.yml`, jejich jednotkové testy v `ops/alerting/alerts_test.yml`. Prometheus čte `/metrics` API (job `novu-backend`) a node_exporter s textfile collectorem (`/var/lib/prometheus/node-exporter`), kam zapisují `bin/nc-backup` a `bin/nc-wg-metrics` (`nc-wg-metrics.timer`, každou minutu).

| Alert | Kdy vystřelí | Zdroj |
|---|---|---|
| `BackendDown` / `BackendTargetMissing` | API neodpovídá 1 min / Prometheus API vůbec nesbírá 5 min | `up{job="novu-backend"}` |
| `WorkerDown` | žádný worker nemá čerstvý heartbeat (< 90 s) 3 min | `novu_worker_alive` |
| `WorkerHeartbeatStale` | některá instance workeru přestala obnovovat heartbeat, zatímco jiné běží (2 min) | `novu_worker_seen_instances`, `novu_worker_alive_instances` |
| `WorkerHeartbeatUnknown` | API nemůže číst heartbeaty z Redisu 5 min | `novu_worker_monitoring_available` |
| `WireGuardInterfaceDown` | `wg-nc` / `wg-nc-admin` chybí, je `down`, nebo `wg show` selže (2 min) | `nc_wg_interface_up` |
| `WireGuardInterfaceNotMonitored` | pro `wg-nc` / `wg-nc-admin` nepřichází žádná metrika 10 min | `absent(nc_wg_interface_up)` |
| `WireGuardNoHandshake` | rozhraní je nahoře, ale žádný peer neudělal handshake déle než nastavený limit (2 min); rozhraní bez peerů se počítá jako bez handshaku | `nc_wg_interface_latest_handshake_timestamp_seconds`, `nc_wg_handshake_max_age_seconds` |
| `WireGuardMetricsStale` | `nc_wg.prom` je starší než 5 min | `node_textfile_mtime_seconds` |

Limit handshaku se nastavuje v `/etc/novuconstruct/monitoring.env` (šablona `env/monitoring.env.example`): `NC_WG_HANDSHAKE_MAX_AGE` (výchozí 900 s, `0` alert vypne) a `NC_WG_HANDSHAKE_MAX_AGE_OVERRIDES="wg-nc-admin:0"` pro jednotlivá rozhraní. Neplatná hodnota → `nc-wg-metrics` skončí exit 2 a předchozí metriky ponechá; po 5 minutách hlásí `WireGuardMetricsStale`.

## 5. Testy

| Co | Jak |
|---|---|
| Zařazení všech rout, zóna × route, nezařazená route, CORS preflight, hlavičky nemění zónu | `pytest tests/test_route_exposure.py` |
| JWT `iss`/`aud`/`iat`/`exp`, podpis, `alg=none`, token z jiné zóny, superadmin jen v admin zóně | `pytest tests/test_f3_jwt_zones.py` |
| Proxy přes unix socket, podvržené `X-Forwarded-For` | `pytest tests/test_sa05_client_ip.py` |
| `nginx -t` (dedikovaný i sdílený nginx vedle cizích vhostů NovuServeru, T5.3), `nft -c`, `systemd-analyze verify` + `security`, shellcheck, žádné klíče v šablonách; Web Gateway: edge vhost proti stub gateway (404, CSP, `X-Forwarded-For`, `X-NC-*`, limity těla), izolace jednotky od secrets core, práva `nc-gen-secrets`, ACL Redisu gateway | `tests/validate-configs.sh` (CI job `deploy-linux-config`) |
| `deploy.sh`: úspěch s migrací i bez, neplatné SHA, selhání zálohy, selhání health a migrace s rollbackem, selhání po změně revize bez rollbacku, starý heartbeat | `tests/deploy_test.sh` (stuby, součást `validate-configs.sh`) |
| Alerty: `promtool check rules` a `promtool test rules` (výpadek API a workeru, zastaralý heartbeat, WG rozhraní chybí / bez handshaku); `nc-wg-metrics` a `nc-backup` proti stubům | `tests/validate-configs.sh` → `ops/alerting/alerts_test.yml`, `tests/backup_monitoring_test.sh` |
| Síťová izolace N1–N12 na stagingu | `tests/network_isolation.sh` |
