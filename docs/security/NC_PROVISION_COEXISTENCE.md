# Koexistence nc-provision s NovuServerem (T5) – analýza stavu

Stav k 2026-11-10, větev `feat/nc-007-secure-web-platform`. Pouze čtení kódu; nic nebylo spuštěno. Doplněno o implementaci T5.1 (viz oddíl Implementační poznámky).

## Závislosti

| Vstup | Stav | Doklad |
|---|---|---|
| T3 rozhodnutí DEDIKOVANÝ / SDÍLENÝ | Chybí | žádný záznam v `docs/security/` |
| T4 výpis serveru (porty, PG, Redis, `nft list ruleset`, `wg show`) | Chybí v repu, neověřeno | úloha Inventura ve stavu review, výstup není v `docs/` |

Bez T3 nelze zvolit větev akceptace T5.

## Současné chování nc-provision

| Oblast | Stav | Doklad | Dopad na sdíleném serveru |
|---|---|---|---|
| Preflight | Implementováno, neověřeno | `deploy/linux/provision/nc-provision:261-272` (cizí DB, data v Redisu → block), `:291-292` (80/443 cizí proces → block), `:298-300` (existující nft pravidla → warn) | Instalace na sdíleném serveru skončí blokací – bezpečné, ale koexistence nemožná |
| nftables | Vlastní tabulka (T5.1), policy drop zůstává | `nc-core.nft`, `nc-edge.nft`, `nc-single-server.nft`: bez `flush ruleset`, `table` + `delete table inet nc` / `inet nc_edge`; `policy drop` na input/output/forward; UDP jen 51830/51831/51832 a iif `wg-nc`/`wg-nc-admin` | Cizí tabulky zůstanou, ale drop v tabulce `inet nc` zahodí provoz `wg-platform` (10.20.0.0/24) a `wg-admin` (10.40.0.0/24), který povolují |
| Uložení firewallu | Vlastní tabulka (T5.1) | `nc-provision` `cmd_firewall`: záloha `nft list table inet <t>`, návrat = `delete table` + obnova jen vlastní tabulky; trvale `/etc/nftables.d/novuconstruct.nft` + `include` v `/etc/nftables.conf` | Cizí obsah `/etc/nftables.conf` zůstává; stará kopie tabulky z dřívější verze se jen hlásí varováním |
| PostgreSQL | Jen dedikovaný | `nc-provision:423` `listen_addresses = ''`; `:431-444` celý `pg_hba.conf` vlastní, `local all all reject` | NovuServer ztratí TCP i lokální přístup |
| Redis | Jen dedikovaný | `nc-provision:497-524` include do `/etc/redis/redis.conf`, `user default off`, ACL jen nc-api/nc-worker | Klienti NovuServeru bez ACL uživatele přestanou fungovat |
| nginx | Jen dedikovaný | `deploy/linux/nginx/nc-edge-public.conf:10-20` `default_server`; `nc-provision:911` maže `sites-enabled/default`; `systemd/nginx.service.d/10-novuconstruct.conf:7` `Requires=nftables.service`; `nc-http-common.conf` globální http kontext | Konflikt default_server, změna globálního chování nginx NovuServeru |
| Gateway Redis | Oddělený | `deploy/linux/redis/nc-gateway-redis.conf`, unix socket, `PrivateNetwork=yes` | bez kolize |
| Garage | Oddělený | loopback 3900/3901/3903, preflight `nc-provision:251-253` | kolize jen při obsazených portech |

Pozn.: samotné přesunutí pravidel do vlastní tabulky nestačí – drop v libovolném base chainu je v nftables konečný. Varianta SDÍLENÝ vyžaduje, aby tabulka `inet nc` buď neměla `policy drop` pro provoz, který nepatří NovuConstructu, nebo aby explicitně propouštěla provoz NovuServeru (ověřený výpisem T4).

## Testy

- `deploy/linux/tests/validate-configs.sh` (Ubuntu 24.04 kontejner): kontroluje nginx -t, nft -c, systemd, shellcheck, izolaci gateway a Garage. Od T5.1 navíc: žádná sada pravidel nemá `flush ruleset` ani nesahá na jinou tabulku než `inet nc` / `inet nc_edge`; každá sada pravidel se dvakrát načte vedle cizí tabulky `inet novuserver` (cizí tabulka beze změny, žádná zdvojená pravidla); `cmd_firewall` nezálohuje celý ruleset a nepřepisuje `/etc/nftables.conf`. Koexistenci s cizími PG/Redis/nginx netestuje. Pro aktuální stav nespuštěno; poslední PASS je historický (`docs/architecture/PHASE_B_REPORT.md:95`).
- `deploy/linux/tests/network_isolation.sh` (N1–N12): staging, nespuštěno.

## Podmínky uzavření T5

### Varianta DEDIKOVANÝ
1. Rozhodnutí T3 obsahuje větu „koexistence nepoužita“ s odkazem na výpis T4 bez cizích služeb (žádné cizí DB, Redis data, nginx vhosty, nft tabulky, WG rozhraní).
2. T5.1–T5.4 zrušit jako mimo rozsah. Kód beze změny – současný preflight sdílený server odmítne. (T5.1 je mezitím implementováno; změna je neškodná i pro dedikovaný server.)

