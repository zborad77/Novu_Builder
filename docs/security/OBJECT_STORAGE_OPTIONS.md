# Objektové úložiště po konci open-source MinIO – posouzení a doporučení

| | |
|---|---|
| **Datum** | 17. 10. 2026 |
| **Stav** | **NÁVRH k rozhodnutí.** Doporučená varianta Garage je od 10. 11. 2026 implementovaná v provisioningu (ST-00005, commit `8900cd1`: `nc-provision install`/`start`, `nc-garage.service`, `garage.toml`, `nc-gen-secrets --garage`, kontroly ve `validate-configs.sh`). Formální potvrzení S-1 a S-2 (§6) vlastníkem zatím v repozitáři zapsané není. Krok MinIO v provisioningu F6.2 je nahrazen. |
| **Spouštěč** | `dl.min.io` vrací pro server i `mc` `410 Gone`. Repozitář MinIO CE je od 25. 4. 2026 archivovaný, bez bezpečnostních oprav a bez distribuovaných binárek. |
| **Navazuje na** | [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md) kap. 3.4, 5, 8.4 · [PHOTO_DELETION.md](PHOTO_DELETION.md) · IMPLEMENTATION_PLAN F4.6, F6.2, F6.7, F9.1 |

## 1. Požadavky

1. Self-hosted na našem serveru u Hetzneru, bez AWS a jiného cloudu, data na lokálním persistentním úložišti.
2. Bez veřejného přístupu, jen interní komunikace (loopback na core).
3. Kompatibilita se současným S3 klientem backendu (boto3 1.43).
4. Aktivní údržba a bezpečnostní opravy.
5. Licence vhodná pro komerční B2B produkt.
6. Provoz přes systemd, Docker není povinný.
7. Spolehlivé mazání fotek (trvalé smazání podle PHOTO_DELETION).
8. Zálohování a obnova, provoz na jednom serveru (pilot).

## 2. Co backend od úložiště skutečně potřebuje

Inventura `app/storage/s3_photo_storage.py` (jediný modul, který mluví S3):

| Operace | Použití |
|---|---|
| `PutObject` | upload originálu a odvozených souborů, exporty |
| `GetObject` | čtení (worker, AI, budoucí streamování F4.6) |
| `HeadObject`, `HeadBucket` | existence klíče, health při startu |
| `CopyObject` | duplikace zakázky |
| `DeleteObject` | soft delete → purge, úklid orphanů |
| `ListObjectsV2` (paginator) | kontrola konzistence úložiště (orphan scan) |
| presigned `GET` | dnešní `previewUrl`/`downloadUrl`; podle D-03/F4.6 se nahradí streamováním přes core |

**Nepoužívá:** multipart upload, verzování, bucket policy přes API, SSE hlavičky, lifecycle, notifikace.

Požadavky na úložiště jsou tedy malé: stačí jádro S3 API, které dnes implementuje každá z posuzovaných variant.

## 3. Posouzené varianty

