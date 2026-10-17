# Novu Builder - Production Backup/Restore Boundary

This file is the authoritative production operating definition for backup,
restore, and disaster-recovery boundaries.

It answers three separate questions:

1. What the repository implements today
2. What production operators must provide outside the repository
3. What must not be claimed as full production DR

## Production Source Of Truth

Production source of truth is split by data class:

- PostgreSQL database = authoritative source of relational state
- S3 bucket = authoritative source of file storage

Production file storage means:

- uploaded photos
- derived photo variants
- AI input variants
- export artifacts

Local `storage_data` is not a production backup target and is not a production
restore source. It is DEV/TEST compatibility only.

## Production Invariants

- `STORAGE_BACKEND=s3`
- local filesystem storage is forbidden outside DEV/TEST
- DB records must reference S3 object keys
- production restore must never depend on `storage_data` tar archives

## What The Repo Implements Today

Implemented by repository scripts:

- `scripts/backup.sh`
- `ops/restore.sh`
- `python-backend/scripts/verify_restore.sh`
- `python-backend/scripts/restore_db.sh`

Current repository capability:

- deterministic DB backup artifact set
- deterministic DB restore contract
- explicit Variant A foundation contract metadata for future DB + S3 pairing
- DB integrity checks
- schema/head validation
- explicit non-claim of full production DR

Current repository limit:

- no S3 bucket recovery automation
- no S3 object recovery automation
- no full production media recovery workflow
- no full-state production DR proof

Operational truth for `APP_ENV=production` with `STORAGE_BACKEND=s3`:

- repo backup = DB-only truth
- repo restore = DB-only restore contract
- full production DR is not implemented by repo scripts

## Implemented Backup Contract

Authoritative DB artifact set produced by `scripts/backup.sh`:

- `db_YYYYMMDD_HHMMSS.pgdump`
- `db_YYYYMMDD_HHMMSS.pgdump.sha256`
- `db_YYYYMMDD_HHMMSS.json`

Manifest contract:

- `backup_contract = "db-restore-v1"`
- `dr_contract = "variant-a-foundation-v1"`
- `dr_recovery_point_model = "db-artifact-paired-with-explicit-s3-recovery-point"`
- `backup_scope = "db-only"`
- `production_dr_eligible = false`

Production + S3 semantics:

- backup covers database state only
- local storage archive is not produced
- manifest must declare:
  - `storage_backend = "s3"`
  - `storage_coverage = "authoritative-s3-not-covered-by-this-backup"`
  - `storage_archive_included = false`
- manifest may additionally carry Variant A foundation metadata:
  - `s3_bucket`
  - `s3_region`
  - `s3_recovery_point`
  - `storage_snapshot_consistent`

## Variant A Foundation Contract

Purpose:

- define the future full production DR pairing boundary without claiming that the
  repo implements full DR today
- bind one authoritative DB artifact set to one explicit S3 recovery point
- fail closed unless the operator has declared the minimum S3 recovery metadata

Field meaning and justification:

- `dr_contract`
  - version marker for the Variant A foundation semantics
  - prevents ambiguous future interpretation of DR metadata
- `dr_recovery_point_model`
  - states that the pair is `DB artifact + explicit S3 recovery point`
  - prevents broad wording such as "S3 covered" without a concrete recovery
    reference
- `s3_bucket`
  - identifies which authoritative bucket the DB storage keys must resolve
    against
- `s3_region`
  - identifies where that authoritative bucket lives
- `s3_recovery_point`
  - operator-declared reference to the intended S3 bucket state for pairing
  - this is metadata only; it is not an implemented S3 restore action
- `storage_snapshot_consistent`
  - explicit assertion that the declared S3 recovery point is intended to be
    consistent with the DB artifact
  - if unknown, it must not be implied; leave it unset/null and keep
    `production_dr_eligible = false`
- `production_dr_eligible`
  - explicit claim bit
  - remains fail-closed and false in the current repository implementation

Recovery point coupling model:

- DB side of the pair = `db_TIMESTAMP.pgdump` + checksum + manifest
- storage side of the pair = `s3_bucket` + `s3_region` + `s3_recovery_point`
- the pair is only minimally declared for future Variant A use when:
  - `storage_backend = "s3"`
  - `s3_bucket` is known
  - `s3_region` is known
  - `s3_recovery_point` is known
  - `storage_snapshot_consistent = true`
