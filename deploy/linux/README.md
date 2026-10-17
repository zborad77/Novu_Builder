# NovuConstruct – nasazení bez Dockeru (Ubuntu/Debian + systemd + nginx + WireGuard)

| | |
|---|---|
| **Fáze** | F3.1–F3.3, F3.5 (zóny v backendu) + F6.1–F6.3, F6.5 (infrastruktura) podle [IMPLEMENTATION_PLAN.md](../../docs/security/IMPLEMENTATION_PLAN.md) |
| **Stav** | Připraveno a ověřeno staticky (CI). **Nenasazeno.** |
| **Docker** | Jen lokální vývoj a CI. Produkce Docker nepoužívá. |

## 1. Architektura

```
                 INTERNET
                    │ 80/443                    UDP 51830 / 51831
                    ▼                                  │
┌────────────── Public Edge ─────────────┐             │
│ nginx: informační web (nc-edge-public) │             │
│ /api, /bff, /admin → 404 (bez proxy)   │             │
└────────────────────────────────────────┘             │
                                                       ▼
┌──────────────────────────── Private Core ──────────────────────────────────┐
│ wg-nc 10.50.0.1        nginx :8210 (desktop peery 10.50.16.0/20)           │
│ wg-nc-admin 10.51.0.1  nginx :8220 (admin peery), SSH :22                  │
│        │ unix socket            │ unix socket                              │
│  nc-api@desktop          nc-api@admin         (nc-api@gateway od F4)       │
│  NC_ZONE=desktop         NC_ZONE=admin                                     │
│        └──── PostgreSQL 16 · Redis · MinIO jen 127.0.0.1 ── nc-worker      │
└────────────────────────────────────────────────────────────────────────────┘
```

- **Pilot (varianta B):** Public Edge i Private Core na jednom serveru, pravidla `nftables/nc-single-server.nft`.
- **Produkce (varianta A):** dva servery, pravidla `nc-edge.nft` a `nc-core.nft`. Kód backendu je v obou variantách stejný. Mění se jen umístění nginx edge a pravidla firewallu.

## 2. Bezpečnostní principy

| Pravidlo | Kde se vynucuje |
|---|---|
| Zónu určuje proces (`NC_ZONE=%i` v systemd), nikdy požadavek | `systemd/nc-api@.service`, `app/core/exposure.py` |
| Každá instance má vlastní unix socket. Připojit se smí jen nginx (skupina `nc-api-sock`) | systemd `RuntimeDirectory` + `UMask=0007` |
| Deny-by-default: route mimo zónu i nezařazená route vrací 404, a to i v admin zóně | `ExposureGuardMiddleware`, CI `tests/test_route_exposure.py` |
| JWT: ověřuje se podpis, `exp`, `iat`, `iss` a `aud` zóny. Token z jiné zóny vrací 401 | `auth_service.decode_token`, `tests/test_f3_jwt_zones.py` |
| Superadmin se přihlásí jen v admin zóně | `AuthService.login` / `get_user_by_token` |
| PostgreSQL, Redis a MinIO jen na loopbacku a navíc blokované nftables | `env/core.env.overrides`, `nftables/*.nft` |
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

## 4. Instalace (pilot, varianta B)

Skripty se spouštějí ručně a ve všech krocích jako root.

1. **Uživatelé a skupiny:**
   ```sh
   groupadd --system novuconstruct; groupadd --system nc-api-sock
   useradd --system -g novuconstruct -G nc-api-sock -d /nonexistent -s /usr/sbin/nologin novuconstruct
   usermod -aG nc-api-sock www-data
   ```
2. **Kód:** release tag do `/opt/novuconstruct` (vlastník root, jen pro čtení), venv `/opt/novuconstruct/python-backend/.venv`.
3. **Secrets:** `bin/nc-gen-secrets`. Do `/etc/novuconstruct/secrets/ANTHROPIC_API_KEY` vložit skutečný klíč.
4. **PostgreSQL 16:**
   - `listen_addresses = 'localhost'`, `scram-sha-256`,
   - role `nc_owner` (DDL, migrace) a `nc_app` (heslo z `secrets/POSTGRES_PASSWORD`),
   - databáze `novuconstruct`.
5. **Redis 7:** `bind 127.0.0.1 ::1`, `protected-mode yes`, `requirepass` z `secrets/REDIS_PASSWORD`.
6. **MinIO:**
   - systemd služba na `127.0.0.1:9000`, konzole `127.0.0.1:9001`,
   - root heslo z `secrets/MINIO_ROOT_PASSWORD`,
   - aplikační uživatel `S3_ACCESS_KEY_ID` s policy jen na bucket.
7. **Konfigurace:**
   ```sh
   cp python-backend/.env.production.example /etc/novuconstruct/core.env
   ```
   Pak odstranit všechny secrets (jsou v `secrets/`) a doplnit `env/core.env.overrides`. Výsledek: `chmod 0640`, `chown root:novuconstruct`.
8. **Migrace:** explicitně, jako `nc_owner`:
   ```sh
   alembic upgrade head
   ```
9. **WireGuard:** `wireguard/wg-nc.conf.example` a `wg-nc-admin.conf.example` → `/etc/wireguard/` (0600).
   ```sh
   systemctl enable --now wg-quick@wg-nc wg-quick@wg-nc-admin
   ```
10. **nftables:** `nftables/nc-single-server.nft` → `/etc/nftables.conf`.
    ```sh
    nft -c -f /etc/nftables.conf && systemctl enable --now nftables
    ```
    Pak systemd timer pro `bin/nc-egress-refresh`.
11. **Hetzner Cloud Firewall:** jen TCP 80/443 a UDP 51830/51831.
12. **nginx:**
    - `nginx/snippets/*` → `/etc/nginx/snippets/`,
    - `nc-http-common.conf` → `/etc/nginx/conf.d/00-nc-http-common.conf`,
    - `nc-core-private.conf` + `nc-edge-public.conf` → `/etc/nginx/conf.d/`,
    - certifikát Let's Encrypt do `/etc/novuconstruct/tls/`.
13. **Služby:**
    ```sh
    cp systemd/* /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable --now nc-core.target
    ```
14. **Ověření:**
    - `tests/network_isolation.sh` z každého místa (`internet`, `desktop-peer`, `admin-peer`, `core`),
    - `systemd-analyze security nc-api@desktop`.

**Desktop (pilot):** oficiální klient WireGuard pro Windows podle `wireguard/desktop-peer.conf.example`. V aplikaci se jako server nastaví `http://10.50.0.1:8210/api/v1`.

## 5. Testy

| Co | Jak |
|---|---|
| Zařazení všech rout, zóna × route, nezařazená route, CORS preflight, hlavičky nemění zónu | `pytest tests/test_route_exposure.py` |
| JWT `iss`/`aud`/`iat`/`exp`, podpis, `alg=none`, token z jiné zóny, superadmin jen v admin zóně | `pytest tests/test_f3_jwt_zones.py` |
| Proxy přes unix socket, podvržené `X-Forwarded-For` | `pytest tests/test_sa05_client_ip.py` |
| `nginx -t`, `nft -c`, `systemd-analyze verify`, žádné klíče v šablonách | `tests/validate-configs.sh` (CI job `deploy-linux-config`) |
| Síťová izolace N1–N12 na stagingu | `tests/network_isolation.sh` |