| | **Garage** | **versitygw** (POSIX) | **SeaweedFS** | **RustFS** | **Ceph RGW** |
|---|---|---|---|---|---|
| Licence | AGPL-3.0 | Apache-2.0 | Apache-2.0 | Apache-2.0 | LGPL-2.1/3 |
| Kdo vyvíjí | Deuxfleurs (nezisková, granty NLnet), komunita | Versity (firma) | Chris Lu + komunita | RustFS (firma) | Ceph Foundation, IBM/Red Hat |
| Zralost | stabilní řada v2 (v2.3.0 04/2026, v2.4.x 08/2026) | stabilní (v1.7 07/2026, v1.8 09/2026) | dlouhodobě v provozu, velmi časté releasy | GA až 16. 9. 2026 | nejzralejší, nejsložitější |
| Bezpečnost 2026 | CVE-2026-27607 (zápis objektu, opraveno), dřív časovací kanál v SigV4 (opraveno) | advisory 2025 (panic na chunked uploadu), jinak bez větších nálezů | **řada kritických:** obejití autentizace S3 přes OIDC (CVE-2026-77298), neautentizovaná IAM gRPC služba filer (CVE-2026-72920), cross-bucket path traversal (CVE-2026-54917, CVSS 9.1; CVE-2026-55874) | krátká historie, málo auditovaná | aktivní PSIRT, časté CVE kvůli rozsahu |
| Komponenty a porty | 1 binárka: S3 API, RPC, admin API, vše lze na loopback | 1 binárka, 1 port | master + volume + filer + S3 (víc portů a gRPC) | 1 binárka | MON, MGR, OSD, RGW |
| systemd bez Dockeru | ✅ statická binárka + unit | ✅ binárka/deb + unit | ✅ `weed server` | ✅ | ⚠ prakticky jen cephadm (kontejnery) |
| Jeden server | ✅ `replication_factor = 1` (metadata v jediné kopii → snapshoty) | ✅ přirozeně (soubory na FS) | ✅ | ✅ single-node single-disk | ⚠ nad rámec pilotu |
| Naše S3 operace | všechny ✅ (vč. CopyObject a presigned URL) | všechny ✅ | všechny ✅ | všechny ✅ | všechny ✅ |
| Řízení přístupu | klíč s právy na konkrétní bucket (read/write/owner) | účty gateway + ACL na bucket | IAM, identity v konfiguraci | IAM jako MinIO | IAM uživatelé |
| Šifrování v klidu | jen SSE-C (klíč posílá klient), jinak LUKS | ne (LUKS) | SSE-S3/KMS (novější) | SSE | ano |
| Fyzické smazání po `DeleteObject` | blok se smaže **≥ 10 min** po poklesu refcountu na 0, záznam metadat po 24 h | **ihned** (unlink souboru) | až **při vacuum** volumu, když smetí překročí práh (výchozí 30 %) → data mohou zůstat na disku neomezeně dlouho | ihned, při vypnutém verzování | po GC RGW (hodiny) |
| Záloha a obnova | snapshot metadat (`garage meta snapshot`) + datový adresář, nebo kopie přes S3 (rclone) | restic/rsync souborů včetně xattr, obnova = soubory zpět | `weed backup` nebo kopie přes S3 | jako MinIO (xl.meta) | složitá |

Zdroje k jednotlivým tvrzením jsou na konci dokumentu.

## 4. Vyhodnocení

### Nedoporučujeme

- **SeaweedFS.**
  - V roce 2026 měl několik kritických zranitelností přímo v S3 a IAM vrstvě.
  - Má víc komponent a gRPC portů, které je potřeba hlídat.
  - Smazaná data fyzicky zůstávají na disku do vacuum, a to vychází špatně pro náš požadavek na trvalé smazání fotek. Bez pravidelného vynuceného vacuum (`-garbageThreshold` téměř 0) by „trvale smazaná“ fotka mohla na disku zůstat měsíce.
- **RustFS.** Je GA teprve měsíc a stojí za ním jedna firma, tedy stejné riziko změny licence nebo strategie, jaké právě nastalo u MinIO. Je vhodné ho sledovat, ne ho teď nasadit.
- **Ceph RGW.** Na jeden pilotní server je to příliš velký provozní komplex a bez kontejnerů se instaluje obtížně.

### Doporučení: **Garage**, s versitygw jako záložní variantou

**Proč Garage:**

