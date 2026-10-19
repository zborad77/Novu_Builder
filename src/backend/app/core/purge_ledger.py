"""Append-only record of permanent photo deletions, kept outside the database.

A database restore rolls back ``audit_logs`` together with the photo rows, so the
audit trail alone cannot tell which photos must be erased again. Every permanent
deletion is therefore also written here *before* it is committed. The file lives
outside the database (PHOTO_PURGE_LEDGER_PATH), must be shipped off-host with the
log archive, and is read by ``scripts/reapply_photo_purges.py --ledger`` after a
restore (docs/security/PHOTO_DELETION.md §5).

One JSON object per line:
{"ts": "...Z", "photo_id": ..., "case_id": ..., "org_id": ..., "actor_id": ..., "action": ...}
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path


class PurgeLedgerError(RuntimeError):
    pass


def append_purge_entry(path: str, entry: dict) -> None:
    """Durably append one entry (flush + fsync). Raises PurgeLedgerError on failure."""
    line = json.dumps({"ts": datetime.now(UTC).isoformat(), **entry}, ensure_ascii=False, sort_keys=True)
    try:
        ledger = Path(path)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise PurgeLedgerError(f"Cannot append to photo purge ledger: {exc}") from exc


def read_purged_photo_ids(path: str | Path, *, since: datetime | None = None) -> list[str]:
    """Photo ids purged at or after ``since`` (all when None), in ledger order, unique."""
    ids: dict[str, None] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        entry = json.loads(raw)
        if since is not None and datetime.fromisoformat(entry["ts"]) < since:
            continue
        ids[entry["photo_id"]] = None
    return list(ids)
