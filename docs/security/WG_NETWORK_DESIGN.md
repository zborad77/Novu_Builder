# NovuConstruct – WireGuard, firewall a přístupová pravidla

| | |
|---|---|
| **Datum** | 17. 10. 2026 |
| **Stav** | **NÁVRH ke schválení.** Nic není nakonfigurováno ani nasazeno. |
| **Platforma** | Hetzner Cloud, Ubuntu 24.04 LTS / Debian 12, `wireguard-tools`, `nftables`, Hetzner Cloud Firewall |
| **Související** | [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md) · [API_EXPOSURE_MATRIX.md](API_EXPOSURE_MATRIX.md) |

> V tomto dokumentu nejsou žádné skutečné klíče ani hesla. `<…>` jsou místa, kam se doplní hodnoty vygenerované na serveru.

---

## 1. Sítě a adresní plán

Navrhujeme dvě oddělená WG rozhraní na core. Admin peery tak nejsou ve stejné síti jako stovky desktopových zařízení a kompromitace zařízení zákazníka nedá ani síťovou cestu k admin portu.

| Rozhraní | Síť | UDP port (core) | Účel |
|---|---|---|---|
| `wg-nc` | `10.50.0.0/16` | 51830 | gateway ↔ core, desktopy ↔ core |
| `wg-nc-admin` | `10.51.0.0/24` | 51831 | NovuAdmin, monitoring, SSH |

**Kolize:** NovuServer používá `wg-platform` 10.20.0.0/24 a `wg-admin` 10.40.0.0/24. Řada 10.10.0.0/24 je tam legacy. Navržené rozsahy s nimi nekolidují. Je potřeba je ověřit i proti domácím a kancelářským sítím správců (D-08).

### 1.1 Přidělení adres

| Adresa / rozsah | Peer | Rozhraní |
|---|---|---|
| `10.50.0.1` | core | wg-nc |
| `10.50.0.2` | edge (gateway) | wg-nc |
| `10.50.0.3–9` | rezerva (druhá gateway, HA) | wg-nc |
| `10.50.16.0/20` | desktopová zařízení (4094 adres), jedno zařízení = jedna `/32` | wg-nc |
| `10.51.0.1` | core | wg-nc-admin |
| `10.51.0.5` | monitoring (Prometheus, pokud běží mimo core) | wg-nc-admin |
| `10.51.0.10–99` | administrátoři (NovuAdmin), jeden peer = jedna osoba a jedno zařízení | wg-nc-admin |

---

## 2. Porty a pravidla

### 2.1 Core

| Rozhraní | Port | Zdroj | Služba |
|---|---|---|---|
| veřejné | UDP 51830 | internet | WG handshake wg-nc |
| veřejné | UDP 51831 | internet (volitelně jen známé IP správců) | WG handshake wg-nc-admin |
| veřejné | **nic jiného**, ani 22, 80, 443 | – | – |
| wg-nc | TCP 8200 | jen `10.50.0.2` | nginx → `nc-api@gateway` |
| wg-nc | TCP 8210 | `10.50.16.0/20` | nginx → `nc-api@desktop` |
| wg-nc-admin | TCP 8220 | `10.51.0.10–99` | nginx → `nc-api@admin` |
| wg-nc-admin | TCP 22 | `10.51.0.10–99` | SSH (jen klíče, bez hesel, bez roota) |
| wg-nc-admin | TCP 8220 (`/api/v1/metrics`), 9100, 9187, 9121 | `10.51.0.5` | metriky aplikace, node, postgres a redis exporter |
| loopback | 5432, 6379, 9000, 9001 | jen lokální procesy | PostgreSQL, Redis, MinIO (API a konzole) |

**MinIO konzole (9001)** je jen na loopbacku. Správce se k ní dostane přes SSH tunel ve `wg-nc-admin`.

### 2.2 Edge (gateway)