1. Pokrývá všechny S3 operace, které backend používá, a je dlouhodobě udržovaný projekt cílený přesně na malé self-hosted nasazení. Nezisková správa navíc snižuje riziko „MinIO scénáře“.
2. Je to jedna statická binárka se systemd unitem. S3 API, RPC i admin API jdou svázat na `127.0.0.1`, takže nic není veřejné a nftables zůstanou beze změny.
3. Přístupové klíče s právy na jeden bucket odpovídají dnešnímu účtu `nc-app` (SA-33).
4. Mazání je deterministické v řádu minut (≥ 10 min po `DeleteObject`). Do PHOTO_DELETION to stačí zapsat jako krátké okno.
5. Kontroluje integritu bloků (scrub) a umí pozdější rozšíření na víc uzlů, kdyby varianta A dostala druhý datový uzel.

**Na co je u Garage potřeba myslet:**

| Téma | Dopad | Opatření |
|---|---|---|
| AGPL-3.0 | Garage provozujeme nemodifikovaný jako samostatnou službu. Zákazníkům ho nedistribuujeme a nespojujeme s naším kódem, takže povinnost zveřejnit kód nevzniká. Změnilo by se to při úpravách Garage nebo při on-prem distribuci zákazníkům. | potvrdit s právníkem; když AGPL nevyhoví, nastupuje versitygw (Apache-2.0) |
| Bez SSE-S3 | Šifrování v klidu nezajistí úložiště samo. | **F6.7 (LUKS na datovém volume) se stává povinným před reálnými daty.** Nahrazuje KMS klíč MinIO. |
| `replication_factor = 1` | Metadata jsou v jediné kopii. | `metadata_auto_snapshot_interval` (např. 6 h), `metadata_fsync = true`, zálohy snapshotů v F9.1, zkouška obnovy F9.2 |
| Checksumy boto3 1.43 | Nové SDK posílají CRC32 checksumy, které některá úložiště neuměla. | v klientu nastavit `request_checksum_calculation="when_required"` a `response_checksum_validation="when_required"`, ověřit integračním testem |

**Kdy zvolit versitygw:** když AGPL nebude přijatelná, nebo když dáme přednost maximální jednoduchosti.
- Objekty jsou obyčejné soubory na LUKS volume, mažou se okamžitě a zálohují se restic/rsync.
- Nevýhody: nekontroluje integritu sama (zbývá integrita filesystému), stojí za ní menší komunita a firma (Versity), a metadata objektů jsou v xattr, takže zálohovací nástroj je musí přenášet.

## 5. Dopady na backend (společné pro Garage i versitygw)

Tvar API a DB se nemění; ukládají se jen klíče objektů, jak dnes.

1. **Konfigurace klienta S3** (`_build_s3_client_kwargs`):
   - `addressing_style="path"`,
   - checksum režim `when_required` (bod výše),
   - `S3_REGION` podle úložiště (Garage výchozí `garage`).

   Jde o malou změnu s jednotkovým testem.
2. **Integrační test úložiště v CI.** Proti skutečnému Garage (kontejner jen v CI) projet put/get/head/copy/list/delete/presign a scénáře z PHOTO_DELETION (purge, retry purge). Dnes se S3 cesta testuje jen mockem.
3. **Presigned URL.** URL by mířila na `127.0.0.1:3900`, což je pro desktop přes WG nedosažitelné, stejně jako u MinIO. Řeší to plánované streamování přes core (F4.6 / D-03). To je nutná podmínka pilotu s fotkami v desktopu bez ohledu na volbu úložiště.
4. **PHOTO_DELETION.** Doplnit okno fyzického smazání (Garage ≥ 10 min) a to, že zálohy úložiště mají vlastní retenci.
5. **Kontrola konzistence** (`storage_consistency_service`): beze změny. `ListObjectsV2` funguje ve všech variantách.
6. **Provisioning F6.2.** Krok MinIO nahradit krokem pro zvolené úložiště:
   - binárka z oficiálního release s ověřeným SHA-256,
   - systemd unit se sandboxem,
   - konfigurace pod `NC_DATA_ROOT`, vše na `127.0.0.1`,
   - secrets přes `LoadCredential` (`rpc_secret`, admin token),
   - založení bucketu a klíče s právy jen na bucket.

   Docker compose pro lokální vývoj přepnout na stejné úložiště, aby dev a produkce mluvily se stejnou implementací.
