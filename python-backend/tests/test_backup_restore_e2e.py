"""
E2E tests for backup/restore workflow (scripts/backup.sh, ops/restore.sh).

Strategy: subprocess + fake binaries injected via PATH override.
No real Docker, no real DB, no real remote storage — fully isolated.

Scenarios covered:
  Backup:
    B1  valid run → pgdump + sha256 + db-scoped manifest created
    B8  rsync fails → local artifacts intact, only warning emitted
    B9  alembic/git unavailable → backup created, manifest has "unknown", warning printed

  Restore:
    R1  valid artifact set → restore proceeds to completion
    R2  missing .sha256 → fail before destructive action
    R3  checksum mismatch → fail before destructive action
    R4  missing manifest → fail
    R5  invalid manifest content → fail (missing keys / value mismatch)
    R6  verify_restore.sh nonzero exit → fail before destructive action
    R7  verify timeout (exit 124) → fail before destructive action
"""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import textwrap
from pathlib import Path
from typing import Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKUP_SH  = REPO_ROOT / "scripts" / "backup.sh"
RESTORE_SH = REPO_ROOT / "ops" / "restore.sh"

_TS = "20260101_120000"  # fixed timestamp for artifacts


def _repo_alembic_head() -> str:
    versions_dir = REPO_ROOT / "python-backend" / "alembic" / "versions"
    revisions: set[str] = set()
    down_revisions: set[str] = set()

    for path in versions_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("revision = "):
                revisions.add(line.split('"')[1])
            elif line.startswith("down_revision = "):
                down_revisions.update(part for part in line.split('"')[1::2] if part != "None")

    heads = sorted(revisions - down_revisions)
    assert len(heads) == 1, f"expected single alembic head, got: {heads}"
    return heads[0]


REPO_ALEMBIC_HEAD = _repo_alembic_head()


# ── helpers ───────────────────────────────────────────────────────────────────

