#!/usr/bin/env python3
"""
Re-apply permanent photo deletions after restoring a database/storage backup.

A backup taken before a permanent deletion still contains the photo row and its
files. After a restore, purge again every photo recorded in the off-database purge
ledger (PHOTO_PURGE_LEDGER_PATH) since the backup was taken
(docs/security/PHOTO_DELETION.md §5):

    python -m scripts.reapply_photo_purges --confirm --ledger /var/lib/novu/photo-purge-ledger.jsonl         --since 2026-10-17T02:00:00+00:00
    python -m scripts.reapply_photo_purges --confirm pho_ab12cd34 pho_ef56ab78
    python -m scripts.reapply_photo_purges --confirm --from-file purged_ids.txt

Idempotent: photos already ``deleted`` or absent are reported and skipped.
Each purge is audited (``system.image.purge``) and uses the same two-phase path
as the API (hidden + exports expired first, storage removal second). Photos whose
storage removal fails stay ``purge_pending`` and the worker finishes them.
"""
import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.audit import commit_security_critical_audit
from app.core.config import get_settings
from app.core.purge_ledger import read_purged_photo_ids
from app.models.domain import Project
from app.repositories.photo_repository import PhotoRepository
from app.services.photo_service import PhotoService

SYSTEM_ACTOR = "system:reapply_photo_purges"


async def _reapply(photo_ids: list[str]) -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    pending = 0
    try:
        for photo_id in photo_ids:
            async with session_factory() as session:
                service = PhotoService(PhotoRepository(session))
                photo = await service.get_photo_any_status(photo_id)
                if photo is None:
                    print(f"{photo_id}: not in this database, skipped")
                    continue
                if photo.status == "deleted":
                    print(f"{photo_id}: already deleted, skipped")
                    continue
                if photo.status != "purge_pending":
                    previous_status = photo.status
                    project = await session.get(Project, photo.project_id)
                    staged = await service.stage_purge(photo, actor_user_id=None)
                    await commit_security_critical_audit(
                        session,
                        current_user_id=SYSTEM_ACTOR,
                        action="system.image.purge",
                        resource_type="image",
                        resource_id=photo.id,
                        detail={
                            "case_id": photo.project_id,
                            "target_org": project.organization_id if project else None,
                            "previous_status": previous_status,
                            **staged,
                            "reason": "re-applied after backup restore",
                        },
                    )
                if await service.complete_purge(photo):
                    print(f"{photo_id}: purged")
                else:
                    pending += 1
                    print(f"{photo_id}: purge_pending (storage unavailable; the worker will retry)")
    finally:
        await engine.dispose()
    return pending


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("photo_ids", nargs="*", help="Photo ids to purge permanently.")
    parser.add_argument("--from-file", type=Path, help="File with one photo id per line.")
    parser.add_argument("--ledger", type=Path, help="Purge ledger (PHOTO_PURGE_LEDGER_PATH) to read ids from.")
    parser.add_argument(
        "--since",
        type=datetime.fromisoformat,
        help="With --ledger: only entries at/after this ISO-8601 time (the backup timestamp, with offset).",
    )
    parser.add_argument("--confirm", action="store_true", help="Required: permanent deletion cannot be undone.")
    args = parser.parse_args()

    photo_ids = list(args.photo_ids)
    if args.from_file:
        photo_ids += [line.strip() for line in args.from_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.ledger:
        photo_ids += read_purged_photo_ids(args.ledger, since=args.since)
    elif args.since:
        parser.error("--since requires --ledger")
    photo_ids = list(dict.fromkeys(photo_ids))
    if not photo_ids:
        parser.error("no photo ids given")
    if not args.confirm:
        parser.error("--confirm is required; this permanently deletes photos")

    pending = asyncio.run(_reapply(photo_ids))
    return 1 if pending else 0


if __name__ == "__main__":
    sys.exit(main())
