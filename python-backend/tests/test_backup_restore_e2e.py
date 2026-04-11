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
import sqlite3
import stat
import subprocess
import sys
import tempfile
import textwrap
import uuid
from pathlib import Path
from typing import Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKUP_SH  = REPO_ROOT / "scripts" / "backup.sh"
RESTORE_SH = REPO_ROOT / "ops" / "restore.sh"
VALIDATE_RESTORED_MEDIA = REPO_ROOT / "python-backend" / "scripts" / "validate_restored_media.py"
LOCAL_TEST_ROOT = Path(tempfile.gettempdir()) / "novu_restore_e2e"
LOCAL_TEST_ROOT.mkdir(parents=True, exist_ok=True)

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


def _create_local_test_case_dir() -> Path:
    path = LOCAL_TEST_ROOT / f"restore_case_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
        consistency_check_exit_code: int = 0,
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
                *"check_storage_consistency.py"*)
                    if [[ {consistency_check_exit_code} -eq 0 ]]; then
                      echo "STORAGE_CONSISTENCY_SCAN_STATUS|scan_complete|db_to_s3=complete s3_to_db=complete"
                      exit 0
                    else
                      echo "STORAGE_CONSISTENCY_SCAN_STATUS|fail|db_to_s3=complete blockers=1 s3_to_db=complete"
                      exit {consistency_check_exit_code}
                    fi ;;
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

    def verify_script_with_steps(
        self,
        *,
        reference_sample_status: str = "PASSED",
        reference_sample_detail: str = "validated sampled DB-to-storage references",
        signed_url_status: str = "PASSED",
        signed_url_detail: str = "url check ok",
        app_smoke_status: str = "PASSED",
        app_smoke_detail: str = "smoke ok",
        exit_code: int = 0,
    ) -> Path:
        """
        Fake verify that emits structured POST_RESTORE_VALIDATION_STEP lines.
        Used to test that restore.sh captures and acts on verify substep statuses.
        """
        p = self.tmp / "fake_verify_steps.sh"
        _exe(p, textwrap.dedent(f"""\
            #!/usr/bin/env bash
            echo "POST_RESTORE_VALIDATION_STEP|db_query_usability|PASSED|critical tables exist and operational queries ok"
            echo "POST_RESTORE_VALIDATION_STEP|schema_head_alignment|PASSED|schema revision matches repository HEAD"
            echo "POST_RESTORE_VALIDATION_STEP|reference_sample_validation|{reference_sample_status}|{reference_sample_detail}"
            echo "POST_RESTORE_VALIDATION_STEP|signed_url_validation|{signed_url_status}|{signed_url_detail}"
            echo "POST_RESTORE_VALIDATION_STEP|app_media_smoke|{app_smoke_status}|{app_smoke_detail}"
            exit {exit_code}
        """))
        return p

    def s3_media_export_helper(self, *, unique_object_count: int = 2) -> Path:
        p = self.tmp / "fake_export_s3_manifest.py"
        p.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env python
            import argparse, json
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--database-url", required=True)
            parser.add_argument("--output", required=True)
            parser.add_argument("--bucket", required=True)
            parser.add_argument("--region", required=True)
            parser.add_argument("--declared-recovery-point", required=True)
            parser.add_argument("--db-backup-file", required=True)
            parser.add_argument("--db-manifest-file", required=True)
            args = parser.parse_args()

            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            payload = {{
                "format": "novu-s3-media-manifest-v1",
                "generated_at": "2026-03-31T00:00:00Z",
                "db_backup_file": args.db_backup_file,
                "db_manifest_file": args.db_manifest_file,
                "source_bucket": args.bucket,
                "source_region": args.region,
                "declared_recovery_point": args.declared_recovery_point,
                "storage_snapshot_consistent": True,
                "source_reference_count": {unique_object_count},
                "unique_object_count": {unique_object_count},
                "objects": [
                    {{
                        "key": f"projects/prj_{{idx}}/original.jpg",
                        "version_id": f"v{{idx}}",
                        "size": 10 + idx,
                        "etag": None,
                        "last_modified_at": "2026-03-31T00:00:00Z",
                        "references": [
                            {{
                                "source": "db.project_photo.original",
                                "organization_id": "org_1",
                                "project_id": f"prj_{{idx}}",
                                "record_id": f"pho_{{idx}}",
                            }}
                        ],
                    }}
                    for idx in range(1, {unique_object_count} + 1)
                ],
            }}
            output.write_text(json.dumps(payload, separators=(",", ":")) + "\\n", encoding="utf-8")
            print(json.dumps({{"status": "ok", "unique_object_count": {unique_object_count}}}, separators=(",", ":")))
        """), encoding="utf-8")
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return p

    def media_restore_helper(self, *, exit_code: int = 0) -> Path:
        p = self.tmp / "fake_restore_s3_media.py"
        p.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env python
            import argparse, json, sys
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--media-manifest", required=True)
            parser.add_argument("--target-bucket", required=True)
            parser.add_argument("--target-region", required=True)
            parser.add_argument("--output", required=True)
            args = parser.parse_args()
            if {exit_code} != 0:
                raise SystemExit({exit_code})
            manifest = json.loads(Path(args.media_manifest).read_text(encoding="utf-8"))
            objects = manifest.get("objects", [])
            payload = {{
                "format": "novu-restored-s3-media-v1",
                "restored_at": "2026-03-31T00:00:00Z",
                "source_bucket": manifest["source_bucket"],
                "source_region": manifest["source_region"],
                "target_bucket": args.target_bucket,
                "target_region": args.target_region,
                "db_backup_file": manifest["db_backup_file"],
                "db_manifest_file": manifest["db_manifest_file"],
                "declared_recovery_point": manifest["declared_recovery_point"],
                "object_count": len(objects),
                "app_compatible_key_layout": True,
                "objects": [
                    {{
                        "source_key": item["key"],
                        "target_key": item["key"],
                        "source_version_id": item["version_id"],
                        "size": item["size"],
                    }}
                    for item in objects
                ],
            }}
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(payload, separators=(",", ":")) + "\\n", encoding="utf-8")
            print(json.dumps({{"status": "ok", "object_count": len(objects), "target_bucket": args.target_bucket}}, separators=(",", ":")))
        """), encoding="utf-8")
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return p

    def media_validation_helper(
        self,
        *,
        reference_sample_status: str = "PASSED",
        signed_url_status: str = "PASSED",
        app_smoke_status: str = "PASSED",
        exit_code: int = 0,
    ) -> Path:
        p = self.tmp / "fake_validate_restored_media.py"
        p.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env python
            import argparse, json

            parser = argparse.ArgumentParser()
            parser.add_argument("--database-url", required=True)
            parser.add_argument("--sample-size", required=True)
            parser.parse_args()
            print("POST_RESTORE_VALIDATION_STEP|reference_sample_validation|{reference_sample_status}|validated restored DB references")
            print("POST_RESTORE_VALIDATION_STEP|signed_url_validation|{signed_url_status}|validated restored signed URL path")
            print("POST_RESTORE_VALIDATION_STEP|app_media_smoke|{app_smoke_status}|validated restored app media smoke")
            print("POST_RESTORE_VALIDATION_JSON=" + json.dumps({{"status": "ok"}}, separators=(",", ":")))
            raise SystemExit({exit_code})
        """), encoding="utf-8")
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return p

    def storage_consistency_helper(self, *, exit_code: int = 0) -> Path:
        p = self.tmp / "fake_check_storage_consistency.py"
        p.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env python
            import argparse

            parser = argparse.ArgumentParser()
            parser.add_argument("--database-url", required=False)
            parser.add_argument("--mode", required=True)
            parser.add_argument("--json-only", action="store_true")
            parser.parse_args()
            if {exit_code} == 0:
                print("STORAGE_CONSISTENCY_SCAN_STATUS|scan_complete|db_to_s3=complete s3_to_db=complete")
            else:
                print("STORAGE_CONSISTENCY_SCAN_STATUS|fail|db_to_s3=complete blockers=1 s3_to_db=complete")
            raise SystemExit({exit_code})
        """), encoding="utf-8")
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
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
        backup_scope: str = "db-only",
        production_dr_eligible: bool = False,
        s3_bucket: Optional[str] = None,
        s3_region: Optional[str] = None,
        s3_recovery_point: Optional[str] = None,
        storage_snapshot_consistent: Optional[bool] = None,
        s3_media_manifest_file: Optional[str] = None,
        s3_media_manifest_format: Optional[str] = None,
        s3_media_restore_strategy: Optional[str] = None,
        s3_object_count: Optional[int] = None,
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
            "backup_scope": backup_scope,
            "production_dr_eligible": production_dr_eligible,
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
        if s3_media_manifest_file is not None:
            manifest_payload["s3_media_manifest_file"] = s3_media_manifest_file
        if s3_media_manifest_format is not None:
            manifest_payload["s3_media_manifest_format"] = s3_media_manifest_format
        if s3_media_restore_strategy is not None:
            manifest_payload["s3_media_restore_strategy"] = s3_media_restore_strategy
        if s3_object_count is not None:
            manifest_payload["s3_object_count"] = s3_object_count
        manifest.write_text(json.dumps(manifest_payload, separators=(",", ":")) + "\n")
        return dump, sha, manifest

    def make_s3_media_manifest(
        self,
        *,
        db_backup_file: str,
        db_manifest_file: str,
        source_bucket: str,
        source_region: str,
        declared_recovery_point: str,
        unique_object_count: int = 2,
        object_count_override: Optional[int] = None,
    ) -> Path:
        manifest = self.bdir / Path(db_backup_file).with_suffix(".s3-media.json").name
        payload = {
            "format": "novu-s3-media-manifest-v1",
            "generated_at": "2026-03-31T00:00:00Z",
            "db_backup_file": db_backup_file,
            "db_manifest_file": db_manifest_file,
            "source_bucket": source_bucket,
            "source_region": source_region,
            "declared_recovery_point": declared_recovery_point,
            "storage_snapshot_consistent": True,
            "source_reference_count": unique_object_count,
            "unique_object_count": object_count_override if object_count_override is not None else unique_object_count,
            "objects": [
                {
                    "key": f"projects/prj_{idx}/original.jpg",
                    "version_id": f"v{idx}",
                    "size": 10 + idx,
                    "etag": None,
                    "last_modified_at": "2026-03-31T00:00:00Z",
                    "references": [
                        {
                            "source": "db.project_photo.original",
                            "organization_id": "org_1",
                            "project_id": f"prj_{idx}",
                            "record_id": f"pho_{idx}",
                        }
                    ],
                }
                for idx in range(1, unique_object_count + 1)
            ],
        }
        manifest.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
        return manifest

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

    def _require_working_bash(self) -> str:
        bash = self._bash()
        probe = subprocess.run(
            [bash, "-lc", "true"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        if probe.returncode != 0:
            detail = (probe.stderr or probe.stdout or "").strip()
            pytest.skip(f"bash-backed restore E2E is unavailable in this runner: {detail}")
        return bash

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
        bash = self._require_working_bash()
        return subprocess.run(
            [bash, str(BACKUP_SH)],
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
        bash = self._require_working_bash()
        cmd = [bash, str(RESTORE_SH), str(dump), "--yes"]
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

    def make_media_validation_fixture(
        self,
        *,
        include_photo: bool = True,
        include_export: bool = True,
        missing_storage_keys: tuple[str, ...] = (),
    ) -> tuple[str, Path]:
        db_path = self.tmp / "restore_validation.sqlite3"
        storage_root = self.tmp / "storage"
        storage_root.mkdir(exist_ok=True)

        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE organizations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                default_currency TEXT NOT NULL DEFAULT 'CZK',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                email TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_superadmin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                created_by_user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'mobile',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE project_photos (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                storage_key TEXT NOT NULL,
                preview_storage_key TEXT,
                ai_input_storage_key TEXT,
                original_filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                width INTEGER,
                height INTEGER,
                preview_file_size INTEGER,
                preview_width INTEGER,
                preview_height INTEGER,
                ai_input_file_size INTEGER,
                ai_input_width INTEGER,
                ai_input_height INTEGER,
                processing_status TEXT NOT NULL,
                taken_at TEXT,
                exif_lat REAL,
                exif_lng REAL,
                is_primary INTEGER NOT NULL,
                is_analysis_reference INTEGER NOT NULL,
                sort_order INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE project_exports (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                export_type TEXT NOT NULL,
                status TEXT NOT NULL,
                file_name TEXT NOT NULL,
                storage_key TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                expires_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO organizations (id, name) VALUES (?, ?)",
            ("org_1", "NOVU"),
        )
        conn.execute(
            "INSERT INTO users (id, organization_id, email, password_hash, full_name, role) VALUES (?, ?, ?, ?, ?, ?)",
            ("usr_1", "org_1", "restore@example.com", "hashed", "Restore User", "admin"),
        )
        conn.execute(
            "INSERT INTO projects (id, organization_id, created_by_user_id, title, status) VALUES (?, ?, ?, ?, ?)",
            ("prj_1", "org_1", "usr_1", "Restored project", "ready"),
        )

        if include_photo:
            conn.execute(
                """
                INSERT INTO project_photos (
                    id, project_id, status, storage_key, preview_storage_key, ai_input_storage_key,
                    original_filename, mime_type, file_size, width, height,
                    preview_file_size, preview_width, preview_height,
                    ai_input_file_size, ai_input_width, ai_input_height,
                    processing_status, taken_at, exif_lat, exif_lng,
                    is_primary, is_analysis_reference, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "pho_1",
                    "prj_1",
                    "active",
                    "projects/prj_1/original.jpg",
                    "projects/prj_1/preview.jpg",
                    None,
                    "original.jpg",
                    "image/jpeg",
                    12345,
                    1600,
                    1200,
                    3456,
                    800,
                    600,
                    None,
                    None,
                    None,
                    "ready",
                    "2026-03-30 00:00:00",
                    None,
                    None,
                    1,
                    1,
                    1,
                ),
            )

        if include_export:
            conn.execute(
                """
                INSERT INTO project_exports (
                    id, project_id, export_type, status, file_name, storage_key, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "exp_1",
                    "prj_1",
                    "pdf",
                    "completed",
                    "report.pdf",
                    "exports/prj_1/report.pdf",
                    "2026-04-06 00:00:00",
                ),
            )

        conn.commit()
        conn.close()

        for storage_key in (
            "projects/prj_1/original.jpg",
            "projects/prj_1/preview.jpg",
            "exports/prj_1/report.pdf",
        ):
            if storage_key in missing_storage_keys:
                continue
            target = storage_root / storage_key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fixture")

        return f"sqlite:///{db_path.resolve().as_posix()}", storage_root

    def run_media_validation(
        self,
        *,
        database_url: str,
        sample_size: int = 3,
        **env: str,
    ) -> subprocess.CompletedProcess:
        cmd = [
            sys.executable,
            str(VALIDATE_RESTORED_MEDIA),
            "--database-url",
            database_url,
            "--sample-size",
            str(sample_size),
        ]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=self._base_env(**env),
            cwd=str(REPO_ROOT),
        )


@pytest.fixture
def fx() -> Env:
    tmp_path = _create_local_test_case_dir()
    try:
        yield Env(tmp_path)
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_restore_fixture_uses_dedicated_local_temp_root() -> None:
    tmp_path = _create_local_test_case_dir()
    try:
        assert tmp_path.parent == LOCAL_TEST_ROOT
        assert tmp_path.name.startswith("restore_case_")
        assert tmp_path.is_dir()
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# B1 — valid backup run
# ═══════════════════════════════════════════════════════════════════════════════

class TestRestoreMediaValidationHelper:
    def test_sampled_db_to_storage_validation_passes_for_existing_media(self, fx: Env) -> None:
        database_url, storage_root = fx.make_media_validation_fixture()
        r = fx.run_media_validation(
            database_url=database_url,
            STORAGE_BACKEND="local",
            STORAGE_ROOT=str(storage_root),
        )
        combined = r.stdout + r.stderr
        assert r.returncode == 0, combined
        assert "POST_RESTORE_VALIDATION_STEP|reference_sample_validation|PASSED|" in combined
        assert "POST_RESTORE_VALIDATION_STEP|signed_url_validation|PASSED|" in combined
        assert "POST_RESTORE_VALIDATION_STEP|app_media_smoke|PASSED|" in combined

    def test_missing_db_referenced_object_is_a_hard_fail(self, fx: Env) -> None:
        database_url, storage_root = fx.make_media_validation_fixture(
            missing_storage_keys=("projects/prj_1/original.jpg",),
        )
        r = fx.run_media_validation(
            database_url=database_url,
            STORAGE_BACKEND="local",
            STORAGE_ROOT=str(storage_root),
        )
        combined = r.stdout + r.stderr
        assert r.returncode != 0, combined
        assert "POST_RESTORE_VALIDATION_STEP|reference_sample_validation|FAILED|" in combined
        assert "missing DB-referenced object" in combined
        assert "POST_RESTORE_VALIDATION_STEP|signed_url_validation|NOT EXECUTED|" in combined
        assert "POST_RESTORE_VALIDATION_STEP|app_media_smoke|NOT EXECUTED|" in combined

    def test_no_storage_references_is_out_of_scope_not_success_claim(self, fx: Env) -> None:
        database_url, storage_root = fx.make_media_validation_fixture(
            include_photo=False,
            include_export=False,
        )
        r = fx.run_media_validation(
            database_url=database_url,
            STORAGE_BACKEND="local",
            STORAGE_ROOT=str(storage_root),
        )
        combined = r.stdout + r.stderr
        assert r.returncode == 0, combined
        assert "POST_RESTORE_VALIDATION_STEP|reference_sample_validation|OUT OF SCOPE|" in combined
        assert "POST_RESTORE_VALIDATION_STEP|signed_url_validation|OUT OF SCOPE|" in combined
        assert "POST_RESTORE_VALIDATION_STEP|app_media_smoke|OUT OF SCOPE|" in combined


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
        assert "5. Media restore step: NOT EXECUTED" in combined
        assert "6. Media validation step: NOT EXECUTED" in combined
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
        assert "Release readiness decision: PASSED (DB handoff ready with validated DB<->storage consistency; Production DR remains NOT VERIFIED)" in combined
        assert "Authoritative S3/object storage recovery: NOT VERIFIED / OUT OF SCOPE" in combined


class TestBackupProductionS3FullStateSemantics:
    _s3_env = dict(
        APP_ENV="production",
        STORAGE_BACKEND="s3",
        S3_BUCKET="novu-prod-bucket",
        S3_REGION="us-east-1",
        S3_RECOVERY_POINT="versioned-bucket@2026-03-30T01:15:00Z",
        STORAGE_SNAPSHOT_CONSISTENT="true",
        S3_FULL_COVERAGE_DECLARED="true",
        AWS_ACCESS_KEY_ID="test-access-key",
        AWS_SECRET_ACCESS_KEY="test-secret-key",
        DATABASE_URL="sqlite:///placeholder.sqlite3",
    )

    def test_full_state_opt_in_writes_media_manifest_and_marks_backup_scope(self, fx: Env) -> None:
        helper = fx.s3_media_export_helper(unique_object_count=2)
        r = fx.run_backup(
            **self._s3_env,
            S3_MEDIA_EXPORT_HELPER_OVERRIDE=fx._bash_path(helper),
        )
        combined = r.stdout + r.stderr
        assert r.returncode == 0, combined
        manifest = json.loads(next(fx.bdir.glob("db_*.json")).read_text())
        assert manifest["backup_scope"] == "db-plus-s3-media-manifest"
        assert manifest["production_dr_eligible"] is True
        assert manifest["dr_contract"] == "s3-full-state-v1"
        assert manifest["dr_recovery_point_model"] == "db-artifact-paired-with-versioned-s3-object-manifest"
        assert manifest["s3_media_manifest_format"] == "novu-s3-media-manifest-v1"
        assert manifest["s3_media_restore_strategy"] == "versioned-copy-to-isolated-bucket-v1"
        assert manifest["s3_object_count"] == 2
        assert (fx.bdir / manifest["s3_media_manifest_file"]).is_file()

    def test_full_state_backup_output_is_explicitly_conditional(self, fx: Env) -> None:
        helper = fx.s3_media_export_helper(unique_object_count=2)
        r = fx.run_backup(
            **self._s3_env,
            S3_MEDIA_EXPORT_HELPER_OVERRIDE=fx._bash_path(helper),
        )
        combined = r.stdout + r.stderr
        assert r.returncode == 0, combined
        assert "version-pinned S3 media manifest" in combined
        assert "eligible only after isolated media restore + validation succeeds" in combined


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
        assert "5. Media restore step: NOT EXECUTED" in combined
        assert "6. Media validation step: NOT EXECUTED" in combined
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


class TestRestoreProductionS3FullState:
    _base_env = dict(
        APP_ENV="production",
        STORAGE_BACKEND="s3",
        S3_BUCKET="novu-prod-bucket",
        S3_REGION="us-east-1",
        S3_RESTORE_TARGET_BUCKET="novu-restore-bucket",
        S3_RESTORE_TARGET_REGION="us-east-1",
        AWS_ACCESS_KEY_ID="test-access-key",
        AWS_SECRET_ACCESS_KEY="test-secret-key",
        DATABASE_URL="sqlite:///restore-validation.sqlite3",
    )

    def _make_full_state_dump(self, fx: Env, *, object_count_override: Optional[int] = None) -> Path:
        dump, _, manifest = fx.make_artifacts(
            app_env="production",
            storage_backend="s3",
            storage_coverage="authoritative-s3-media-manifest",
            storage_archive_included=False,
            dr_contract="s3-full-state-v1",
            dr_recovery_point_model="db-artifact-paired-with-versioned-s3-object-manifest",
            backup_scope="db-plus-s3-media-manifest",
            production_dr_eligible=True,
            s3_bucket="novu-prod-bucket",
            s3_region="us-east-1",
            s3_recovery_point="versioned-bucket@2026-03-30T01:15:00Z",
            storage_snapshot_consistent=True,
            s3_media_manifest_file=f"db_{_TS}.s3-media.json",
            s3_media_manifest_format="novu-s3-media-manifest-v1",
            s3_media_restore_strategy="versioned-copy-to-isolated-bucket-v1",
            s3_object_count=2,  # DB manifest always declares 2; override only affects media manifest
        )
        fx.make_s3_media_manifest(
            db_backup_file=dump.name,
            db_manifest_file=manifest.name,
            source_bucket="novu-prod-bucket",
            source_region="us-east-1",
            declared_recovery_point="versioned-bucket@2026-03-30T01:15:00Z",
            unique_object_count=2,
            object_count_override=object_count_override,
        )
        return dump

    def test_missing_restore_target_bucket_fails_before_destructive_restore(self, fx: Env) -> None:
        dump = self._make_full_state_dump(fx)
        log = fx.docker_logging()
        env = dict(self._base_env)
        env.pop("S3_RESTORE_TARGET_BUCKET")
        r = fx.run_restore(dump, **env)
        combined = (r.stdout + r.stderr).lower()
        calls = log.read_text() if log.exists() else ""
        assert r.returncode != 0, combined
        assert "s3_restore_target_bucket is required" in combined
        assert "stop backend" not in calls

    def test_pairing_mismatch_fails_before_destructive_restore(self, fx: Env) -> None:
        dump = self._make_full_state_dump(fx, object_count_override=3)
        log = fx.docker_logging()
        r = fx.run_restore(dump, **self._base_env)
        combined = (r.stdout + r.stderr).lower()
        calls = log.read_text() if log.exists() else ""
        assert r.returncode != 0, combined
        assert "s3 media manifest object count does not match the db manifest" in combined
        assert "stop backend" not in calls

    def test_full_state_restore_happy_path_verifies_production_dr(self, fx: Env) -> None:
        dump = self._make_full_state_dump(fx)
        restore_helper = fx.media_restore_helper()
        validation_helper = fx.media_validation_helper()
        consistency_helper = fx.storage_consistency_helper()
        r = fx.run_restore(
            dump,
            **self._base_env,
            MEDIA_RESTORE_HELPER_OVERRIDE=fx._bash_path(restore_helper),
            MEDIA_VALIDATE_HELPER_OVERRIDE=fx._bash_path(validation_helper),
            STORAGE_CONSISTENCY_HELPER_OVERRIDE=fx._bash_path(consistency_helper),
        )
        combined = r.stdout + r.stderr
        assert r.returncode == 0, combined
        assert "5. Media restore step: PASSED" in combined
        assert "6. Media validation step: PASSED" in combined
        assert "production_dr_eligible: true" in combined
        assert "Full-state restore claim: VERIFIED" in combined
        assert "Production DR status: VERIFIED" in combined
        assert "Production DR: VERIFIED" in combined
        assert "Authoritative S3/object storage recovery: VERIFIED" in combined
        assert "Restored isolated bucket: novu-restore-bucket" in combined


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


# ═══════════════════════════════════════════════════════════════════════════════
# DR Claim Gating — explicit production_dr_eligible and RELEASE_READINESS gates
# ═══════════════════════════════════════════════════════════════════════════════

class TestDrClaimGating:
    """
    Tests for the explicit DR claim gating model.

    Verifies that:
      - DB-only manifests keep production_dr_eligible=false
      - RELEASE_READINESS_DECISION is gated on all required conditions
      - verify substep statuses are captured and fed into the decision gate
      - DB-only restore paths never overclaim Production DR
      - The DR claim decision block is present and correctly labelled
    """

    # ── backup manifest ───────────────────────────────────────────────────────

    def test_production_dr_eligible_is_always_false_in_backup_manifest(self, fx: Env) -> None:
        """DB-only local backup manifests must keep production_dr_eligible=false."""
        fx.run_backup()
        manifest = json.loads(next(fx.bdir.glob("db_*.json")).read_text())
        assert manifest["production_dr_eligible"] is False

    def test_production_dr_eligible_false_in_s3_production_manifest(self, fx: Env) -> None:
        """Default production+s3 DB-only fallback must keep production_dr_eligible=false."""
        fx.run_backup(
            APP_ENV="production",
            STORAGE_BACKEND="s3",
            S3_BUCKET="novu-prod-bucket",
            S3_REGION="us-east-1",
            S3_RECOVERY_POINT="versioned-bucket@2026-03-30T01:15:00Z",
            STORAGE_SNAPSHOT_CONSISTENT="true",
        )
        manifest = json.loads(next(fx.bdir.glob("db_*.json")).read_text())
        assert manifest["production_dr_eligible"] is False

    # ── DR claim decision block ───────────────────────────────────────────────

    def test_dr_claim_decision_block_present_in_restore_output(self, fx: Env) -> None:
        """The DR claim decision block must appear in the restore output."""
        dump, _, _ = fx.make_artifacts()
        r = fx.run_restore(dump)
        combined = r.stdout + r.stderr
        assert r.returncode == 0, combined
        assert "DR Claim Decision" in combined

    def test_dr_claim_decision_block_shows_production_dr_not_verified(self, fx: Env) -> None:
        """The decision block must show Production DR verified: NOT VERIFIED."""
        dump, _, _ = fx.make_artifacts()
        r = fx.run_restore(dump)
        combined = r.stdout + r.stderr
        assert "Production DR verified:      NOT VERIFIED" in combined

    def test_dr_claim_decision_block_shows_production_dr_eligible_false(self, fx: Env) -> None:
        """The decision block must show production_dr_eligible: false."""
        dump, _, _ = fx.make_artifacts()
        r = fx.run_restore(dump)
        combined = r.stdout + r.stderr
        assert "production_dr_eligible:      false" in combined

    def test_dr_claim_decision_block_lists_unmet_conditions(self, fx: Env) -> None:
        """The decision block must enumerate each condition that is not met."""
        dump, _, _ = fx.make_artifacts()
        r = fx.run_restore(dump)
        combined = r.stdout + r.stderr
        assert "Backup set validation:" in combined
        assert "DB restore:" in combined
        assert "Schema/head alignment:" in combined
        assert "Post-restore validation:" in combined
        assert "DB-referenced objects:" in combined
        assert "Storage consistency gate:" in combined

    def test_dr_claim_decision_block_shows_full_state_restore_not_verified(self, fx: Env) -> None:
        """The decision block must show the full-state restore claim as NOT VERIFIED."""
        dump, _, _ = fx.make_artifacts()
        r = fx.run_restore(dump)
        combined = r.stdout + r.stderr
        assert "Full-state restore claim:    NOT VERIFIED" in combined

    # ── DB-only paths never overclaim Production DR ──────────────────────────

    def test_production_dr_never_verified_on_happy_path(self, fx: Env) -> None:
        """Even when all restore steps pass, Production DR must remain NOT VERIFIED."""
        dump, _, _ = fx.make_artifacts()
        r = fx.run_restore(dump)
        combined = r.stdout + r.stderr
        assert r.returncode == 0, combined
        assert "Production DR status: NOT VERIFIED" in combined
        assert "Production DR: NOT VERIFIED" in combined
        assert "Production DR remains NOT VERIFIED" in combined

    def test_production_dr_not_verified_when_s3_and_liveness_pass(self, fx: Env) -> None:
        """Production DR must not be claimed verified even when S3 and liveness all pass."""
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
        assert "Production DR: NOT VERIFIED" in combined
        assert "Production DR: VERIFIED" not in combined
        assert "Production DR status: VERIFIED" not in combined
        assert "production_dr_eligible: false" in combined
        assert "Full-state restore claim: NOT VERIFIED" in combined

    def test_no_dr_verified_wording_in_any_restore_output(self, fx: Env) -> None:
        """No form of 'DR: VERIFIED' or 'DR status: VERIFIED' may appear in restore output."""
        dump, _, _ = fx.make_artifacts()
        r = fx.run_restore(dump)
        combined = r.stdout + r.stderr
        assert "DR: VERIFIED" not in combined
        assert "DR status: VERIFIED" not in combined

    # ── verify substep capture and gating ────────────────────────────────────

    def test_verify_substep_statuses_appear_in_restore_summary(self, fx: Env) -> None:
        """When verify emits step lines, they must appear in the restore orchestration summary."""
        dump, _, _ = fx.make_artifacts()
        verify = fx.verify_script_with_steps(
            reference_sample_status="PASSED",
            reference_sample_detail="validated 3 sampled DB-to-storage references",
        )
        r = fx.run_restore(dump, skip_verify=False, verify_script_path=verify)
        combined = r.stdout + r.stderr
        assert r.returncode == 0, combined
        assert "Verified DB -> storage sampled references: PASSED" in combined

    def test_verify_reference_failure_blocks_release_readiness(self, fx: Env) -> None:
        """
        If verify exits 0 but emits FAILED for reference_sample_validation, the restore
        must block RELEASE_READINESS_DECISION — fail-closed gate on verify substeps.
        """
        dump, _, _ = fx.make_artifacts()
        verify = fx.verify_script_with_steps(
            reference_sample_status="FAILED",
            reference_sample_detail="missing DB-referenced object key=projects/p1/photo.jpg",
            exit_code=0,  # verify exits 0 — substep gate must still block
        )
        r = fx.run_restore(dump, skip_verify=False, verify_script_path=verify)
        combined = r.stdout + r.stderr
        assert r.returncode != 0, (
            "restore must exit non-zero when DB-referenced objects validation FAILED, "
            "even if verify itself exited 0"
        )
        assert "Verified DB -> storage sampled references: FAILED" in combined
        assert "11. Release readiness decision: FAILED" in combined
        assert "DB restore contract: PASSED" in combined
        assert "production_dr_eligible:      false" in combined
        assert "Production DR verified:      NOT VERIFIED" in combined

    def test_verify_reference_failure_does_not_misreport_db_restore_as_failed(self, fx: Env) -> None:
        """
        A failed reference validation blocks RELEASE_READINESS_DECISION
        but must not misreport the DB restore step itself as failed.
        """
        dump, _, _ = fx.make_artifacts()
        verify = fx.verify_script_with_steps(
            reference_sample_status="FAILED",
            reference_sample_detail="missing key=projects/p1/photo.jpg",
            exit_code=0,
        )
        r = fx.run_restore(dump, skip_verify=False, verify_script_path=verify)
        combined = r.stdout + r.stderr
        assert r.returncode != 0, combined
        assert "DB restore contract: PASSED" in combined
        assert "11. Release readiness decision: FAILED" in combined

    def test_verify_signed_url_failure_blocks_release_readiness_and_claim(self, fx: Env) -> None:
        """Signed URL/access path failure must keep production DR explicitly NOT VERIFIED."""
        dump, _, _ = fx.make_artifacts()
        verify = fx.verify_script_with_steps(
            signed_url_status="FAILED",
            signed_url_detail="signed URL generation failed for sampled storage key",
        )
        r = fx.run_restore(dump, skip_verify=False, verify_script_path=verify)
        combined = r.stdout + r.stderr
        assert r.returncode != 0, combined
        assert "Verified signed URL / storage access path: FAILED" in combined
        assert "11. Release readiness decision: FAILED" in combined
        assert "production_dr_eligible:      false" in combined
        assert "Production DR verified:      NOT VERIFIED" in combined

    def test_verify_app_media_smoke_failure_blocks_release_readiness_and_claim(self, fx: Env) -> None:
        """Application media smoke failure must keep production DR explicitly NOT VERIFIED."""
        dump, _, _ = fx.make_artifacts()
        verify = fx.verify_script_with_steps(
            app_smoke_status="FAILED",
            app_smoke_detail="photo read-model smoke failed for sampled media reference",
        )
        r = fx.run_restore(dump, skip_verify=False, verify_script_path=verify)
        combined = r.stdout + r.stderr
        assert r.returncode != 0, combined
        assert "Verified application media smoke: FAILED" in combined
        assert "11. Release readiness decision: FAILED" in combined
        assert "production_dr_eligible:      false" in combined
        assert "Production DR verified:      NOT VERIFIED" in combined

    def test_verify_substep_failure_reason_explicit_in_output(self, fx: Env) -> None:
        """The failure reason must reference the blocking condition explicitly."""
        dump, _, _ = fx.make_artifacts()
        verify = fx.verify_script_with_steps(
            reference_sample_status="FAILED",
            reference_sample_detail="missing key=projects/p1/photo.jpg",
            exit_code=0,
        )
        r = fx.run_restore(dump, skip_verify=False, verify_script_path=verify)
        combined = r.stdout + r.stderr
        assert r.returncode != 0, combined
        assert "DB-referenced storage objects validation" in combined

    def test_full_storage_consistency_failure_blocks_release(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts()
        fx.docker(consistency_check_exit_code=1)

        r = fx.run_restore(dump)
        combined = r.stdout + r.stderr

        assert r.returncode != 0, combined
        assert "12. Storage consistency check (DB<->S3): FAILED" in combined
        assert "11. Release readiness decision: FAILED" in combined
        assert "Full DB<->storage consistency validation: FAILED" in combined

    # ── separated claims ──────────────────────────────────────────────────────

    def test_db_restore_liveness_and_dr_are_reported_as_distinct_claims(self, fx: Env) -> None:
        """DB restore success, backend liveness, and Production DR must be separate claims."""
        dump, _, _ = fx.make_artifacts()
        r = fx.run_restore(dump)
        combined = r.stdout + r.stderr
        assert r.returncode == 0, combined
        assert "DB restore contract: PASSED" in combined
        assert "Backend liveness probe: PASSED" in combined
        assert "Production DR: NOT VERIFIED" in combined

    def test_restore_rejects_manifest_with_production_dr_eligible_true(self, fx: Env) -> None:
        """
        ops/restore.sh must reject a DB-only manifest that claims production_dr_eligible=true.
        Full-state eligibility is valid only for the explicit db-plus-s3-media-manifest scope.
        """
        dump, _, _ = fx.make_artifacts()
        bad_manifest = fx.bdir / f"db_{_TS}.json"
        bad_manifest.write_text(json.dumps({
            "timestamp": _TS,
            "app_env": "development",
            "backup_contract": "db-restore-v1",
            "backup_scope": "db-only",
            "production_dr_eligible": True,
            "storage_backend": "local",
            "s3_bucket": None,
            "s3_region": None,
            "s3_recovery_point": None,
            "storage_snapshot_consistent": None,
            "storage_coverage": "local-volume-archive-compatibility-only",
            "storage_archive_included": True,
            "storage_archive_file": f"storage_{_TS}.tar.gz",
            "db_file": f"db_{_TS}.pgdump",
            "checksum_file": f"db_{_TS}.pgdump.sha256",
            "backup_version": "v4",
            "alembic_head": REPO_ALEMBIC_HEAD,
            "git_sha": "abc1234",
        }) + "\n")
        r = fx.run_restore(dump)
        combined = r.stdout + r.stderr
        assert r.returncode != 0, "restore must reject manifest with production_dr_eligible=true"
        assert "production_dr_eligible" in combined.lower()
