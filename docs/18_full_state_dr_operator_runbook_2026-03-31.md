# Full-State DR Operator Runbook

Datum: 2026-03-31
Rozsah: produkcni `APP_ENV=production` + `STORAGE_BACKEND=s3`
Cil: pravdivy full-state DR proces `backup -> verify -> isolated restore -> verdict -> handoff`

## 1. Ucel

Tento runbook je operator postup pro autoritativni DB + media disaster recovery kontrakt.

Pouzivej ho pouze pro backup sety vytvorene skriptem:

- `scripts/backup.sh`

A pro restore orchestraci skriptem:

- `ops/restore.sh`

Tento runbook je platny jen pro explicitni full-state backup scope:

- `backup_scope = "db-plus-s3-media-manifest"`

Pokud ma manifest:

- `backup_scope = "db-only"`

nejde o full-state DR a nelze tvrdit `Production DR: VERIFIED`.

## 2. Kanonicke Skripty

- `scripts/backup.sh`
- `python-backend/scripts/verify_restore.sh`
- `ops/restore.sh`
- `python-backend/scripts/export_s3_recovery_manifest.py`
- `python-backend/scripts/restore_s3_media.py`
- `python-backend/scripts/validate_restored_media.py`
- `python-backend/scripts/check_storage_consistency.py`

Nepouzivej pro full-state DR:

- `python-backend/scripts/restore_db.sh`

Ten je ted pouze DB-only restore cesta a full-state manifest ma explicitne odmitnout.

## 3. Povinne Predpoklady

Pred spustenim musi byt splneno vse:

- produkcni S3 bucket ma zapnuty versioning
- AWS pristup ma pravo na `HeadObject`, `CopyObject`, `ListObjectVersions`, `HeadBucket`
- existuje izolovany restore bucket odlisny od produkcniho bucketu
- operator zna deklarovany `S3_RECOVERY_POINT`
- je k dispozici `DATABASE_URL` nebo `DATABASE_URL_SYNC`
- host umi spustit `bash`, `python`, `docker compose`, `curl`, `sha256sum`, `timeout`

## 4. Povinne Promenne Pro Full-State Backup

```bash
export APP_ENV=production
export STORAGE_BACKEND=s3
export S3_BUCKET=novu-prod-bucket
export S3_REGION=eu-central-1
export S3_RECOVERY_POINT='versioned-bucket@2026-03-31T01:15:00Z'
export STORAGE_SNAPSHOT_CONSISTENT=true
export S3_FULL_COVERAGE_DECLARED=true
export AWS_ACCESS_KEY_ID='...'
export AWS_SECRET_ACCESS_KEY='...'
export DATABASE_URL='postgresql://...'
```

Volitelne:

```bash
export BACKUP_DIR=/var/backups/novu
```

## 5. Povinne Promenne Pro Isolated Restore

```bash
export S3_RESTORE_TARGET_BUCKET=novu-dr-restore-bucket
export S3_RESTORE_TARGET_REGION=eu-central-1
```

Pravidla:

- target bucket musi byt prazdny nebo operatorne pripraveny pro restore
- target bucket nesmi byt stejny jako `S3_BUCKET`
- target bucket je jen izolovany restore target, ne produkcni bucket

## 6. Faze A - Backup

Spust:

```bash
bash scripts/backup.sh
```

### 6.1 Ocekavane Artefakty

Musi vzniknout:

- `db_YYYYMMDD_HHMMSS.pgdump`
- `db_YYYYMMDD_HHMMSS.pgdump.sha256`
- `db_YYYYMMDD_HHMMSS.json`
- `db_YYYYMMDD_HHMMSS.s3-media.json`

### 6.2 Ocekavane Manifest Semantiky

V `db_*.json` musi byt:

- `backup_contract = "db-restore-v1"`
- `backup_scope = "db-plus-s3-media-manifest"`
- `production_dr_eligible = true`
- `dr_contract = "s3-full-state-v1"`
- `dr_recovery_point_model = "db-artifact-paired-with-versioned-s3-object-manifest"`
- `storage_coverage = "authoritative-s3-media-manifest"`
- `s3_media_manifest_file`
- `s3_media_manifest_format = "novu-s3-media-manifest-v1"`
- `s3_media_restore_strategy = "versioned-copy-to-isolated-bucket-v1"`
- `s3_object_count`

V `db_*.s3-media.json` musi byt:

- `format = "novu-s3-media-manifest-v1"`
- `db_backup_file`
- `db_manifest_file`
- `source_bucket`
- `source_region`
- `declared_recovery_point`
- `unique_object_count`
- `objects[*].key`
- `objects[*].version_id`

### 6.3 Go / No-Go Po Backupu

GO:

- vsechny 4 artefakty existuji
- backup output uvadi, ze jde o `DB backup paired with version-pinned S3 media manifest`

NO-GO:

- chybi `.s3-media.json`
- `backup_scope` je `db-only`
- `production_dr_eligible` je `false`
- `s3_object_count` neni validni cislo

## 7. Faze B - Verify Backup Setu

Vyber artefakt:

