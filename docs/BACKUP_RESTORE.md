# Novu Builder - Implemented Backup/Restore Contract

This document describes what the repository actually implements today.
For the authoritative production operating boundary, see
[../BACKUP_RESTORE.md](../BACKUP_RESTORE.md).

## Scope

Implemented by repo scripts:

- `scripts/backup.sh`
- `ops/restore.sh`
- `python-backend/scripts/verify_restore.sh`
- `python-backend/scripts/restore_db.sh`

This is a DB-only restore contract.
It is not a full production disaster recovery solution for
`APP_ENV=production` with `STORAGE_BACKEND=s3`.

## Artifact Contract

Authoritative write contract produced by `scripts/backup.sh`:

| Artifact | Meaning |
|---|---|
| `db_YYYYMMDD_HHMMSS.pgdump` | PostgreSQL custom-format dump |
| `db_YYYYMMDD_HHMMSS.pgdump.sha256` | Mandatory checksum |
| `db_YYYYMMDD_HHMMSS.json` | Mandatory manifest |

Required manifest semantics:

- `backup_contract = "db-restore-v1"`
- `dr_contract = "variant-a-foundation-v1"`
- `dr_recovery_point_model = "db-artifact-paired-with-explicit-s3-recovery-point"`
- `backup_scope = "db-only"`
- `production_dr_eligible = false`

Restore flow also expects:

- `db_file`
- `checksum_file`
- `backup_version`

Additional metadata may include:

- `app_env`
- `storage_backend`
- `s3_bucket`
- `s3_region`
- `s3_recovery_point`
- `storage_snapshot_consistent`
- `storage_coverage`
- `storage_archive_included`
- `storage_archive_file`
- `alembic_head`
- `git_sha`

Legacy read compatibility:

- restore scripts can still read old `manifest_YYYYMMDD_HHMMSS.json`
- this is read-only compatibility with warning output
- new writes must use `db_YYYYMMDD_HHMMSS.json`

## Mode Semantics

### Local/Dev

Typical mode:

- `APP_ENV=development`
- `STORAGE_BACKEND=local`

Backup behavior:

- writes DB artifact set
- writes `storage_YYYYMMDD_HHMMSS.tar.gz`

Meaning:

- DB restore contract is authoritative for DB state
- local storage archive is a compatibility artifact for local/dev workflows
- this is not a production DR claim

### Production + S3

Typical mode:

- `APP_ENV=production`
- `STORAGE_BACKEND=s3`

Backup behavior:

- writes DB artifact set
- does not write `storage_*.tar.gz`
- manifest declares:
  - `backup_scope = "db-only"`
  - `production_dr_eligible = false`
  - `storage_coverage = "authoritative-s3-not-covered-by-this-backup"`

Meaning:

- backup covers database state only
- authoritative production object storage is not backed up by repo scripts
- repo scripts do not implement full production DR for S3 media
- manifest may carry Variant A foundation metadata for a future DB + S3 pairing,
  but that metadata does not change the current DB-only claim

### Variant A Foundation Metadata

The manifest can carry the future full-DR pairing inputs without claiming that
full DR exists today.

Field purpose:

- `dr_contract` version-marks the Variant A foundation semantics
- `dr_recovery_point_model` states that the pair is `DB artifact + explicit S3 recovery point`
- `s3_bucket` and `s3_region` identify the authoritative bucket
- `s3_recovery_point` records the operator-declared storage recovery reference
- `storage_snapshot_consistent` records whether that declared storage point is
  explicitly intended to match the DB artifact

Minimum future pairing metadata:

- `storage_backend = "s3"`
- `s3_bucket`
- `s3_region`
- `s3_recovery_point`
- `storage_snapshot_consistent = true`

Current boundary:

- repo scripts still do not restore S3/object storage
- repo scripts still do not validate full DB + S3 recovery
- `production_dr_eligible` therefore remains fail-closed and false

## Backup Procedure

Run from repository root:

```bash
BACKUP_DIR=/backups ./scripts/backup.sh
```

What the script guarantees:

1. creates `.pgdump`
2. creates `.sha256`
3. writes manifest only after DB dump and checksum exist
4. enforces retention for DB artifacts
5. optionally syncs DB artifacts off-host when `BACKUP_REMOTE` is configured

Important boundary:

- in `production+s3`, remote sync still covers only DB artifact set
- repo scripts do not provide S3 bucket backup coverage

## Restore Procedure

Primary operator entrypoint:

```bash
./ops/restore.sh /backups/db_YYYYMMDD_HHMMSS.pgdump
```

What `ops/restore.sh` validates:

1. manifest exists and matches backup file
2. checksum exists and matches
3. `verify_restore.sh` passes, unless operator explicitly uses `--skip-verify`
4. critical DB tables exist after restore
5. `alembic_version` is populated
6. schema matches repository HEAD after migration step
7. backend liveness probe responds

What `ops/restore.sh` does not claim:

- full production disaster recovery
- S3/object storage recovery
- full application readiness beyond dependency-free liveness

Restore output semantics:

- `DB restore contract: PASSED` means DB restore checks passed
- `Schema/head alignment: PASSED` means DB revision matches repo HEAD
- `Backend liveness probe: PASSED` means process liveness only
- `Production DR: NOT VERIFIED` is always explicit
- for `production+s3`, output also states:
  - `S3 protection prerequisites: PASSED|FAILED`
  - `S3 pre-restore validation: PASSED|FAILED|NOT EXECUTED`
  - `Authoritative S3/object storage recovery: NOT VERIFIED / OUT OF SCOPE`

Fail-closed behavior:

- missing or mismatched manifest fails
- checksum missing or mismatched fails
- contradictory `production+s3` manifest fails
- `storage_snapshot_consistent = true` without complete S3 recovery point metadata fails
- S3 DR metadata on a non-S3 backend fails
- missing production S3 bucket/region/credentials/versioning prerequisites fail
- failed S3 bucket reachability or object/version listing checks fail
- failed verify fails
- failed `pg_restore` fails
- failed liveness ends with `Restore handoff status: INCOMPLETE`

## Verify Helper

Non-destructive check:

```bash
python-backend/scripts/verify_restore.sh /backups/db_YYYYMMDD_HHMMSS.pgdump
```

What it proves:

- backup can be restored into a temporary DB
- critical tables exist
- key operational tables contain rows
- `alembic_version` matches repository HEAD

What it does not prove:

- runtime startup
- production S3 availability
- full production DR

## Local Storage Archive

`storage_YYYYMMDD_HHMMSS.tar.gz` is:

- local/dev compatibility only
- not part of the authoritative production model
- not produced in `production+s3`

Do not use it as evidence of production DR coverage.

## Operator Rule

In `APP_ENV=production` with `STORAGE_BACKEND=s3`:

- use repo scripts for DB backup/restore only
- treat S3 protection and recovery as external controls outside this repo
- do not say "restore complete" as a full-state production claim based only on
  repo scripts

## Legacy

Older `.sql.gz` backups and older `manifest_*.json` names are legacy inputs.
They are supported only as compatibility paths where explicitly documented by
scripts. They are not the current write contract.