def _exe(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


# ── fixture ───────────────────────────────────────────────────────────────────

class Env:
    """
    Manages fake binaries, temp dirs, and subprocess helpers for one test.
    All binaries default to success; individual tests override as needed.
    """

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.bin  = tmp / "bin"
        self.bdir = tmp / "backups"
        self.bin.mkdir()
        self.bdir.mkdir()
        self._defaults()

    # ── binary writers ────────────────────────────────────────────────────────

    def _defaults(self) -> None:
        self.docker()
        self.git()
        self.sha256sum()
        self.rsync()
        self.ssh()
        self.timeout()
        self.curl()
        self.aws()
        _exe(self.bin / "du",    "#!/usr/bin/env bash\necho \"4.0K\t${@: -1}\"\n")
        _exe(self.bin / "sleep", "#!/usr/bin/env bash\nexit 0\n")
        _exe(self.bin / "seq",   "#!/usr/bin/env bash\nfor i in $(eval \"echo {1..$1}\"); do echo \"$i\"; done\n")

    def docker(
        self,
        alembic_head: str = REPO_ALEMBIC_HEAD,
        pg_dump_fail: bool = False,
        pg_restore_exit_code: int = 0,
    ) -> None:
        pg_body = (
            "exit 1"
            if pg_dump_fail
            else "python3 -c \"import sys; sys.stdout.buffer.write(b'PGDMP' + b'x' * 2048)\" 2>/dev/null"
        )
        pg_restore_body = "true" if pg_restore_exit_code == 0 else f"exit {pg_restore_exit_code}"
        _exe(self.bin / "docker", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            args="$*"
            case "$args" in
                *pg_dump*)              {pg_body} ;;
                *alembic_version*)      echo "{alembic_head}" ;;
                *"ps -q"*)             echo "fake_container_id" ;;
                *" cp "*)              true ;;
                *" rm "*)              true ;;
                *pg_restore*)          {pg_restore_body} ;;
                *"run --rm backend"*)  true ;;
                *"start backend"*)     true ;;
                *"stop backend"*)      true ;;
                *psql*)
                    if   [[ "$args" == *"EXISTS"*      ]]; then echo "t"
                    elif [[ "$args" == *"version_num"* ]]; then echo "{alembic_head}"
                    elif [[ "$args" == *"COUNT"*        ]]; then echo "t"
                    else true; fi ;;
                *) true ;;
            esac
        """))

    def git(self, sha: str = "abc1234", fail: bool = False) -> None:
        body = "exit 1" if fail else f'echo "{sha}"'
        _exe(self.bin / "git", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            if [[ "$*" == *"rev-parse"* ]]; then {body}; else true; fi
        """))

    def sha256sum(self, verify_pass: bool = True) -> None:
        verify = "exit 0" if verify_pass else 'echo "FAILED" >&2; exit 1'
        _exe(self.bin / "sha256sum", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            if [[ "$1" == "-c" || "$1" == "--check" ]]; then {verify}; fi
            echo "aabbccdd1234  $1"
        """))

    def rsync(self, exit_code: int = 0) -> None:
        _exe(self.bin / "rsync", f"#!/usr/bin/env bash\nexit {exit_code}\n")

    def ssh(self, exit_code: int = 0) -> None:
        _exe(self.bin / "ssh", f"#!/usr/bin/env bash\nexit {exit_code}\n")

    def timeout(self, simulate_timeout: bool = False) -> None:
        body = "exit 124" if simulate_timeout else 'shift; exec "$@"'
        _exe(self.bin / "timeout", f"#!/usr/bin/env bash\n{body}\n")

    def curl(self, exit_code: int = 0) -> None:
        _exe(self.bin / "curl", f"#!/usr/bin/env bash\nexit {exit_code}\n")

    def aws(
        self,
        *,
        versioning_enabled: bool = True,
        head_bucket_exit: int = 0,
        list_objects_exit: int = 0,
        list_versions_exit: int = 0,
    ) -> None:
        versioning_body = 'echo \'{"Status":"Enabled"}\'' if versioning_enabled else 'echo \'{}\''
        _exe(self.bin / "aws", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            args="$*"
            case "$args" in
                *"get-bucket-versioning"*) {versioning_body} ;;
                *"head-bucket"*) exit {head_bucket_exit} ;;
                *"list-objects-v2"*) exit {list_objects_exit} ;;
                *"list-object-versions"*) exit {list_versions_exit} ;;
                *) exit 0 ;;
            esac
        """))

    def aws_missing(self) -> None:
        p = self.bin / "aws"
        if p.exists():
            p.unlink()

    def verify_script(self, exit_code: int = 0) -> Path:
        """Write a standalone fake verify_restore.sh; returns its path."""
        p = self.tmp / "fake_verify.sh"
        _exe(p, f"#!/usr/bin/env bash\nexit {exit_code}\n")
        return p

    def docker_logging(self) -> Path:
        """Replace docker with a logging stub; returns the log file path."""
        log = self.tmp / "docker_calls.log"
        _exe(self.bin / "docker", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            echo "$*" >> {log}
            case "$*" in *"ps -q"*) echo "fake_container_id" ;; *) true ;; esac
        """))
        return log

    def latest_dump(self) -> Path:
        return next(self.bdir.glob("db_*.pgdump"))

    def latest_manifest(self) -> Path:
        return next(self.bdir.glob("db_*.json"))

    # ── artifact helpers ──────────────────────────────────────────────────────

    def make_artifacts(
        self,
        ts: str = _TS,
        *,
        app_env: str = "development",
        storage_backend: str = "local",
        storage_coverage: str = "local-volume-archive-compatibility-only",
        storage_archive_included: bool = True,
        dr_contract: Optional[str] = "variant-a-foundation-v1",
        dr_recovery_point_model: Optional[str] = "db-artifact-paired-with-explicit-s3-recovery-point",
        s3_bucket: Optional[str] = None,
        s3_region: Optional[str] = None,
        s3_recovery_point: Optional[str] = None,
        storage_snapshot_consistent: Optional[bool] = None,
    ) -> tuple[Path, Path, Path]:
        """
        Create a valid backup artifact set (dump, sha256, manifest).
        Manifest is named db_TS.json to match the authoritative restore contract:
          MANIFEST_FILE="${BACKUP_FILE%.pgdump}.json"
        """
        dump = self.bdir / f"db_{ts}.pgdump"
        dump_bytes = b"PGDMP" + b"x" * 2048
        dump.write_bytes(dump_bytes)

        sha = self.bdir / f"db_{ts}.pgdump.sha256"
        sha.write_text(
            f"{hashlib.sha256(dump_bytes).hexdigest()}  {dump}\n",
            newline="\n",
        )

        manifest = self.bdir / f"db_{ts}.json"
        manifest_payload: dict[str, object] = {
            "timestamp": ts,
            "app_env": app_env,
            "backup_contract": "db-restore-v1",
            "backup_scope": "db-only",
            "production_dr_eligible": False,
            "storage_backend": storage_backend,
            "s3_bucket": s3_bucket,
            "s3_region": s3_region,
            "s3_recovery_point": s3_recovery_point,
            "storage_snapshot_consistent": storage_snapshot_consistent,
            "storage_coverage": storage_coverage,
            "storage_archive_included": storage_archive_included,
            "storage_archive_file": f"storage_{ts}.tar.gz" if storage_archive_included else None,
            "db_file": f"db_{ts}.pgdump",
            "checksum_file": f"db_{ts}.pgdump.sha256",
            "backup_version": "v4",
            "alembic_head": REPO_ALEMBIC_HEAD,
            "git_sha": "abc1234",
        }
        if dr_contract is not None:
            manifest_payload["dr_contract"] = dr_contract
        if dr_recovery_point_model is not None:
            manifest_payload["dr_recovery_point_model"] = dr_recovery_point_model
        manifest.write_text(json.dumps(manifest_payload, separators=(",", ":")) + "\n")
        return dump, sha, manifest

    def make_legacy_manifest_only(self, ts: str = _TS) -> tuple[Path, Path, Path]:
        dump, sha, manifest = self.make_artifacts(ts=ts)
        legacy_manifest = self.bdir / f"manifest_{ts}.json"
        manifest.replace(legacy_manifest)
        return dump, sha, legacy_manifest

    # ── runners ───────────────────────────────────────────────────────────────

    def _base_env(self, **overrides: str) -> dict:
        e = {
            **os.environ,
            "PATH":          f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}",
            "BACKUP_DIR":    self._bash_path(self.bdir),
            "BASH_ENV":      self._bash_path(self._write_bash_env()),
            "POSTGRES_USER": "novu",
            "POSTGRES_DB":   "novu_builder",
            "RETAIN_DAYS":   "7",
        }
        e.update(overrides)
        return e

    def _bash(self) -> str:
        found = shutil.which("bash")
        if found:
            return found
        for candidate in (
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
        ):
            if Path(candidate).exists():
                return candidate
        raise FileNotFoundError("bash executable not found for backup/restore E2E test")

    def _bash_path(self, path: Path) -> str:
        resolved = path.resolve().as_posix()
        if len(resolved) >= 3 and resolved[1:3] == ":/":
            return f"/{resolved[0].lower()}{resolved[2:]}"
        return resolved

    def _write_bash_env(self) -> Path:
        bash_env = self.tmp / "bash_env.sh"
        wrappers = []
        for name in ("docker", "git", "sha256sum", "rsync", "ssh", "timeout", "curl", "aws", "sleep", "seq"):
            path = self.bin / name
            if path.exists():
                wrappers.append(f"{name}() {{ '{self._bash_path(path)}' \"$@\"; }}")
        bash_env.write_text("\n".join(wrappers) + "\n", newline="\n")
        return bash_env

    def run_backup(self, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self._bash(), str(BACKUP_SH)],
            capture_output=True, text=True,
            env=self._base_env(**env),
            cwd=str(REPO_ROOT),
        )

    def run_restore(
        self,
        dump: Path,
        *,
        skip_verify: bool = True,
        verify_script_path: Optional[Path] = None,
        **env: str,
    ) -> subprocess.CompletedProcess:
        cmd = [self._bash(), str(RESTORE_SH), str(dump), "--yes"]
        if skip_verify:
            cmd.append("--skip-verify")
        e = self._base_env(**env)
        if verify_script_path is not None:
            e["VERIFY_SCRIPT_OVERRIDE"] = self._bash_path(verify_script_path)
        return subprocess.run(
            cmd,
            capture_output=True, text=True,
            env=e,
            cwd=str(REPO_ROOT),
        )


@pytest.fixture
def fx(tmp_path: Path) -> Env:
    return Env(tmp_path)


# ═══════════════════════════════════════════════════════════════════════════════
# B1 — valid backup run
# ═══════════════════════════════════════════════════════════════════════════════

class TestBackupValidRun:
    def test_exits_zero(self, fx: Env) -> None:
        r = fx.run_backup()
        assert r.returncode == 0, r.stderr

    def test_creates_pgdump(self, fx: Env) -> None:
        fx.run_backup()
        assert len(list(fx.bdir.glob("db_*.pgdump"))) == 1

    def test_creates_sha256(self, fx: Env) -> None:
        fx.run_backup()
        assert len(list(fx.bdir.glob("db_*.pgdump.sha256"))) == 1

    def test_creates_manifest(self, fx: Env) -> None:
        fx.run_backup()
        assert len(list(fx.bdir.glob("db_*.json"))) == 1

    def test_creates_storage_archive_in_default_local_mode(self, fx: Env) -> None:
        fx.run_backup()
        assert len(list(fx.bdir.glob("storage_*.tar.gz"))) == 1

    def test_manifest_has_required_keys(self, fx: Env) -> None:
        fx.run_backup()
        content = next(fx.bdir.glob("db_*.json")).read_text()
        for key in (
            "app_env",
            "backup_contract",
            "dr_contract",
            "dr_recovery_point_model",
            "backup_scope",
            "production_dr_eligible",
            "storage_backend",
            "s3_bucket",
            "s3_region",
            "s3_recovery_point",
            "storage_snapshot_consistent",
            "storage_coverage",
            "storage_archive_included",
            "storage_archive_file",
            "db_file",
            "checksum_file",
            "backup_version",
            "alembic_head",
            "git_sha",
        ):
            assert f'"{key}"' in content, f"manifest missing key: {key}"

    def test_manifest_marks_local_storage_as_compatibility_only(self, fx: Env) -> None:
        fx.run_backup()
        manifest = json.loads(next(fx.bdir.glob("db_*.json")).read_text())
        assert manifest["storage_backend"] == "local"
        assert manifest["dr_contract"] == "variant-a-foundation-v1"
        assert manifest["dr_recovery_point_model"] == "db-artifact-paired-with-explicit-s3-recovery-point"
        assert manifest["s3_bucket"] is None
        assert manifest["s3_region"] is None
        assert manifest["s3_recovery_point"] is None
        assert manifest["storage_snapshot_consistent"] is None
        assert manifest["storage_coverage"] == "local-volume-archive-compatibility-only"
        assert manifest["storage_archive_included"] is True

    def test_real_backup_output_is_restore_compatible(self, fx: Env) -> None:
        backup = fx.run_backup()
        assert backup.returncode == 0, backup.stderr
        dump = fx.latest_dump()
        restore = fx.run_restore(dump)
        combined = restore.stdout + restore.stderr
        assert restore.returncode == 0, combined
        assert "DB restore contract: PASSED" in combined
        assert "Schema/head alignment: PASSED" in combined


class TestBackupProductionS3DbOnlySemantics:
    _s3_env = dict(
        APP_ENV="production",
        STORAGE_BACKEND="s3",
        S3_BUCKET="novu-prod-bucket",
        S3_REGION="us-east-1",
        AWS_ACCESS_KEY_ID="test-access-key",
        AWS_SECRET_ACCESS_KEY="test-secret-key",
    )

    def test_skips_storage_archive(self, fx: Env) -> None:
        r = fx.run_backup(APP_ENV="production", STORAGE_BACKEND="s3")
        assert r.returncode == 0, r.stderr
        assert len(list(fx.bdir.glob("storage_*.tar.gz"))) == 0

    def test_manifest_marks_s3_as_not_covered(self, fx: Env) -> None:
        fx.run_backup(APP_ENV="production", STORAGE_BACKEND="s3")
        manifest = json.loads(next(fx.bdir.glob("db_*.json")).read_text())
        assert manifest["app_env"] == "production"
        assert manifest["storage_backend"] == "s3"
        assert manifest["dr_contract"] == "variant-a-foundation-v1"
        assert manifest["dr_recovery_point_model"] == "db-artifact-paired-with-explicit-s3-recovery-point"
        assert manifest["s3_bucket"] is None
        assert manifest["s3_region"] is None
        assert manifest["s3_recovery_point"] is None
        assert manifest["storage_snapshot_consistent"] is None
        assert manifest["storage_coverage"] == "authoritative-s3-not-covered-by-this-backup"
        assert manifest["storage_archive_included"] is False
        assert manifest["storage_archive_file"] is None

    def test_output_is_explicitly_db_only(self, fx: Env) -> None:
        r = fx.run_backup(APP_ENV="production", STORAGE_BACKEND="s3")
        combined = r.stdout + r.stderr
        assert "DB-only" in combined
        assert "NOT covered" in combined or "not covered" in combined.lower()
        assert "Variant A foundation" in combined
        assert "NOT eligible" in combined

    def test_records_variant_a_foundation_metadata_without_claiming_full_dr(self, fx: Env) -> None:
        fx.run_backup(
            **self._s3_env,
            S3_BUCKET="novu-prod-bucket",
            S3_REGION="us-east-1",
            S3_RECOVERY_POINT="versioned-bucket@2026-03-30T01:15:00Z",
            STORAGE_SNAPSHOT_CONSISTENT="true",
        )
        manifest = json.loads(next(fx.bdir.glob("db_*.json")).read_text())
        assert manifest["s3_bucket"] == "novu-prod-bucket"
        assert manifest["s3_region"] == "us-east-1"
        assert manifest["s3_recovery_point"] == "versioned-bucket@2026-03-30T01:15:00Z"
        assert manifest["storage_snapshot_consistent"] is True
        assert manifest["production_dr_eligible"] is False

    def test_restore_summary_keeps_variant_a_foundation_as_metadata_only(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts(
            app_env="production",
            storage_backend="s3",
            storage_coverage="authoritative-s3-not-covered-by-this-backup",
            storage_archive_included=False,
            s3_bucket="novu-prod-bucket",
            s3_region="us-east-1",
            s3_recovery_point="versioned-bucket@2026-03-30T01:15:00Z",
            storage_snapshot_consistent=True,
        )
        restore = fx.run_restore(dump, **self._s3_env)
        combined = restore.stdout + restore.stderr
        assert restore.returncode == 0, combined
        assert "Restore orchestration status" in combined
        assert "Production DR status: NOT VERIFIED" in combined
        assert "S3 protection prerequisites: PASSED" in combined
        assert "S3 pre-restore validation: PASSED" in combined
        assert "Variant A storage-readiness: PASSED" in combined
        assert "5. Media restore step: NOT IMPLEMENTED" in combined
        assert "6. Media validation step: NOT VERIFIED" in combined
        assert "Variant A foundation contract: metadata recorded only; full DR still not implemented" in combined

    def test_real_production_s3_backup_output_restores_as_db_only(self, fx: Env) -> None:
        backup = fx.run_backup(**self._s3_env)
        assert backup.returncode == 0, backup.stderr
        dump = fx.latest_dump()
        restore = fx.run_restore(dump, **self._s3_env)
        combined = restore.stdout + restore.stderr
        assert restore.returncode == 0, combined
        assert "Production DR status: NOT VERIFIED" in combined
        assert "Production DR: NOT VERIFIED" in combined
        assert "S3 protection prerequisites: PASSED" in combined
        assert "S3 pre-restore validation: PASSED" in combined
        assert "Variant A storage-readiness: FAILED" in combined
        assert "Release readiness decision: PASSED (DB handoff ready only; Production DR remains NOT VERIFIED)" in combined
        assert "Authoritative S3/object storage recovery: NOT VERIFIED / OUT OF SCOPE" in combined


# ═══════════════════════════════════════════════════════════════════════════════
# B8 — rsync failure → local artifacts intact
# ═══════════════════════════════════════════════════════════════════════════════

class TestBackupRemoteSyncFail:
    _remote_env = dict(BACKUP_REMOTE="user@host", BACKUP_REMOTE_PATH="/remote/backups")

    def test_exits_zero_despite_rsync_fail(self, fx: Env) -> None:
        fx.rsync(exit_code=1)
        r = fx.run_backup(**self._remote_env)
        assert r.returncode == 0, r.stderr

    def test_pgdump_intact(self, fx: Env) -> None:
        fx.rsync(exit_code=1)
        fx.run_backup(**self._remote_env)
        assert len(list(fx.bdir.glob("db_*.pgdump"))) == 1

    def test_sha256_intact(self, fx: Env) -> None:
        fx.rsync(exit_code=1)
        fx.run_backup(**self._remote_env)
        assert len(list(fx.bdir.glob("db_*.pgdump.sha256"))) == 1

    def test_manifest_intact(self, fx: Env) -> None:
        fx.rsync(exit_code=1)
        fx.run_backup(**self._remote_env)
        assert len(list(fx.bdir.glob("db_*.json"))) == 1

    def test_warning_in_output(self, fx: Env) -> None:
        fx.rsync(exit_code=1)
        r = fx.run_backup(**self._remote_env)
        # backup.sh emits "⚠ WARNING: remote sync failed" or "WARNING:" prefix
        assert "WARNING" in (r.stdout + r.stderr) or "warning" in (r.stdout + r.stderr).lower()

    def test_no_rsync_without_backup_remote(self, fx: Env) -> None:
        """If BACKUP_REMOTE is unset, a failing rsync must not affect exit code."""
        fx.rsync(exit_code=1)
        r = fx.run_backup()  # no BACKUP_REMOTE
        assert r.returncode == 0, r.stderr


# ═══════════════════════════════════════════════════════════════════════════════
# B9 — degraded metadata (alembic/git unavailable)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBackupDegradedMetadata:
    def _degrade(self, fx: Env) -> None:
        fx.git(fail=True)
        fx.docker(alembic_head="")  # empty → backup.sh falls back to "unknown"

    def test_backup_still_succeeds(self, fx: Env) -> None:
        self._degrade(fx)
        r = fx.run_backup()
        assert r.returncode == 0, r.stderr

    def test_pgdump_created(self, fx: Env) -> None:
        self._degrade(fx)
        fx.run_backup()
        assert len(list(fx.bdir.glob("db_*.pgdump"))) == 1

    def test_manifest_contains_unknown(self, fx: Env) -> None:
        self._degrade(fx)
        fx.run_backup()
        content = next(fx.bdir.glob("db_*.json")).read_text()
        assert '"unknown"' in content

    def test_warning_in_stdout(self, fx: Env) -> None:
        self._degrade(fx)
        r = fx.run_backup()
        assert "WARNING" in (r.stdout + r.stderr)


# ═══════════════════════════════════════════════════════════════════════════════
# R1 — valid artifact set → restore completes
# ═══════════════════════════════════════════════════════════════════════════════

class TestRestoreValidArtifacts:
    def test_exits_zero(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts()
        r = fx.run_restore(dump)
        assert r.returncode == 0, r.stderr

    def test_restore_status_message(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts()
        r = fx.run_restore(dump)
        assert "Restore orchestration status" in r.stdout
        assert "DB restore status: PASSED" in r.stdout
        assert "1. Maintenance mode / write stop intent: PASSED" in r.stdout
        assert "11. Release readiness decision: PASSED" in r.stdout
        assert "Production DR status: NOT VERIFIED" in r.stdout
        assert "DB restore contract: PASSED" in r.stdout
        assert "Production DR: NOT VERIFIED" in r.stdout

    def test_skip_verify_is_reported_as_skipped_not_passed(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts()
        r = fx.run_restore(dump, skip_verify=True)
        combined = r.stdout + r.stderr
        assert r.returncode == 0, combined
        assert "Backup-set verify: SKIPPED (operator override)" in combined

    def test_restore_fails_when_liveness_not_confirmed(self, fx: Env) -> None:
        fx.curl(exit_code=1)
        dump, _, _ = fx.make_artifacts()
        r = fx.run_restore(dump)
        combined = r.stdout + r.stderr
        assert r.returncode != 0, combined
        assert "Restore orchestration status" in combined
        assert "9. Backend liveness / handoff readiness: FAILED" in combined
        assert "10. Post-restore validation: FAILED" in combined
        assert "11. Release readiness decision: FAILED" in combined
        assert "Backend liveness probe: FAILED" in combined
        assert "Release readiness decision: FAILED (backend liveness was not confirmed; Production DR remains NOT VERIFIED)" in combined

    def test_legacy_manifest_name_is_still_readable_with_warning(self, fx: Env) -> None:
        dump, _, _ = fx.make_legacy_manifest_only()
        r = fx.run_restore(dump)
        combined = r.stdout + r.stderr
        assert r.returncode == 0, combined
        assert "deprecated legacy manifest name" in combined

    def test_restore_calls_out_s3_as_out_of_scope_for_production(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts(
            app_env="production",
            storage_backend="s3",
            storage_coverage="authoritative-s3-not-covered-by-this-backup",
            storage_archive_included=False,
            s3_bucket="novu-prod-bucket",
            s3_region="us-east-1",
        )
        r = fx.run_restore(
            dump,
            APP_ENV="production",
            STORAGE_BACKEND="s3",
            S3_BUCKET="novu-prod-bucket",
            S3_REGION="us-east-1",
            AWS_ACCESS_KEY_ID="test-access-key",
            AWS_SECRET_ACCESS_KEY="test-secret-key",
        )
        combined = r.stdout + r.stderr
        assert r.returncode == 0, combined
        assert "Production DR status: NOT VERIFIED" in combined
        assert "S3 protection prerequisites: PASSED" in combined
        assert "S3 pre-restore validation: PASSED" in combined
        assert "5. Media restore step: NOT IMPLEMENTED" in combined
        assert "6. Media validation step: NOT VERIFIED" in combined
        assert "Authoritative S3/object storage recovery: NOT VERIFIED / OUT OF SCOPE" in combined


# ═══════════════════════════════════════════════════════════════════════════════
# R2 — missing .sha256
# ═══════════════════════════════════════════════════════════════════════════════

class TestRestoreProductionS3Guards:
    _base_env = dict(
        APP_ENV="production",
        STORAGE_BACKEND="s3",
        S3_BUCKET="novu-prod-bucket",
        S3_REGION="us-east-1",
        AWS_ACCESS_KEY_ID="test-access-key",
        AWS_SECRET_ACCESS_KEY="test-secret-key",
    )

    def _dump_with_foundation(self, fx: Env) -> Path:
        dump, _, _ = fx.make_artifacts(
            app_env="production",
            storage_backend="s3",
            storage_coverage="authoritative-s3-not-covered-by-this-backup",
            storage_archive_included=False,
            s3_bucket="novu-prod-bucket",
            s3_region="us-east-1",
            s3_recovery_point="versioned-bucket@2026-03-30T01:15:00Z",
            storage_snapshot_consistent=True,
        )
        return dump

    def test_missing_s3_bucket_config_fails_before_destructive_restore(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts(
            app_env="production",
            storage_backend="s3",
            storage_coverage="authoritative-s3-not-covered-by-this-backup",
            storage_archive_included=False,
        )
        log = fx.docker_logging()
        r = fx.run_restore(
            dump,
            APP_ENV="production",
            STORAGE_BACKEND="s3",
            AWS_ACCESS_KEY_ID="test-access-key",
            AWS_SECRET_ACCESS_KEY="test-secret-key",
        )
        combined = (r.stdout + r.stderr).lower()
        calls = log.read_text() if log.exists() else ""
        assert r.returncode != 0
        assert "s3 protection prerequisites failed" in combined
        assert "bucket name is missing" in combined
        assert "stop backend" not in calls

    def test_missing_credentials_fail_before_destructive_restore(self, fx: Env) -> None:
        dump = self._dump_with_foundation(fx)
        log = fx.docker_logging()
        r = fx.run_restore(
            dump,
            APP_ENV="production",
            STORAGE_BACKEND="s3",
            S3_BUCKET="novu-prod-bucket",
            S3_REGION="us-east-1",
        )
        combined = (r.stdout + r.stderr).lower()
        calls = log.read_text() if log.exists() else ""
        assert r.returncode != 0
        assert "s3 protection prerequisites failed" in combined
        assert "credentials" in combined
        assert "stop backend" not in calls

    def test_versioning_requirement_failure_is_explicit_and_fail_closed(self, fx: Env) -> None:
        fx.aws(versioning_enabled=False)
        dump = self._dump_with_foundation(fx)
        log = fx.docker_logging()
        r = fx.run_restore(dump, **self._base_env)
        combined = (r.stdout + r.stderr).lower()
        calls = log.read_text() if log.exists() else ""
        assert r.returncode != 0
        assert "s3 protection prerequisites failed" in combined
        assert "versioning is not enabled" in combined
        assert "stop backend" not in calls

    def test_bucket_reachability_failure_is_explicit_and_fail_closed(self, fx: Env) -> None:
        fx.aws(head_bucket_exit=1)
        dump = self._dump_with_foundation(fx)
        log = fx.docker_logging()
        r = fx.run_restore(dump, **self._base_env)
        combined = (r.stdout + r.stderr).lower()
        calls = log.read_text() if log.exists() else ""
        assert r.returncode != 0
        assert "s3 pre-restore validation failed" in combined
        assert "not reachable" in combined
        assert "stop backend" not in calls

    def test_version_listing_failure_is_explicit_and_fail_closed(self, fx: Env) -> None:
        fx.aws(list_versions_exit=1)
        dump = self._dump_with_foundation(fx)
        log = fx.docker_logging()
        r = fx.run_restore(dump, **self._base_env)
        combined = (r.stdout + r.stderr).lower()
        calls = log.read_text() if log.exists() else ""
        assert r.returncode != 0
        assert "s3 pre-restore validation failed" in combined
        assert "object/version listing check failed" in combined
        assert "stop backend" not in calls

    def test_non_claim_state_remains_explicit_when_foundation_metadata_is_incomplete(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts(
            app_env="production",
            storage_backend="s3",
            storage_coverage="authoritative-s3-not-covered-by-this-backup",
            storage_archive_included=False,
            s3_bucket="novu-prod-bucket",
            s3_region="us-east-1",
        )
        r = fx.run_restore(dump, **self._base_env)
        combined = r.stdout + r.stderr
        assert r.returncode == 0, combined
        assert "Production DR status: NOT VERIFIED" in combined
        assert "S3 protection prerequisites: PASSED" in combined
        assert "S3 pre-restore validation: PASSED" in combined
        assert "Variant A storage-readiness: FAILED" in combined
        assert "Variant A storage-readiness reason: manifest is missing s3_recovery_point" in combined
        assert "11. Release readiness decision: PASSED" in combined
        assert "Production DR: NOT VERIFIED" in combined


class TestRestoreMissingChecksum:
    def test_exits_nonzero(self, fx: Env) -> None:
        dump, sha, _ = fx.make_artifacts()
        sha.unlink()
        assert fx.run_restore(dump).returncode != 0

    def test_error_message(self, fx: Env) -> None:
        dump, sha, _ = fx.make_artifacts()
        sha.unlink()
        r = fx.run_restore(dump)
        assert "sha256" in (r.stdout + r.stderr).lower() or "Checksum" in (r.stdout + r.stderr)

    def test_no_destructive_docker_call(self, fx: Env) -> None:
        dump, sha, _ = fx.make_artifacts()
        sha.unlink()
        log = fx.docker_logging()
        fx.run_restore(dump)
        calls = log.read_text() if log.exists() else ""
        assert "stop backend" not in calls


# ═══════════════════════════════════════════════════════════════════════════════
# R3 — checksum mismatch
# ═══════════════════════════════════════════════════════════════════════════════

class TestRestoreChecksumMismatch:
    def test_exits_nonzero(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts()
        fx.sha256sum(verify_pass=False)
        assert fx.run_restore(dump).returncode != 0

    def test_error_message(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts()
        fx.sha256sum(verify_pass=False)
        r = fx.run_restore(dump)
        combined = (r.stdout + r.stderr).lower()
        assert "mismatch" in combined or "corrupt" in combined

    def test_no_destructive_docker_call(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts()
        fx.sha256sum(verify_pass=False)
        log = fx.docker_logging()
        fx.run_restore(dump)
        calls = log.read_text() if log.exists() else ""
        assert "stop backend" not in calls


# ═══════════════════════════════════════════════════════════════════════════════
# R4 — missing manifest
# ═══════════════════════════════════════════════════════════════════════════════

class TestRestoreMissingManifest:
    def test_exits_nonzero(self, fx: Env) -> None:
        dump, _, manifest = fx.make_artifacts()
        manifest.unlink()
        assert fx.run_restore(dump).returncode != 0

    def test_error_message(self, fx: Env) -> None:
        dump, _, manifest = fx.make_artifacts()
        manifest.unlink()
        r = fx.run_restore(dump)
        assert "manifest" in (r.stdout + r.stderr).lower()

    def test_no_destructive_docker_call(self, fx: Env) -> None:
        dump, _, manifest = fx.make_artifacts()
        manifest.unlink()
        log = fx.docker_logging()
        fx.run_restore(dump)
        calls = log.read_text() if log.exists() else ""
        assert "stop backend" not in calls


# ═══════════════════════════════════════════════════════════════════════════════
# R5 — invalid manifest content
# ═══════════════════════════════════════════════════════════════════════════════

class TestRestoreInvalidManifest:
    def _write_manifest(self, fx: Env, content: str) -> Path:
        dump, _, m = fx.make_artifacts()
        m.write_text(content)
        return dump

    def test_missing_db_file_key(self, fx: Env) -> None:
        dump = self._write_manifest(
            fx, '{"checksum_file":"db_20260101_120000.pgdump.sha256","backup_version":"v2"}\n'
        )
        r = fx.run_restore(dump)
        assert r.returncode != 0
        assert "manifest" in (r.stdout + r.stderr).lower()

    def test_missing_checksum_file_key(self, fx: Env) -> None:
        dump = self._write_manifest(
            fx, '{"db_file":"db_20260101_120000.pgdump","backup_version":"v2"}\n'
        )
        assert fx.run_restore(dump).returncode != 0

    def test_missing_backup_version_key(self, fx: Env) -> None:
        dump = self._write_manifest(
            fx, '{"db_file":"db_20260101_120000.pgdump","checksum_file":"db_20260101_120000.pgdump.sha256"}\n'
        )
        assert fx.run_restore(dump).returncode != 0

    def test_db_file_value_mismatch(self, fx: Env) -> None:
        dump = self._write_manifest(fx, (
            '{"db_file":"db_WRONG.pgdump",'
            '"checksum_file":"db_20260101_120000.pgdump.sha256",'
            '"backup_version":"v2"}\n'
        ))
        r = fx.run_restore(dump)
        assert r.returncode != 0
        combined = (r.stdout + r.stderr).lower()
        assert "mismatch" in combined or "manifest" in combined

    def test_checksum_file_value_mismatch(self, fx: Env) -> None:
        dump = self._write_manifest(fx, (
            '{"db_file":"db_20260101_120000.pgdump",'
            '"checksum_file":"db_WRONG.pgdump.sha256",'
            '"backup_version":"v2"}\n'
        ))
        r = fx.run_restore(dump)
        assert r.returncode != 0
        combined = (r.stdout + r.stderr).lower()
        assert "mismatch" in combined or "manifest" in combined

    def test_production_s3_manifest_with_storage_archive_claim_fails(self, fx: Env) -> None:
        dump = self._write_manifest(fx, (
            '{'
            '"app_env":"production",'
            '"storage_backend":"s3",'
            '"backup_contract":"db-restore-v1",'
            '"dr_contract":"variant-a-foundation-v1",'
            '"dr_recovery_point_model":"db-artifact-paired-with-explicit-s3-recovery-point",'
            '"backup_scope":"db-only",'
            '"production_dr_eligible":false,'
            '"storage_coverage":"authoritative-s3-not-covered-by-this-backup",'
            '"storage_archive_included":true,'
            '"db_file":"db_20260101_120000.pgdump",'
            '"checksum_file":"db_20260101_120000.pgdump.sha256",'
            '"backup_version":"v4"'
            '}\n'
        ))
        r = fx.run_restore(dump)
        combined = (r.stdout + r.stderr).lower()
        assert r.returncode != 0
        assert "storage archive coverage" in combined or "ambiguous production media claims" in combined

    def test_production_s3_manifest_with_wrong_storage_coverage_fails(self, fx: Env) -> None:
        dump = self._write_manifest(fx, (
            '{'
            '"app_env":"production",'
            '"storage_backend":"s3",'
            '"backup_contract":"db-restore-v1",'
            '"dr_contract":"variant-a-foundation-v1",'
            '"dr_recovery_point_model":"db-artifact-paired-with-explicit-s3-recovery-point",'
            '"backup_scope":"db-only",'
            '"production_dr_eligible":false,'
            '"storage_coverage":"full-production-dr",'
            '"storage_archive_included":false,'
            '"db_file":"db_20260101_120000.pgdump",'
            '"checksum_file":"db_20260101_120000.pgdump.sha256",'
            '"backup_version":"v4"'
            '}\n'
        ))
        r = fx.run_restore(dump)
        combined = (r.stdout + r.stderr).lower()
        assert r.returncode != 0
        assert "storage_coverage" in combined or "production+s3" in combined

    def test_storage_snapshot_consistent_requires_complete_s3_recovery_point_metadata(self, fx: Env) -> None:
        dump = self._write_manifest(fx, (
            '{'
            '"app_env":"production",'
            '"storage_backend":"s3",'
            '"backup_contract":"db-restore-v1",'
            '"dr_contract":"variant-a-foundation-v1",'
            '"dr_recovery_point_model":"db-artifact-paired-with-explicit-s3-recovery-point",'
            '"backup_scope":"db-only",'
            '"production_dr_eligible":false,'
            '"s3_bucket":"novu-prod-bucket",'
            '"s3_region":"us-east-1",'
            '"s3_recovery_point":null,'
            '"storage_snapshot_consistent":true,'
            '"storage_coverage":"authoritative-s3-not-covered-by-this-backup",'
            '"storage_archive_included":false,'
            '"db_file":"db_20260101_120000.pgdump",'
            '"checksum_file":"db_20260101_120000.pgdump.sha256",'
            '"backup_version":"v4"'
            '}\n'
        ))
        r = fx.run_restore(dump)
        combined = (r.stdout + r.stderr).lower()
        assert r.returncode != 0
        assert "storage_snapshot_consistent" in combined and "s3_recovery_point" in combined

    def test_non_s3_backend_with_s3_dr_metadata_fails(self, fx: Env) -> None:
        dump = self._write_manifest(fx, (
            '{'
            '"app_env":"development",'
            '"storage_backend":"local",'
            '"backup_contract":"db-restore-v1",'
            '"dr_contract":"variant-a-foundation-v1",'
            '"dr_recovery_point_model":"db-artifact-paired-with-explicit-s3-recovery-point",'
            '"backup_scope":"db-only",'
            '"production_dr_eligible":false,'
            '"s3_bucket":"novu-prod-bucket",'
            '"storage_coverage":"local-volume-archive-compatibility-only",'
            '"storage_archive_included":true,'
            '"storage_archive_file":"storage_20260101_120000.tar.gz",'
            '"db_file":"db_20260101_120000.pgdump",'
            '"checksum_file":"db_20260101_120000.pgdump.sha256",'
            '"backup_version":"v4"'
            '}\n'
        ))
        r = fx.run_restore(dump)
        combined = (r.stdout + r.stderr).lower()
        assert r.returncode != 0
        assert "s3 dr metadata" in combined or "storage_backend=s3" in combined


class TestRestoreSuccessSemantics:
    def test_no_success_summary_when_pg_restore_fails(self, fx: Env) -> None:
        fx.docker(pg_restore_exit_code=2)
        dump, _, _ = fx.make_artifacts()
        r = fx.run_restore(dump)
        combined = r.stdout + r.stderr
        assert r.returncode != 0, combined
        assert "pg_restore failed with exit code 2" in combined
        assert "DB restore contract: PASSED" not in combined
        assert "Restore handoff status:" not in combined

    def test_no_runtime_confirmed_message_when_liveness_fails(self, fx: Env) -> None:
        fx.curl(exit_code=1)
        dump, _, _ = fx.make_artifacts()
        r = fx.run_restore(dump)
        combined = r.stdout + r.stderr
        assert r.returncode != 0, combined
        assert "Restore handoff status: DB restore validated; runtime liveness confirmed." not in combined


# ═══════════════════════════════════════════════════════════════════════════════
# R6 — verify_restore.sh nonzero exit
# ═══════════════════════════════════════════════════════════════════════════════

class TestRestoreVerifyFail:
    def test_exits_nonzero(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts()
        verify = fx.verify_script(exit_code=1)
        r = fx.run_restore(dump, skip_verify=False, verify_script_path=verify)
        assert r.returncode != 0

    def test_error_message(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts()
        verify = fx.verify_script(exit_code=1)
        r = fx.run_restore(dump, skip_verify=False, verify_script_path=verify)
        combined = r.stdout + r.stderr
        assert "verify" in combined.lower() or "FAILED" in combined

    def test_no_destructive_docker_call(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts()
        verify = fx.verify_script(exit_code=1)
        log = fx.docker_logging()
        fx.run_restore(dump, skip_verify=False, verify_script_path=verify)
        calls = log.read_text() if log.exists() else ""
        assert "stop backend" not in calls


# ═══════════════════════════════════════════════════════════════════════════════
# R7 — verify times out (timeout exits 124)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRestoreVerifyTimeout:
    def test_exits_nonzero(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts()
        verify = fx.verify_script(exit_code=0)  # would pass, but timeout fires first
        fx.timeout(simulate_timeout=True)
        r = fx.run_restore(dump, skip_verify=False, verify_script_path=verify)
        assert r.returncode != 0

    def test_error_message(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts()
        verify = fx.verify_script(exit_code=0)
        fx.timeout(simulate_timeout=True)
        r = fx.run_restore(dump, skip_verify=False, verify_script_path=verify)
        combined = r.stdout + r.stderr
        assert "verify" in combined.lower() or "timed out" in combined.lower() or "FAILED" in combined

    def test_no_destructive_docker_call(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts()
        verify = fx.verify_script(exit_code=0)
        fx.timeout(simulate_timeout=True)
        log = fx.docker_logging()
        fx.run_restore(dump, skip_verify=False, verify_script_path=verify)
        calls = log.read_text() if log.exists() else ""
        assert "stop backend" not in calls
