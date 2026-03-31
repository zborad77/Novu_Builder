# Full-State DR Incident Checklist

Datum: 2026-03-31
Pouziti: kratka 1-page operator verze pro incident

## 1. Priprava

- over `APP_ENV=production`
- over `STORAGE_BACKEND=s3`
- over `S3_BUCKET`
- over `S3_REGION`
- over `S3_RECOVERY_POINT`
- over `STORAGE_SNAPSHOT_CONSISTENT=true`
- over `S3_FULL_COVERAGE_DECLARED=true`
- over AWS credentials
- over `DATABASE_URL` nebo `DATABASE_URL_SYNC`
- priprav izolovany `S3_RESTORE_TARGET_BUCKET`
- over, ze target bucket neni produkcni bucket

## 2. Backup

Spust:

```bash
bash scripts/backup.sh
```

Musim videt:

- `db_*.pgdump`
- `db_*.pgdump.sha256`
- `db_*.json`
- `db_*.s3-media.json`

V manifestu musi byt:

- `backup_scope = db-plus-s3-media-manifest`
- `production_dr_eligible = true`
- `dr_contract = s3-full-state-v1`

## 3. Verify

Spust:

```bash
bash python-backend/scripts/verify_restore.sh "$BACKUP_FILE"
```

Musim videt:

- `DB restore verification status: PASSED`
- `Full-state backup contract: DECLARED`
- `Production DR: NOT VERIFIED`

Stop pokud:

- verify failne
- pairing mismatch
- chybi `s3_media_manifest_file`

## 4. Isolated Restore

Spust:

```bash
bash ops/restore.sh "$BACKUP_FILE" --yes
```

Musim videt:

- `5. Media restore step: PASSED`
- `6. Media validation step: PASSED`
- `DB restore contract: PASSED`
- `Schema/head alignment: PASSED`
- `Backend liveness probe: PASSED`
- `Full DB<->storage consistency validation: PASSED`

## 5. Finalni Verdikt

Jediný validni success:

- `Full-state restore claim: VERIFIED`
- `Production DR: VERIFIED`
- `Release readiness decision: PASSED`

Pokud ne:

- NO-GO
- bez handoffu

## 6. Handoff

Uloz:

- backup file
- oba manifesty
- recovery point
- restore target bucket
- cely vystup restore
- operator + timestamp

