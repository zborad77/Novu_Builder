# Full-State DR Copy-Paste Playbook

Datum: 2026-03-31
Pouziti: operator varianta s presnymi prikazy

## 1. Export Prostredi

```bash
export APP_ENV=production
export STORAGE_BACKEND=s3
export S3_BUCKET=novu-prod-bucket
export S3_REGION=eu-central-1
export S3_RECOVERY_POINT='versioned-bucket@2026-03-31T01:15:00Z'
export STORAGE_SNAPSHOT_CONSISTENT=true
export S3_FULL_COVERAGE_DECLARED=true
export AWS_ACCESS_KEY_ID='REPLACE_ME'
export AWS_SECRET_ACCESS_KEY='REPLACE_ME'
export DATABASE_URL='postgresql://REPLACE_ME'
export S3_RESTORE_TARGET_BUCKET=novu-dr-restore-bucket
export S3_RESTORE_TARGET_REGION=eu-central-1
```

## 2. Backup

```bash
bash scripts/backup.sh
```

## 3. Vyber Posledni Backup

```bash
export BACKUP_FILE="$(ls -1t backups/db_*.pgdump | head -1)"
echo "$BACKUP_FILE"
```

## 4. Rychla Kontrola Manifestu

```bash
python - <<'PY'
import json, pathlib
backup = pathlib.Path(sorted(pathlib.Path("backups").glob("db_*.pgdump"))[-1])
manifest = pathlib.Path(str(backup).replace(".pgdump", ".json"))
data = json.loads(manifest.read_text(encoding="utf-8"))
print("manifest:", manifest.name)
print("backup_scope:", data.get("backup_scope"))
print("production_dr_eligible:", data.get("production_dr_eligible"))
print("dr_contract:", data.get("dr_contract"))
print("media_manifest:", data.get("s3_media_manifest_file"))
PY
```

Ocekavane:

- `backup_scope: db-plus-s3-media-manifest`
- `production_dr_eligible: True`
- `dr_contract: s3-full-state-v1`

## 5. Verify Backup Setu

```bash
bash python-backend/scripts/verify_restore.sh "$BACKUP_FILE"
```

## 6. Isolated Restore

```bash
bash ops/restore.sh "$BACKUP_FILE" --yes | tee "restore_$(date +%Y%m%d_%H%M%S).log"
```

## 7. Rychly Post-Check

```bash
grep -E "Media restore step|Media validation step|Full-state restore claim|Production DR:|Release readiness decision:|Full DB<->storage consistency validation:" "restore_"*.log
```

Musim dostat:

```text
Media restore step: PASSED
Media validation step: PASSED
Full DB<->storage consistency validation: PASSED
Full-state restore claim: VERIFIED
Production DR: VERIFIED
Release readiness decision: PASSED
```

## 8. No-Go Triggery

Stop kdyz grep vrati cokoli z:

```text
FAILED
NOT VERIFIED
OUT OF SCOPE
```

## 9. Minimalni Handoff Zaznam

```bash
python - <<'PY'
import json, pathlib
backup = pathlib.Path(sorted(pathlib.Path("backups").glob("db_*.pgdump"))[-1])
manifest = pathlib.Path(str(backup).replace(".pgdump", ".json"))
data = json.loads(manifest.read_text(encoding="utf-8"))
print({
    "backup_file": backup.name,
    "db_manifest_file": manifest.name,
    "s3_media_manifest_file": data.get("s3_media_manifest_file"),
    "declared_recovery_point": data.get("s3_recovery_point"),
    "restore_target_bucket": "novu-dr-restore-bucket",
})
PY
```