7. **Secrets.** `MINIO_ROOT_*` a `MINIO_KMS_SECRET_KEY` odpadnou. Přibudou `GARAGE_RPC_SECRET` a `GARAGE_ADMIN_TOKEN`. `S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY` zůstanou (klíč vygeneruje Garage při založení).

Odhad: 1–2 dny včetně integračního testu a úpravy provisioningu. Kontrakt API se nemění.

## 6. Rozhodnutí, která jsou potřeba

| # | Otázka | Doporučení |
|---|---|---|
| S-1 | Úložiště pro pilot i produkci | **Garage** |
| S-2 | Je AGPL-3.0 (nemodifikovaný, interní provoz) přijatelná? | ano, ale potvrdit právně. Když ne, **versitygw** |
| S-3 | Šifrování v klidu | LUKS na datovém volume (F6.7) jako povinnost před reálnými daty |
| S-4 | Streamování médií přes core (F4.6) před pilotem s fotkami | ano |

## Zdroje

- MinIO archiv a alternativy: [pinggy.io](https://pinggy.io/blog/minio_archived_self_hosted_s3_alternatives/), [wz-it.com](https://wz-it.com/en/blog/minio-successor-s3-storage-comparison/), [vegardit.com](https://vegardit.com/en/blog/minio-alternatives/), [ssdnodes.com](https://www.ssdnodes.com/learn/self-hosted-minio-alternatives)
- Garage: [S3 compatibility](https://garagehq.deuxfleurs.fr/documentation/reference-manual/s3-compatibility/), [release v2.3.0](https://git.deuxfleurs.fr/Deuxfleurs/garage/releases/tag/v2.3.0), [Internals (GC bloků 10 min, metadata 24 h)](https://garagehq.deuxfleurs.fr/documentation/design/internals/), [Known issues](https://garagehq.deuxfleurs.fr/documentation/reference-manual/known-issues/), [Encryption](https://garagehq.deuxfleurs.fr/documentation/cookbook/encryption/), [Configuration](https://garagehq.deuxfleurs.fr/documentation/reference-manual/configuration/), [repozitář (AGPL)](https://github.com/deuxfleurs-org/garage)
- SeaweedFS: [CVE-2026-77298](https://www.sentinelone.com/vulnerability-database/cve-2026-77298/), [CVE-2026-72920](https://advisories.gitlab.com/golang/github.com/seaweedfs/seaweedfs/CVE-2026-72920/), [CVE-2026-54917](https://advisories.gitlab.com/golang/github.com/seaweedfs/seaweedfs/CVE-2026-54917/), [CVE-2026-55874](https://securelayer7.net/lab/cve-2026-55874-seaweedfs-s3-copy-source-path-traversal), [FAQ (vacuum)](https://github.com/seaweedfs/seaweedfs/wiki/FAQ), [releases](https://github.com/seaweedfs/seaweedfs/releases)
- versitygw: [repozitář](https://github.com/versity/versitygw), [Incompatibilities With AWS S3](https://github.com/versity/versitygw/wiki/Incompatibilities-With-AWS-S3), [advisory GHSA-v2ch-c8v8-fgr7](https://advisories.gitlab.com/pkg/golang/github.com/versity/versitygw/GHSA-v2ch-c8v8-fgr7/)
- RustFS: [RustFS 1.0 GA](https://linuxiac.com/rustfs-1-0-s3-compatible-object-storage-reaches-ga/), [co je a není production-ready](https://dev.to/ethan-carter/rustfs-10-is-ga-after-25-years-whats-actually-production-ready-and-what-isnt-15go)
- boto3 checksumy: [Data Integrity Protections for Amazon S3](https://docs.aws.amazon.com/sdkref/latest/guide/feature-dataintegrity.html)