| Rozhraní | Port | Zdroj | Služba |
|---|---|---|---|
| veřejné | TCP 80 | internet | jen ACME challenge + 301 na HTTPS |
| veřejné | TCP 443 | internet | nginx: SPA, `/bff/*` |
| veřejné | UDP – | – | Edge nemá WG listen port. Spojení iniciuje k core (`Endpoint=core:51830`, `PersistentKeepalive=25`). |
| wg-edge-admin (D-12) | TCP 22 | admin peery | SSH na edge (viz poznámka níže) |
| wg-nc | TCP 9100 | `10.50.0.1` | node_exporter (scrape z core) |
| loopback | 6379 | gateway | session store Redis |

**SSH na edge:** edge nemá veřejný port 22. Doporučujeme připojit edge jako druhý peer do sítě správců. Edge dostane vlastní malé rozhraní `wg-edge-admin` (např. `10.52.0.0/24`, UDP 51832 na edge), kam se připojují jen admin zařízení. Alternativa je Hetzner Console nebo rescue jako break-glass. Rozhodnutí je D-12.

### 2.3 Hetzner Cloud Firewall (vnější vrstva)

| Server | Povolený vstup |
|---|---|
| core | UDP 51830, UDP 51831 |
| edge | TCP 80, TCP 443, UDP 51832 (jen pokud D-12 = wg-edge-admin) |

Odchozí provoz omezuje nftables, protože Hetzner Firewall řeší hlavně příchozí.

### 2.4 nftables – core (referenční politika, neaplikovat)

```nft
#!/usr/sbin/nft -f
# NovuConstruct core – REFERENCE ONLY, not applied.
flush ruleset

table inet nc {
    set gateway_peer  { type ipv4_addr; elements = { 10.50.0.2 } }
    set desktop_peers { type ipv4_addr; flags interval; elements = { 10.50.16.0/20 } }
    set admin_peers   { type ipv4_addr; flags interval; elements = { 10.51.0.10-10.51.0.99 } }
    set monitor_peer  { type ipv4_addr; elements = { 10.51.0.5 } }
    set egress_allow  { type ipv4_addr; flags interval; }   # Anthropic API, SMTP relay, Storage Box – vyplňuje skript z DNS

    chain input {
        type filter hook input priority filter; policy drop;
        iif "lo" accept
        ct state established,related accept
        ct state invalid drop
        meta l4proto { icmp, ipv6-icmp } limit rate 10/second accept

        # veřejné rozhraní: jen WG handshake
        iifname != { "wg-nc", "wg-nc-admin" } udp dport { 51830, 51831 } accept

        # wg-nc
        iifname "wg-nc" ip saddr @gateway_peer  tcp dport 8200 accept
        iifname "wg-nc" ip saddr @desktop_peers tcp dport 8210 accept

        # wg-nc-admin
        iifname "wg-nc-admin" ip saddr @admin_peers  tcp dport { 22, 8220 } accept
        iifname "wg-nc-admin" ip saddr @monitor_peer tcp dport { 8220, 9100, 9121, 9187 } accept

        log prefix "nc-drop-in " level info limit rate 5/minute
    }

    chain forward {
        type filter hook forward priority filter; policy drop;
        # žádné směrování mezi peery: desktop nevidí desktop, gateway nevidí admina
    }

    chain output {
        type filter hook output priority filter; policy drop;
        oif "lo" accept
        ct state established,related accept
        oifname { "wg-nc", "wg-nc-admin" } accept
        udp dport 53 accept
        tcp dport 53 accept
        udp dport 123 accept                                   # NTP
        tcp dport 443 ip daddr @egress_allow accept            # Anthropic API
        tcp dport { 465, 587 } ip daddr @egress_allow accept   # SMTP relay
        tcp dport 23 ip daddr @egress_allow accept             # Storage Box SSH (port 23)
        tcp dport { 80, 443 } meta skuid "_apt" accept         # aktualizace OS
        log prefix "nc-drop-out " level info limit rate 5/minute
    }
}
```

`forward` je drop: **peery spolu nemohou komunikovat** a core není router.