- even when that minimum metadata is present, the repository still does not
  claim full production DR because:
  - repo scripts do not restore S3/object storage
  - repo scripts do not validate recovered S3 media against DB references
  - repo scripts therefore keep `production_dr_eligible = false`

Local/dev semantics:

- backup covers the same DB artifact set
- script may additionally create `storage_YYYYMMDD_HHMMSS.tar.gz`
- that archive is local/dev compatibility only
- it is not an authoritative production recovery mechanism

## Implemented Restore Contract

Primary operator entrypoint:

```bash
./ops/restore.sh /backups/db_YYYYMMDD_HHMMSS.pgdump
```

What repo restore validates:

1. manifest exists and matches backup artifact
2. checksum exists and matches
3. `verify_restore.sh` passes, unless operator explicitly uses `--skip-verify`
4. critical DB tables exist after restore
5. `alembic_version` is populated
6. schema matches repository HEAD after migration step
7. backend liveness probe responds

What repo restore does not claim:

- full production disaster recovery
- S3/object storage recovery
- full application readiness beyond dependency-free liveness

Restore success semantics:

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
- `storage_snapshot_consistent = true` without complete S3 recovery point
  metadata fails
- S3 DR metadata on a non-S3 backend fails
- missing production S3 bucket/region/credentials/versioning prerequisites fail
- failed S3 bucket reachability or object/version listing checks fail
- failed verify fails
- failed `pg_restore` fails
- failed liveness ends with `Restore handoff status: INCOMPLETE`

## External Production S3 Controls

Production media protection must be provided outside repo scripts.

Required external controls:

- S3 bucket versioning enabled
- lifecycle rules for noncurrent version retention
- delete marker handling according to retention policy
- audit trail according to platform policy

Recommended operator minimum:

- keep current objects until explicitly deleted by app lifecycle
- retain noncurrent versions long enough to cover operational recovery window
- do not expire versions sooner than DB dump retention without explicit approval

Important boundary:

- this repository describes the boundary
- this repository does not deliver the S3 recovery automation itself

## Production Restore Order

For `production+s3`, restore order is mandatory:

1. Recover S3 first
2. Restore PostgreSQL second
3. Start backend and worker
4. Run DB, S3, and application validation
5. Run orphan cleanup only if needed

Reason:

- DB contains storage keys that must resolve against S3
- if DB is restored before S3 is available, the system enters a critical invalid
  state

## Production Validation Checklist

### Database

- `alembic_version` is present
- critical tables exist
- tenant data counts are plausible

### S3

- sample photo `storage_key` from DB resolves in S3
- sample export `storage_key` from DB resolves in S3
- signed download URLs can be generated

### Application

- `/api/v1/health` is healthy
- authenticated login works
- one known case loads correctly
- one known image resolves correctly

Important boundary:

- `/api/v1/health` alone is not evidence of full production restore
- repo scripts use liveness as a narrow runtime signal, not a full-state DR proof

## Invalid States

### DB Without S3

This is a critical error.

Meaning:

- DB rows reference objects that do not exist in the authoritative storage layer
- image and export retrieval will fail
- production state is incomplete

Required action:

- stop treating the system as restored
- recover S3 first
- re-run validation

### S3 Without DB

This is not a valid serving state, but it is recoverable.

Meaning:

- bucket contains objects that may not have relational references
- objects without DB references are storage orphans

Required action:

- restore DB
- run storage consistency scan
- resolve via orphan cleanup policy

## What Must Not Be Claimed

These claims are false under the current repository implementation:

- `scripts/backup.sh` provides full production DR in `production+s3`
- `ops/restore.sh` proves full production restore in `production+s3`
- `storage_data.tar.gz` is authoritative production media coverage
- local filesystem media recovery is valid production recovery for S3 mode

## Operator Rule

In `APP_ENV=production` with `STORAGE_BACKEND=s3`:

- use repo scripts for DB backup/restore only
- use external S3 controls for media protection and recovery
- do not describe repo restore success as full-state production recovery

If any document disagrees with this file, this file defines the production
operating truth.