```bash
export BACKUP_FILE=/var/backups/novu/db_YYYYMMDD_HHMMSS.pgdump
```

Spust:

```bash
bash python-backend/scripts/verify_restore.sh "$BACKUP_FILE"
```

### 7.1 Co Verify Dela

- validuje DB dump + checksum + DB manifest
- validuje full-state backup scope
- validuje pairing mezi `db_*.json` a `db_*.s3-media.json`
- validuje shodu bucket/region/recovery point/object count
- pro full-state contract hlasi:
  - `Full-state backup contract: DECLARED`
  - `Production DR: NOT VERIFIED`

### 7.2 Interpretace

`verify_restore.sh` je preflight, ne finalni DR dukaz.

GO:

- verify skonci `DB restore verification status: PASSED`
- nehlasi pairing mismatch
- nehlasi missing manifest fields

NO-GO:

- libovolny `FAILED`
- mismatch `db_backup_file`, `db_manifest_file`, `source_bucket`, `source_region`, `declared_recovery_point`
- mismatch `unique_object_count` vs `s3_object_count`

## 8. Faze C - Isolated Restore

Spust:

```bash
bash ops/restore.sh "$BACKUP_FILE" --yes
```

### 8.1 Co Se Dela V Poradi

1. backup set validation
2. checksum enforcement
3. pre-restore verify
4. S3 protection prerequisites
5. S3 pre-restore validation
6. isolated media restore do `S3_RESTORE_TARGET_BUCKET`
7. potvrzeny DB restore
8. schema/head validation
9. backend handoff readiness
10. post-restore media validation proti restore bucketu
11. full DB<->storage consistency check proti restore bucketu
12. release readiness decision
13. production DR claim decision

### 8.2 Kriticke Guardy

Restore musi failnout pred destruktivni DB akci kdyz:

- chybi `S3_RESTORE_TARGET_BUCKET`
- chybi `S3_RESTORE_TARGET_REGION` a nejde odvodit region
- target bucket je stejny jako source bucket
- S3 media manifest je neplatny nebo nespárovany
- chybi AWS pristup
- source bucket neni reachable
- bucket nema versioning

## 9. Faze D - Verdikt

### 9.1 Jediny Platny Full-State Success Signal

Plne pozitivni verdict vyzaduje ve vystupu `ops/restore.sh` vse:

```text
5. Media restore step: PASSED
6. Media validation step: PASSED
DB restore contract: PASSED
Schema/head alignment: PASSED
Backend liveness probe: PASSED
Full DB<->storage consistency validation: PASSED
Full-state restore claim: VERIFIED
Production DR: VERIFIED
Release readiness decision: PASSED
```

### 9.2 Co Znamena `Production DR: VERIFIED`

Tvrzeni je pravdive jen kdyz:

- backup byl full-state
- media restore probehl do izolovaneho bucketu
- media usability validation probehla proti izolovanemu bucketu
- DB restore probehl
- schema/head sedi
- backend po restore zije
- DB a restored storage jsou konzistentni

### 9.3 Co Neni Duvod Pro `VERIFIED`

Nasledujici samy o sobe nestaci:

- uspech `backup.sh`
- uspech `verify_restore.sh`
- pritomnost `production_dr_eligible = true` v manifestu
- uspesny DB restore bez media validation
- uspesny sampled media check bez full consistency check

## 10. Faze E - Handoff

Handoff je povolen jen kdyz:

- `Release readiness decision: PASSED`
- `Production DR: VERIFIED`

Povinne ulozit:

- nazev `db_*.pgdump`
- nazev `db_*.json`
- nazev `db_*.s3-media.json`
- `S3_RECOVERY_POINT`
- `S3_RESTORE_TARGET_BUCKET`
- cely stdout/stderr z `ops/restore.sh`
- datum a cas provedeni
- jmeno operatora

## 11. Fail-Closed Pravidla

Okamzite zastav a neprovadej handoff kdyz:

- `backup_scope = db-only`
- `Production DR: NOT VERIFIED`
- `Full-state restore claim: NOT VERIFIED`
- `Release readiness decision: FAILED`
- `Media restore step != PASSED`
- `Media validation step != PASSED`
- `Full DB<->storage consistency validation != PASSED`

## 12. Zakazane Zkratky

- nepouzivej `python-backend/scripts/restore_db.sh` pro full-state DR
- neobnovuj media do produkcniho bucketu
- nepovazuj sampled-only kontrolu za dukaz full DR
- neprijimej manifest claim bez realneho restore verdictu
- nepouzivej `--skip-verify` v produkcni DR operaci

## 13. Minimalni Auditni Zaznam Po Dokonceni

Operator musi zapsat:

- `backup_file`
- `db_manifest_file`
- `s3_media_manifest_file`
- `declared_recovery_point`
- `restore_target_bucket`
- `media_restore_step_status`
- `media_validation_step_status`
- `storage_consistency_status`
- `production_dr_status`
- `release_readiness_status`

## 14. Kanonicky Go / No-Go Souhrn

GO:

- `Production DR: VERIFIED`
- `Release readiness decision: PASSED`

NO-GO:

- cokoliv jineho