### Varianta SDÍLENÝ
- T5.1 nftables: bez `flush ruleset` (jen `table inet nc` delete/create) – **hotovo**; rollback a `/etc/nftables.conf` nepřepisují cizí pravidla (include místo náhrady) – **hotovo**; bez konečného drop pro provoz NovuServeru – **otevřené** (závisí na T3/T4).
- T5.2 PostgreSQL/Redis: samostatný cluster PG (např. `postgresql@<ver>-nc`, vlastní socket/port) a samostatná instance Redis (`redis-server@nc`, vlastní socket); žádný zásah do `pg_hba.conf` ani `/etc/redis/redis.conf` NovuServeru; úprava preflightu.
- T5.3 nginx: žádný `default_server`, nemazat `sites-enabled/default`, `nc-http-common.conf` jen neutrální direktivy, drop-in bez `Requires=nftables.service` pro cizí vhosty; podmíněná instalace.
- `validate-configs.sh` rozšířit o scénář koexistence (cizí tabulka nft – **hotovo**, cizí vhost, cizí PG/Redis) a musí projít.
- T5.4: uživatel ověří na VM s běžícím NovuServerem (`wg-platform`, `wg-admin`, jeho DB, Redis a vhosty fungují po `install` i `firewall`).

## Implementační poznámky – T5.1 nftables ve vlastní tabulce (ST-00001, 2026-11-10)

Autor: Pavel Dostál, Novusion

### Změněné chování
- `deploy/linux/nftables/nc-single-server.nft`, `nc-core.nft`, `nc-edge.nft`: `flush ruleset` nahrazeno `table inet nc` + `delete table inet nc` (edge `nc_edge`). Opakované `nft -f` v jedné atomické transakci odstraní jen starou vlastní tabulku a založí novou; cizí tabulky se nemění. Upraveny všechny tři soubory, protože je nasazuje stejná funkce `cmd_firewall`.
- `deploy/linux/provision/nc-provision` `cmd_firewall`:
  - odmítne sadu pravidel s `flush ruleset`; název tabulky čte ze souboru (`nc` / `nc_edge`);
  - záloha jen `nft list table inet <t>` (prázdný soubor = tabulka dřív neexistovala);
  - rollback skript: `{ table inet <t>; delete table inet <t>; <záloha> } | nft -f -` – atomicky, bez `flush ruleset`;
  - `ssh_emergency` se přidává do `inet <t>` (dřív natvrdo `inet nc`, na edge chyba – tabulka se jmenuje `nc_edge`);
  - trvale: `/etc/nftables.d/novuconstruct.nft` + jednorázově `include "/etc/nftables.d/novuconstruct.nft"` na konec `/etc/nftables.conf` (záloha `.nc-bak.<TS>`); pokud `/etc/nftables.conf` ještě obsahuje starou kopii tabulky z dřívější verze, vypíše varování (nic nemaže).
- Preflight: varování o existujících pravidlech nově říká, že se mění jen vlastní tabulka, ale její `policy drop` zahodí i provoz povolený cizími tabulkami.
- `deploy/linux/README.md` (Firewall a SSH) a `docs/security/WG_NETWORK_DESIGN.md` §2.4 popisují nové chování.

### Validace
- `nft -c` / `validate-configs.sh`: **NOT RUN** – vyžaduje Ubuntu 24.04 kontejner s `NET_ADMIN` (CI job `deploy-linux-config`); na pracovní stanici chybí `nft` i Docker.
- `bash -n` / `sh -n` / shellcheck: **NOT RUN** – lokálně čeká na schválení; pokrývá je `validate-configs.sh` v CI.
- `build.bat`: Failed – venv backendu odkazuje na neexistující Python 3.13 (WindowsApps); nesouvisí se změnou (jen `deploy/linux` a dokumentace).
- Commit `[ST-00001]`: neproveden – git hlásí dubious ownership.

### Rizika a navazující práce
- `policy drop` v `inet nc` dál blokuje provoz NovuServeru na sdíleném serveru (konečný verdikt drop v jakémkoli base chainu). Řešení podle T3/T4 v rámci T5.
- Obnova zálohy tabulky se sadami s `timeout`/`expires` prvky závisí na tom, že `nft` přijme vlastní výpis (stejné riziko jako dřívější obnova celého rulesetu); ověřit na VM v T5.4.
- Servery zprovozněné dřívější verzí mají v `/etc/nftables.conf` kopii tabulky i `flush ruleset`; při `systemctl reload nftables` se cizí pravidla z jiných souborů ztratí – odstranit ručně podle varování.

## Otevřené
- Rozhodnutí T3 a výpis T4.
- `git status` neověřen (dubious ownership; příkaz čeká na schválení).
- Běh `validate-configs.sh` nad změnou T5.1 (CI `deploy-linux-config`).
