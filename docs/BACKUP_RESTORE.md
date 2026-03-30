# Novu Builder — Backup & Restore

> Autoritativní postup pro zálohu a obnovu databáze a souborového úložiště.
> Všechny příkazy spouštěj z kořenového adresáře projektu (složka s `docker-compose.yml`).

---

## Obsah

1. [Přehled artefaktů](#1-přehled-artefaktů)
2. [Jak vytvořit zálohu](#2-jak-vytvořit-zálohu)
3. [Struktura zálohy](#3-struktura-zálohy)
4. [Jak provést restore](#4-jak-provést-restore)
5. [Co dělat při checksum fail](#5-co-dělat-při-checksum-fail)
6. [Co dělat při verify fail](#6-co-dělat-při-verify-fail)
7. [Legacy zálohy (.sql.gz)](#7-legacy-zálohy-sqlgz)
8. [Offsite sync](#8-offsite-sync)

---

## 1. Přehled artefaktů

| Soubor | Popis |
|---|---|
| `db_YYYYMMDD_HHMMSS.pgdump` | PostgreSQL custom-format dump (autoritativní) |
| `db_YYYYMMDD_HHMMSS.pgdump.sha256` | SHA-256 checksum dump souboru |
| `manifest_YYYYMMDD_HHMMSS.json` | Metadata zálohy (alembic head, git SHA, verze) |
| `storage_YYYYMMDD_HHMMSS.tar.gz` | Archiv souborového úložiště (fotky, exporty) |

Zálohovací skript: `scripts/backup.sh`
Restore skript: `ops/restore.sh`

---

## 2. Jak vytvořit zálohu

### Základní záloha

```bash
# Spusť z kořenového adresáře projektu
./scripts/backup.sh
```

Záloha se uloží do `./backups/` (nebo do `$BACKUP_DIR`, pokud je nastavena).

### S vlastním cílovým adresářem

```bash
BACKUP_DIR=/mnt/nfs/novu-backups ./scripts/backup.sh
```

### Prostředí

Skript načte konfiguraci z `.env` (a `.env.production` pro APP_ENV=production):

```bash
# Volitelné proměnné prostředí
BACKUP_DIR=./backups          # kam ukládat zálohy (default: ./backups)
POSTGRES_USER=novu            # uživatel PostgreSQL (default: novu)
POSTGRES_DB=novu_builder      # jméno databáze (default: novu_builder)
RETAIN_DAYS=7                 # kolik dní záloh uchovat (default: 7)
BACKUP_REMOTE=user@host:/path # offsite rsync cíl (volitelné)
```

### Cron (doporučené nastavení)

```cron
# Denní záloha ve 02:00, log do souboru
0 2 * * * cd /opt/novu-builder && BACKUP_DIR=/backups ./scripts/backup.sh >> /var/log/novu-backup.log 2>&1
```

### Co skript provede

1. Vytvoří `pg_dump --format=custom --compress=9` z běžící DB
2. Vypočítá SHA-256 checksum a uloží do `.sha256` souboru
3. Zapíše `manifest_*.json` s metadaty (atomicky přes tmp → mv)
4. Vytvoří tar.gz archiv souborového úložiště (Docker volume)
5. Ořízne zálohy starší než `RETAIN_DAYS` dní
6. Volitelně synchronizuje na offsite přes rsync (jen při `BACKUP_REMOTE`)

---

## 3. Struktura zálohy

### Soubory po úspěšné záloze

```
backups/
├── db_20260329_020001.pgdump           ← hlavní záloha DB
├── db_20260329_020001.pgdump.sha256    ← checksum
├── manifest_20260329_020001.json       ← metadata
└── storage_20260329_020001.tar.gz      ← souborové úložiště
```

### Obsah manifest.json

```json
{
  "timestamp": "20260329_020001",
  "db_file": "db_20260329_020001.pgdump",
  "checksum_file": "db_20260329_020001.pgdump.sha256",
  "alembic_head": "20260329_0021",
  "git_sha": "a1b2c3d",
  "backup_version": "v2"
}
```

| Pole | Popis |
|---|---|
| `timestamp` | Čas vytvoření zálohy (YYYYMMDD_HHMMSS) |
| `db_file` | Jméno dump souboru (bez cesty) |
| `checksum_file` | Jméno checksum souboru (bez cesty) |
| `alembic_head` | Aktuální Alembic revize v DB v době zálohy |
| `git_sha` | Git commit, ze kterého backend běžel |
| `backup_version` | Verze formátu zálohy (`v2` = pgdump, current) |

### Formát .sha256

```
aabbccdd1234...  db_20260329_020001.pgdump
```

Ověření: `sha256sum -c db_20260329_020001.pgdump.sha256`

---

## 4. Jak provést restore

> **VAROVÁNÍ:** Restore trvale přepíše existující databázi. Vždy mej k dispozici čerstvou zálohu stávajícího stavu.

### Interaktivní restore (doporučeno pro produkci)

```bash
./ops/restore.sh backups/db_YYYYMMDD_HHMMSS.pgdump
```

Skript se zeptá `Type 'yes' to continue:` před destruktivní akcí.

### Unattended restore (CI / automatizace)

```bash
./ops/restore.sh backups/db_YYYYMMDD_HHMMSS.pgdump --yes
```

### Restore bez verify (jen v nouzi, explicitní obejití)

```bash
./ops/restore.sh backups/db_YYYYMMDD_HHMMSS.pgdump --yes --skip-verify
```

> `--skip-verify` **není povoleno** v produkčním prostředí (`ENV=production`).

### Průběh restore krok za krokem

| Krok | Akce | Destruktivní? |
|---|---|---|
| 0 | Ověření manifest souboru (přítomnost + konzistence klíčů) | Ne |
| 1 | Ověření checksum (`sha256sum -c`) | Ne |
| 2 | Spuštění `verify_restore.sh` v temp DB | Ne |
| 3 | Potvrzení operátora (přeskočeno s `--yes`) | — |
| 4 | Zastavení `backend` + `worker` | Ne |
| 5 | Terminace aktivních spojení na DB | Ne |
| 6 | `DROP DATABASE novu_builder` | **ANO** |
| 7 | `CREATE DATABASE novu_builder OWNER novu` | Ne |
| 8 | Kopírování dump souboru do DB kontejneru | Ne |
| 9 | `pg_restore` do nové DB | Ne |
| 10 | Ověření kritických tabulek + `alembic_version` | Ne |
| 11 | `alembic upgrade head` (pending migrace) | Ne |
| 12 | Spuštění `backend` + `worker` | Ne |
| 13 | Poll health endpointu (max 60 s) | Ne |

### Manuální ověření po restore

```bash
# Počet organizací
docker compose exec db psql -U novu novu_builder \
  -c "SELECT COUNT(*) FROM organizations;"

# Počet aktivních uživatelů
docker compose exec db psql -U novu novu_builder \
  -c "SELECT COUNT(*) FROM users WHERE is_active=true;"

# Aktuální Alembic revize
docker compose run --rm backend alembic current

# Smoke check
python scripts/smoke_check_live.py http://localhost <email> <password>
```

---

## 5. Co dělat při checksum fail

Chyba: `Checksum mismatch — backup may be corrupt.`

```bash
# 1. Ověř ručně
sha256sum backups/db_YYYYMMDD_HHMMSS.pgdump
cat backups/db_YYYYMMDD_HHMMSS.pgdump.sha256
# Pokud se hodnoty liší → soubor je poškozen

# 2. Zkontroluj velikost souboru
ls -lh backups/db_YYYYMMDD_HHMMSS.pgdump
# Nulový nebo nápadně malý soubor = přerušený dump

# 3. Zkus předchozí zálohu
ls -lth backups/*.pgdump | head -5
# Vezmi druhý nejnovější soubor a ověř jeho checksum

# 4. Pokud nemáš žádnou validní zálohu — použ offsite kopii
rsync -az user@backup-host:/remote/backups/ ./backups/
```

**Nikdy nerestaruji z dump souboru s neplatným checksumem.** Checksum failure = záloha je poškozena nebo přenesena nekompletně.

---

## 6. Co dělat při verify fail

Chyba: `ERROR: verify_restore.sh FAILED or timed out (>60s) — aborting restore`

`verify_restore.sh` provádí non-destruktivní kontrolu v dočasné DB **před** tím, než dojde k jakékoli změně produkčních dat.

```bash
# 1. Spusť verify ručně pro více detailů
bash python-backend/scripts/verify_restore.sh backups/db_YYYYMMDD_HHMMSS.pgdump

# 2. Typické příčiny selhání verify:
#    - pg_restore nahlásí chyby (poškozený dump, nekompatibilní verze PG)
#    - Kritická tabulka chybí v dump souboru
#    - Alembic revize v dump neodpovídá očekávané verzi
#    - Timeout >60 s (příliš velká DB nebo pomalé I/O)

# 3. Pokud verify selže na verzi PG:
docker compose exec db psql -U novu -c "SELECT version();"
pg_restore --version
# Verze pg_restore musí být >= verzi serveru v kontejneru

# 4. Pokud verify selže na timeout a DB je velká (>1 GB):
# Zvyš timeout v ops/restore.sh (řádek: timeout 60 bash "$VERIFY_SCRIPT")
# nebo použi --skip-verify s explicitním vědomím rizika

# 5. Pokud je dump konzistentní ale verify script má bug:
# Použi --skip-verify a proveď manuální kontrolu po restore (krok 4 výše)
```

**Důležité:** `--skip-verify` není povoleno v produkci. Pokud ho potřebuješ na produkci, musíš přechodně odebrat `ENV=production` z prostředí, obnovit data a vrátit nastavení.

---

## 7. Legacy zálohy (.sql.gz)

Zálohy vytvořené před 2026-03-28 (starý `scripts/backup.sh` nebo `ops/backup.sh`) jsou ve formátu `.sql.gz`. `ops/restore.sh` je odmítne — musíš použít manuální postup:

```bash
# 1. Zastavení backendu a workeru
docker compose stop backend worker

# 2. Terminace aktivních spojení
docker compose exec db psql -U novu postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='novu_builder' AND pid <> pg_backend_pid();"

# 3. Drop + create
docker compose exec db psql -U novu postgres \
  -c "DROP DATABASE IF EXISTS novu_builder;"
docker compose exec db psql -U novu postgres \
  -c "CREATE DATABASE novu_builder OWNER novu;"

# 4. Restore z SQL dump
gunzip -c /path/to/db_TIMESTAMP.sql.gz \
  | docker compose exec -T db psql -U novu novu_builder

# 5. Migrace
docker compose run --rm backend alembic upgrade head

# 6. Start
docker compose start backend worker
```

> Legacy `.sql.gz` zálohy nemají `verify_restore.sh` podporu ani manifest.
> Co nejdříve přejdi na aktuální `scripts/backup.sh` (formát `.pgdump`).

---

## 8. Offsite sync

Nastav `BACKUP_REMOTE` pro automatický rsync po každé záloze:

```bash
# V .env nebo při spuštění
BACKUP_REMOTE=user@backup-server:/remote/backups ./scripts/backup.sh
```

Skript synchronizuje `.pgdump`, `.sha256` a `manifest.json` (bez storage archivu, který je příliš velký). Selhání rsync **neovlivní výstupní kód zálohy** — lokální záloha je vždy dokončena nejdříve.

**SSH požadavky:**
- Bezpodmínečná autentifikace (SSH klíč bez passphrase pro cron)
- `BatchMode=yes` je nastaveno — interaktivní prompt nefunguje
- Cílový adresář na remote hostu musí existovat nebo musí být vytvořen přes SSH

```bash
# Ruční test offsite sync
ssh -o BatchMode=yes user@backup-server "ls /remote/backups/"
```

---

*Poslední aktualizace: 2026-03-29*
