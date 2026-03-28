"""
E2E tests for backup/restore workflow (scripts/backup.sh, ops/restore.sh).

Strategy: subprocess + fake binaries injected via PATH override.
No real Docker, no real DB, no real remote storage — fully isolated.

Scenarios covered:
  Backup:
    B1  valid run → pgdump + sha256 + manifest created
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

import os
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
        _exe(self.bin / "du",    "#!/usr/bin/env bash\necho \"4.0K\t${@: -1}\"\n")
        _exe(self.bin / "sleep", "#!/usr/bin/env bash\nexit 0\n")
        _exe(self.bin / "seq",   "#!/usr/bin/env bash\nfor i in $(eval \"echo {1..$1}\"); do echo \"$i\"; done\n")

    def docker(self, alembic_head: str = "abc1234", pg_dump_fail: bool = False) -> None:
        pg_body = (
            "exit 1"
            if pg_dump_fail
            else "python3 -c \"import sys; sys.stdout.buffer.write(b'PGDMP' + b'x' * 2048)\" 2>/dev/null"
        )
        _exe(self.bin / "docker", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            args="$*"
            case "$args" in
                *pg_dump*)              {pg_body} ;;
                *alembic_version*)      echo "{alembic_head}" ;;
                *"ps -q"*)             echo "fake_container_id" ;;
                *" cp "*)              true ;;
                *" rm "*)              true ;;
                *pg_restore*)          true ;;
                *"run --rm backend"*)  true ;;
                *"start backend"*)     true ;;
                *"stop backend"*)      true ;;
                *psql*)
                    if   [[ "$args" == *"EXISTS"*      ]]; then echo "t"
                    elif [[ "$args" == *"version_num"* ]]; then echo "abc1234"
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

    # ── artifact helpers ──────────────────────────────────────────────────────

    def make_artifacts(self, ts: str = _TS) -> tuple[Path, Path, Path]:
        """
        Create a valid backup artifact set (dump, sha256, manifest).
        Manifest is named db_TS.json to match restore.sh derivation logic:
          MANIFEST_FILE="${BACKUP_FILE%.pgdump}.json"
        """
        dump = self.bdir / f"db_{ts}.pgdump"
        dump.write_bytes(b"PGDMP" + b"x" * 2048)

        sha = self.bdir / f"db_{ts}.pgdump.sha256"
        sha.write_text(f"aabbccdd1234  {dump}\n")

        manifest = self.bdir / f"db_{ts}.json"
        manifest.write_text(
            f'{{"timestamp":"{ts}",'
            f'"db_file":"db_{ts}.pgdump",'
            f'"checksum_file":"db_{ts}.pgdump.sha256",'
            f'"backup_version":"v2",'
            f'"alembic_head":"abc1234","git_sha":"abc1234"}}\n'
        )
        return dump, sha, manifest

    # ── runners ───────────────────────────────────────────────────────────────

    def _base_env(self, **overrides: str) -> dict:
        e = {
            **os.environ,
            "PATH":          f"{self.bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "BACKUP_DIR":    str(self.bdir),
            "POSTGRES_USER": "novu",
            "POSTGRES_DB":   "novu_builder",
            "RETAIN_DAYS":   "7",
        }
        e.update(overrides)
        return e

    def run_backup(self, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(BACKUP_SH)],
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
        cmd = ["bash", str(RESTORE_SH), str(dump), "--yes"]
        if skip_verify:
            cmd.append("--skip-verify")
        e = self._base_env(**env)
        if verify_script_path is not None:
            e["VERIFY_SCRIPT_OVERRIDE"] = str(verify_script_path)
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
        assert len(list(fx.bdir.glob("manifest_*.json"))) == 1

    def test_manifest_has_required_keys(self, fx: Env) -> None:
        fx.run_backup()
        content = next(fx.bdir.glob("manifest_*.json")).read_text()
        for key in ("db_file", "checksum_file", "backup_version", "alembic_head", "git_sha"):
            assert f'"{key}"' in content, f"manifest missing key: {key}"


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
        assert len(list(fx.bdir.glob("manifest_*.json"))) == 1

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
        content = next(fx.bdir.glob("manifest_*.json")).read_text()
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

    def test_restore_complete_message(self, fx: Env) -> None:
        dump, _, _ = fx.make_artifacts()
        r = fx.run_restore(dump)
        assert "RESTORE COMPLETE" in r.stdout


# ═══════════════════════════════════════════════════════════════════════════════
# R2 — missing .sha256
# ═══════════════════════════════════════════════════════════════════════════════

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
