import asyncio
import json
from pathlib import Path
import sys

from sqlalchemy import func, select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.bootstrap import ensure_dev_seed
from app.db.session import AsyncSessionFactory
from app.models import Project, ProjectPhoto
from app.storage.backend import sanitize_filename, write_storage_file


DATASET_ROOT = BACKEND_ROOT.parent / "test-data" / "reference-cases"


def load_manifest(case_dir: Path) -> dict:
    return json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))


def build_storage_key(project_id: str, folder: str, filename: str) -> str:
    folder_path = Path("projects") / project_id / folder
    if folder == "original":
        return (Path("projects") / project_id / filename).as_posix()
    return (folder_path / filename).as_posix()


def build_reference_expectations(manifest: dict) -> str:
    expected_primary = next((photo["file"] for photo in manifest["photos"] if photo.get("expectedPrimary")), None)
    expected_analysis_reference = next(
        (photo["file"] for photo in manifest["photos"] if photo.get("expectedAnalysisReference")),
        None,
    )
    return json.dumps(
        {
            "sourceRepo": manifest.get("sourceRepo"),
            "sourcePage": manifest.get("sourcePage"),
            "expectedScope": manifest.get("expectedScope"),
            "expectedPrimaryFilename": expected_primary,
            "expectedAnalysisReferenceFilename": expected_analysis_reference,
        },
        ensure_ascii=False,
    )


async def import_reference_cases() -> None:
    case_dirs = sorted(path for path in DATASET_ROOT.iterdir() if path.is_dir())
    if not case_dirs:
        print("no-reference-cases-found")
        return

    async with AsyncSessionFactory() as session:
        await ensure_dev_seed(session)

        imported_projects = 0
        skipped_projects = 0

        for case_dir in case_dirs:
            manifest = load_manifest(case_dir)
            project_id = f"ref_{manifest['caseId']}"
            reference_expectations_json = build_reference_expectations(manifest)
            existing_project = await session.get(Project, project_id)
            if existing_project is not None:
                existing_project.reference_expectations_json = reference_expectations_json
                if not existing_project.description and manifest.get("expectedSummary"):
                    existing_project.description = manifest.get("expectedSummary")
                if not existing_project.repair_scope and manifest.get("expectedScope"):
                    existing_project.repair_scope = manifest.get("expectedScope")
                skipped_projects += 1
                print(f"sync-project {project_id}")
                continue

            project = Project(
                id=project_id,
                organization_id="org_1",
                client_id="cli_1",
                created_by_user_id="usr_1",
                title=manifest["title"],
                description=manifest.get("expectedSummary"),
                status="draft",
                property_type=manifest.get("category"),
                repair_scope=manifest.get("expectedScope"),
                address_label=manifest.get("title"),
                reference_expectations_json=reference_expectations_json,
            )
            session.add(project)
            await session.flush()

            for index, photo_manifest in enumerate(manifest["photos"], start=1):
                photo_filename = sanitize_filename(photo_manifest["file"])
                photo_bytes = (case_dir / photo_manifest["file"]).read_bytes()
                original_key = build_storage_key(project_id, "original", photo_filename)
                preview_key = build_storage_key(project_id, "preview", photo_filename)
                ai_key = build_storage_key(project_id, "ai", photo_filename)

                write_storage_file(relative_storage_key=original_key, content=photo_bytes)
                write_storage_file(relative_storage_key=preview_key, content=photo_bytes)
                write_storage_file(relative_storage_key=ai_key, content=photo_bytes)

                photo = ProjectPhoto(
                    id=f"{project_id}_pho_{index}",
                    project_id=project_id,
                    storage_key=original_key,
                    preview_storage_key=preview_key,
                    ai_input_storage_key=ai_key,
                    original_filename=photo_filename,
                    mime_type="image/jpeg",
                    file_size=len(photo_bytes),
                    preview_file_size=len(photo_bytes),
                    ai_input_file_size=len(photo_bytes),
                    processing_status="ready",
                    is_primary=bool(photo_manifest.get("expectedPrimary")),
                    is_analysis_reference=bool(photo_manifest.get("expectedAnalysisReference")),
                    sort_order=index,
                )
                session.add(photo)

            imported_projects += 1
            print(f"import-project {project_id}")

        await session.commit()

        project_count = await session.scalar(
            select(func.count(Project.id)).where(Project.id.like("ref_case_%"))
        )
        print(
            f"import-done imported={imported_projects} skipped={skipped_projects} total_ref_projects={project_count or 0}"
        )


if __name__ == "__main__":
    asyncio.run(import_reference_cases())
