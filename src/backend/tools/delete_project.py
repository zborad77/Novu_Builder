import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

BACKEND_ROOT = Path(__file__).resolve().parents[1]
os.chdir(BACKEND_ROOT)
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import AsyncSessionFactory
from app.models import Project
from app.storage.local_photo_storage import STORAGE_ROOT


async def delete_project(*, project_id: str, allow_prefix: str | None) -> int:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.photos))
            .where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if project is None:
            print(f"project-not-found {project_id}")
            return 2

        if allow_prefix and not project.id.startswith(allow_prefix):
            print(f"project-prefix-denied {project.id} expected_prefix={allow_prefix}")
            return 3

        await session.delete(project)
        await session.commit()

    shutil.rmtree(STORAGE_ROOT / "projects" / project_id, ignore_errors=True)
    shutil.rmtree(STORAGE_ROOT / "exports" / project_id, ignore_errors=True)
    print(f"project-deleted {project_id}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delete a dev project and its storage artifacts.")
    parser.add_argument("--project-id", required=True, help="Project ID to remove.")
    parser.add_argument(
        "--allow-prefix",
        default=None,
        help="Optional safety guard. Project ID must start with this prefix.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(asyncio.run(delete_project(project_id=args.project_id, allow_prefix=args.allow_prefix)))
