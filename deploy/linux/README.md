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
│ /api, /bff, /admin → 404 (bez proxy)   │             │
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
$P firewall       # nftables: potvrzení APPLY-FIREWALL + automatický návrat do 120 s
$P ssh-harden     # SSH jen klíčem: potvrzení APPLY-SSH + automatický návrat
$P breakglass     # konzolový nouzový účet (EMERGENCY_ACCESS.md): potvrzení CREATE-BREAKGLASS
```

| Vlastnost | Jak |
|---|---|
| Opakovatelnost | Každý krok zjistí stav a mění jen rozdíl. Druhé spuštění `install` nic nezmění. |
| Nic destruktivního | Žádné `DROP`, žádné mazání dat ani secrets, žádná rotace. Cizí konfigurační soubor se nepřepíše: vznikne `<soubor>.nc-new`. Spravované soubory (evidence v `/var/lib/nc-provision/managed-files`, jen root) se aktualizují se zálohou `.nc-bak.<čas>`. |
| Firewall a SSH | Mění je jen samostatné příkazy. Je potřeba zadat potvrzovací slovo (terminál nebo `NC_PROVISION_CONFIRM`). Bez `KEEP` do 120 s systemd timer vrátí původní stav. Při nasazení firewallu se aktuální SSH adresa dočasně (2 h) přidá do `ssh_emergency`. |
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

## 5. Testy

| Co | Jak |
|---|---|
| Zařazení všech rout, zóna × route, nezařazená route, CORS preflight, hlavičky nemění zónu | `pytest tests/test_route_exposure.py` |
| JWT `iss`/`aud`/`iat`/`exp`, podpis, `alg=none`, token z jiné zóny, superadmin jen v admin zóně | `pytest tests/test_f3_jwt_zones.py` |
| Proxy přes unix socket, podvržené `X-Forwarded-For` | `pytest tests/test_sa05_client_ip.py` |
| `nginx -t`, `nft -c`, `systemd-analyze verify`, žádné klíče v šablonách | `tests/validate-configs.sh` (CI job `deploy-linux-config`) |
| Síťová izolace N1–N12 na stagingu | `tests/network_isolation.sh` |