### 2.5 nftables – edge (zkráceně)

- **input:**
  - `lo`, established,
  - `tcp dport {80,443}` z veřejného rozhraní,
  - `iifname "wg-nc" ip saddr 10.50.0.1 tcp dport 9100`,
  - (D-12) `wg-edge-admin` → 22,
  - jinak drop.
- **output:**
  - `wg-nc` jen na `10.50.0.1` tcp 8200,
  - UDP 51830 na veřejnou IP core,
  - DNS, NTP, ACME (443 na Let's Encrypt), apt,
  - jinak drop.

Kompromitovaná gateway tak nemůže skenovat internet ani zbytek WG sítě.

---

## 3. WireGuard konfigurace (šablony)

### 3.1 Core – `/etc/wireguard/wg-nc.conf`

```ini
[Interface]
Address    = 10.50.0.1/16
ListenPort = 51830
PrivateKey = <core-wg-nc-private>      # vygenerováno na core: wg genkey, 0600 root
# žádné PostUp s iptables/NAT – core není router

[Peer]   # edge / gateway
PublicKey  = <edge-public>
PresharedKey = <psk-edge>              # post-quantum hardening, unikátní na peer
AllowedIPs = 10.50.0.2/32

# Desktopové peery NEJSOU v tomto souboru.
# Spravuje je reconciler z DB (tabulka devices) přes `wg set wg-nc peer ...`,
# po vzoru NovuServer modules/netpeers (reconciler + CLI).
```

### 3.2 Core – `/etc/wireguard/wg-nc-admin.conf`

```ini
[Interface]
Address    = 10.51.0.1/24
ListenPort = 51831
PrivateKey = <core-wg-nc-admin-private>

[Peer]   # administrátor <jméno>, zařízení <název>
PublicKey    = <admin1-public>
PresharedKey = <psk-admin1>
AllowedIPs   = 10.51.0.10/32
```

Admin peery jsou ve statickém souboru, spravované ručně nebo přes Ansible. Je jich málo a každá změna má projít review.

### 3.3 Edge – `/etc/wireguard/wg-nc.conf`

```ini
[Interface]
Address    = 10.50.0.2/32
PrivateKey = <edge-private>

[Peer]   # core
PublicKey    = <core-wg-nc-public>
PresharedKey = <psk-edge>
Endpoint     = <core-public-ip>:51830
AllowedIPs   = 10.50.0.1/32      # jen core, ne celá síť
PersistentKeepalive = 25
```

### 3.4 Desktop (generuje klient)

```ini
[Interface]
Address    = 10.50.x.y/32
PrivateKey = <generováno na zařízení, nikdy neopustí zařízení>
DNS        =                      # žádné, aplikace používá IP adresu

[Peer]
PublicKey    = <core-wg-nc-public>
PresharedKey = <psk-device>       # doručí enrollment
Endpoint     = <core-host>:51830
AllowedIPs   = 10.50.0.1/32       # split tunnel: jen core, nic jiného
PersistentKeepalive = 25
```

`AllowedIPs = 10.50.0.1/32` zajistí, že tunel nepřesměruje ostatní provoz zařízení a zařízení nevidí jiné peery (navíc ho blokuje `forward drop`).

---

## 4. Identita peerů a správa klíčů

### 4.1 Zásady

1. **Jeden peer = jedno zařízení.** Žádné sdílené konfigurace. Peer je vázaný na uživatele a firmu v DB (`devices`: `id`, `organization_id`, `user_id`, `public_key`, `psk_hash`, `wg_ip`, `created_by`, `approved_by`, `last_handshake`, `revoked_at`).
2. **Privátní klíč se generuje na zařízení** a nikdy ho nevidí server ani administrátor.
3. **PresharedKey** pro každý peer, aby tunel nebyl prolomitelný ani po budoucím prolomení Curve25519.
4. **WG identita nenahrazuje přihlášení.** Na zařízení se dál přihlašuje uživatel (heslo, později MFA) a core navíc ověřuje, že `user.organization_id` odpovídá `device.organization_id` zdrojové WG IP. Ukradené zařízení bez hesla nic nezmůže. Ukradené heslo bez zařízení nedá přístup do zóny `desktop`.
5. **Revokace:** `revoked_at` + reconciler odebere peer do 60 s, `token_version++` pro sessions z daného zařízení.

### 4.2 Enrollment desktopu (D-07)

```
Uživatel (desktop)            Gateway (P)               Core                   Manažer / NovuAdmin
      │ vygeneruje keypair         │                      │                            │
      │ POST /bff/device-enrollment│                      │                            │
      │  {code, publicKey, name} ──►│ ── POST /devices/enroll (G, HMAC) ──►             │
      │                            │                      │ ověří kód (jednorázový,    │
      │                            │                      │ 24 h, vázaný na user+org), │
      │                            │                      │ device=PENDING ───────────►│ schválí
      │                            │                      │ ◄──────────────────────────│ (MFA)
      │ ◄── {wgIp, serverPublicKey, endpoint, psk} (polling enrollment status) ──────│
      │ připojí WG, login na 10.50.0.1:8210                                            │
```

- Enrollment kód vydá manažer firmy (nebo superadmin) pro konkrétního uživatele.
- Rate limit `/bff/device-enrollment` je 5 požadavků za hodinu na IP. Neplatný kód vrací obecnou chybu.
- PSK se doručí jen jednou, při prvním úspěšném dotazu na stav. Pak se uloží jen jeho hash.

### 4.3 Klíče infrastruktury

| Klíč | Kde vzniká | Kde je | Rotace |
|---|---|---|---|
| core wg-nc, wg-nc-admin | core (`wg genkey`) | `/etc/wireguard`, 0600 root | 1 rok, plánovaně s překryvem |
| edge | edge | `/etc/wireguard`, 0600 root | 1 rok; ihned při podezření na kompromitaci gateway |
| admin peer | zařízení správce (NovuAdmin embedded) | zařízení | 1 rok, ihned při ztrátě |
| PSK | core (`wg genpsk`) | WG konfigurace obou stran | s klíčem peeru |

Inventář veřejných klíčů je v repozitáři konfigurace (bez privátních klíčů), a změny jdou přes review.

---

## 5. Oddělení oprávnění

| Vrstva | Gateway | Desktop uživatel | Administrátor |
|---|---|---|---|
| Síť | jen `10.50.0.1:8200` | jen `10.50.0.1:8210` | `10.51.0.1:8220` + SSH |
| Instance API | `nc-api@gateway` | `nc-api@desktop` | `nc-api@admin` |
| Routy | allowlist G | zóna D | zóna A |
| Token `aud` | `nc-web` | `nc-desktop` | `nc-admin` |
| Role | technician, manager | technician, manager | superadmin + MFA |
| Navíc | HMAC hlavička gateway | vazba zařízení ↔ firma | admin peer allowlist v nginx i nftables |

Útočník, který získá jednu vrstvu (např. WG klíč desktopu), narazí na další (token, `aud`, role, firma).

---

## 6. Varianty nasazení

### 6.1 Varianta A: dva servery (doporučená pro produkci)

```
edge (CX22, veřejná IP)  ── WG wg-nc ──►  core (CCX13+, veřejná IP jen pro UDP WG)
```

| + | − |
|---|---|
| Kompromitace gateway (veřejně exponovaný kód) nedá lokální přístup k DB, MinIO, Redisu ani secrets core. | Dva servery k údržbě a druhá sada aktualizací. |
| Core nemá žádný TCP port do internetu. | Latence WG hopu (v rámci Hetzner lokace < 1 ms). |
| Edge jde kdykoli znovu postavit; drží jen session store (ztráta = odhlášení uživatelů). | Cena: navíc ~5 EUR měsíčně za CX22. |

Podklad pro WG mezi edge a core: veřejná IP, nebo Hetzner Cloud Network (privátní L3). WG běží v obou případech, takže Hetzner síť není důvěryhodná vrstva.

### 6.2 Varianta B: jeden server (pilot, nebo dokud nebude D-01 rozhodnuto)

```
server (veřejná IP)
  nginx :443 ─► nc-gateway (uživatel nc-gw) ─unix socket─► nginx/ nc-api@gateway
  wg-nc / wg-nc-admin pro desktopy a adminy beze změny
```

| + | − |
|---|---|
| Jednodušší provoz, nižší cena. | **Gateway a core sdílejí kernel.** Lokální eskalace práv z procesu gateway znamená přístup ke všemu. |
| Všechny zóny, `aud`, allowlist i HMAC zůstávají stejné. | Izolaci nahrazuje jen systemd sandboxing a práva na unix sockety. |
| Pozdější rozdělení na variantu A je jen přesun gateway, bez změny kódu. | Mezi gateway a core nevede WG; „Gateway ↔ Backend výhradně přes WG“ v této variantě **neplatí**. |

**Povinná kompenzační opatření ve variantě B:**
- gateway běží pod vlastním uživatelem `nc-gw` bez přístupu k `/etc/novuconstruct/core*`, `/srv/minio`, `/var/lib/postgresql`,
- `IPAddressDeny=any` a `RestrictAddressFamilies=AF_UNIX AF_INET` v jednotce gateway,
- Redis session store je samostatná instance (socket `nc-gw`), ne Redis core,
- socket `api-gateway.sock` má skupinu `nc-gw` a ostatní sockety jsou pro `nc-gw` nedostupné,
- AppArmor profil pro `nc-gateway`.

**Doporučení:** pilot na variantě B, produkce s citlivými daty na variantě A. Přechod je jen operační a nevyžaduje změnu kódu.

---

## 7. Testovací scénáře sítě (akceptace)

| # | Scénář | Očekávaný výsledek |
|---|---|---|
| N1 | `nmap -sU -sT -p- <core-public-ip>` z internetu | otevřené jen UDP 51830, 51831 (TCP nic) |
| N2 | `nmap -p- <edge-public-ip>` | jen 80, 443 |
| N3 | z edge (`10.50.0.2`): `curl 10.50.0.1:8210`, `:8220`, `:5432`, `:9000`, `:22` | timeout (drop) |
| N4 | z edge: `curl 10.50.0.1:8200/api/v1/admin/users` s platným tokenem `nc-web` | 404 |
| N5 | z desktop peeru: `curl 10.50.0.1:8200` | timeout |
| N6 | z desktop peeru: ping na jiný desktop peer | nic nedojde (forward drop, AllowedIPs) |
| N7 | z desktop peeru: token `nc-web` (ukradený z gateway) na `:8210` | 401 (`aud`) |
| N8 | revokace zařízení v NovuAdminu | do 60 s zmizí handshake, request vrací timeout |
| N9 | admin peer: `ssh core` přes `10.51.0.1` | OK. Přes veřejnou IP: timeout. |
| N10 | z core: `curl https://example.com` | drop (egress allowlist) |
| N11 | z edge: `curl https://example.com` | drop |
| N12 | restart core: WG a nftables naběhnou před nginx a API (`After=wg-quick@…`) | žádné okno, kdy by API poslouchalo bez firewallu |

---

## 8. Otevřená rozhodnutí

| ID | Otázka | Doporučení |
|---|---|---|
| D-01 | Jeden, nebo dva servery | A pro produkci, B pro pilot |
| D-07 | Enrollment desktopu | kap. 4.2 |
| D-08 | Adresní rozsahy | 10.50.0.0/16 a 10.51.0.0/24 po ověření kolizí |
| D-12 | SSH na edge | `wg-edge-admin` (10.52.0.0/24), Hetzner Console jako break-glass |
| D-13 | Admin handshake port jen ze známých IP správců? | Ne. Správci mají dynamické IP. WG bez platného klíče neodpovídá, port je tedy „neviditelný“. |
