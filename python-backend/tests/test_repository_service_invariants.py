from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

from app.models import Project, ProjectPhoto
from app.repositories.photo_repository import PhotoRepository
from app.repositories.project_repository import ProjectRepository
from app.services.photo_service import PhotoService
from app.services.project_service import ProjectService


async def _seed_project_photo_rows(db_session, test_tenants):
    token = uuid4().hex[:8]
    base = datetime.now(UTC) + timedelta(days=14)

    project_ids = {
        "a": f"prj_inv_{token}_a",
        "b": f"prj_inv_{token}_b",
    }
    photo_ids = {
        "a1": f"pho_inv_{token}_a1",
        "a2": f"pho_inv_{token}_a2",
        "a3": f"pho_inv_{token}_a3",
        "b1": f"pho_inv_{token}_b1",
    }

    db_session.add_all(
        [
            Project(
                id=project_ids["a"],
                organization_id=test_tenants["org_a"],
                created_by_user_id="usr_e2e_a1",
                title=f"Repo invariant A {token}",
                description=f"Repo invariant marker {token}",
                status="draft",
                source="mobile",
                created_at=base,
                updated_at=base,
            ),
            Project(
                id=project_ids["b"],
                organization_id=test_tenants["org_b"],
                created_by_user_id="usr_e2e_b1",
                title=f"Repo invariant B {token}",
                description=f"Repo invariant marker {token}",
                status="draft",
                source="mobile",
                created_at=base + timedelta(minutes=1),
                updated_at=base + timedelta(minutes=1),
            ),
            ProjectPhoto(
                id=photo_ids["a1"],
                project_id=project_ids["a"],
                storage_key=f"projects/{project_ids['a']}/a1.jpg",
                original_filename="a1.jpg",
                mime_type="image/jpeg",
                file_size=101,
                processing_status="ready",
                is_primary=True,
                is_analysis_reference=True,
                sort_order=1,
                created_at=base + timedelta(seconds=1),
            ),
            ProjectPhoto(
                id=photo_ids["a2"],
                project_id=project_ids["a"],
                storage_key=f"projects/{project_ids['a']}/a2.jpg",
                original_filename="a2.jpg",
                mime_type="image/jpeg",
                file_size=102,
                processing_status="ready",
                is_primary=False,
                is_analysis_reference=False,
                sort_order=2,
                created_at=base + timedelta(seconds=2),
            ),
            ProjectPhoto(
                id=photo_ids["a3"],
                project_id=project_ids["a"],
                storage_key=f"projects/{project_ids['a']}/a3.jpg",
                original_filename="a3.jpg",
                mime_type="image/jpeg",
                file_size=103,
                processing_status="ready",
                is_primary=False,
                is_analysis_reference=False,
                sort_order=3,
                created_at=base + timedelta(seconds=3),
            ),
            ProjectPhoto(
                id=photo_ids["b1"],
                project_id=project_ids["b"],
                storage_key=f"projects/{project_ids['b']}/b1.jpg",
                original_filename="b1.jpg",
                mime_type="image/jpeg",
                file_size=201,
                processing_status="ready",
                is_primary=True,
                is_analysis_reference=True,
                sort_order=1,
                created_at=base + timedelta(seconds=4),
            ),
        ]
    )
    await db_session.commit()

    return {
        "projects": project_ids,
        "photos": photo_ids,
    }


async def _seed_project_list_rows(db_session, test_tenants):
    token = uuid4().hex[:8]
    base = datetime.now(UTC) + timedelta(days=21)

    project_ids = {
        "newest": f"prj_svc_{token}_003",
        "tie_high": f"prj_svc_{token}_002",
        "tie_low": f"prj_svc_{token}_001",
        "other_org": f"prj_svc_{token}_900",
    }

    db_session.add_all(
        [
            Project(
                id=project_ids["newest"],
                organization_id=test_tenants["org_a"],
                created_by_user_id="usr_e2e_a1",
                title=f"Service invariant {token} newest",
                description=f"Service invariant marker {token}",
                status="draft",
                source="mobile",
                created_at=base + timedelta(minutes=3),
                updated_at=base + timedelta(minutes=3),
            ),
            Project(
                id=project_ids["tie_high"],
                organization_id=test_tenants["org_a"],
                created_by_user_id="usr_e2e_a1",
                title=f"Service invariant {token} tie high",
                description=f"Service invariant marker {token}",
                status="draft",
                source="mobile",
                created_at=base + timedelta(minutes=2),
                updated_at=base + timedelta(minutes=2),
            ),
            Project(
                id=project_ids["tie_low"],
                organization_id=test_tenants["org_a"],
                created_by_user_id="usr_e2e_a1",
                title=f"Service invariant {token} tie low",
                description=f"Service invariant marker {token}",
                status="draft",
                source="mobile",
                created_at=base + timedelta(minutes=2),
                updated_at=base + timedelta(minutes=2),
            ),
            Project(
                id=project_ids["other_org"],
                organization_id=test_tenants["org_b"],
                created_by_user_id="usr_e2e_b1",
                title=f"Service invariant {token} foreign",
                description=f"Service invariant marker {token}",
                status="draft",
                source="mobile",
                created_at=base + timedelta(minutes=4),
                updated_at=base + timedelta(minutes=4),
            ),
        ]
    )
    await db_session.commit()

    return {
        "token": token,
        "projects": project_ids,
    }


async def test_photo_repository_list_and_count_are_consistent_for_the_same_project(
    db_session,
    test_tenants,
):
    seeded = await _seed_project_photo_rows(db_session, test_tenants)
    repo = PhotoRepository(db_session)

    photos = list(await repo.list_photos_by_project_id(seeded["projects"]["a"]))
    count = await repo.count_photos(seeded["projects"]["a"])

    assert [photo.id for photo in photos] == [
        seeded["photos"]["a1"],
        seeded["photos"]["a2"],
        seeded["photos"]["a3"],
    ]
    assert count == len(photos) == 3
    assert all(photo.project_id == seeded["projects"]["a"] for photo in photos)


async def test_photo_repository_project_scoping_and_next_sort_order_stay_consistent(
    db_session,
    test_tenants,
):
    seeded = await _seed_project_photo_rows(db_session, test_tenants)
    repo = PhotoRepository(db_session)

    same_project = await repo.get_photo(seeded["projects"]["a"], seeded["photos"]["a2"])
    wrong_project = await repo.get_photo(seeded["projects"]["b"], seeded["photos"]["a2"])

    assert same_project is not None
    assert same_project.project_id == seeded["projects"]["a"]
    assert wrong_project is None
    assert await repo.get_next_sort_order(seeded["projects"]["a"]) == 4
    assert await repo.get_next_sort_order(seeded["projects"]["b"]) == 2


async def test_photo_service_move_photo_reindexes_without_gaps_or_duplicates(
    db_session,
    test_tenants,
):
    seeded = await _seed_project_photo_rows(db_session, test_tenants)
    repo = PhotoRepository(db_session)
    service = PhotoService(repo)

    items, _meta = await service.move_photo(seeded["projects"]["a"], seeded["photos"]["a1"], "down")

    assert [item.id for item in items] == [
        seeded["photos"]["a2"],
        seeded["photos"]["a1"],
        seeded["photos"]["a3"],
    ]
    assert [item.sortOrder for item in items] == [1, 2, 3]

    reloaded = list(await repo.list_photos_by_project_id(seeded["projects"]["a"]))
    assert [(photo.id, photo.sort_order) for photo in reloaded] == [
        (seeded["photos"]["a2"], 1),
        (seeded["photos"]["a1"], 2),
        (seeded["photos"]["a3"], 3),
    ]


async def test_project_repository_get_project_respects_org_scope_for_detail_reads(
    db_session,
    test_tenants,
):
    seeded = await _seed_project_photo_rows(db_session, test_tenants)
    repo = ProjectRepository(db_session)

    visible = await repo.get_project(seeded["projects"]["a"], organization_id=test_tenants["org_a"])
    hidden = await repo.get_project(seeded["projects"]["a"], organization_id=test_tenants["org_b"])

    assert visible is not None
    assert visible.organization_id == test_tenants["org_a"]
    assert hidden is None


async def test_project_service_list_projects_is_tenant_scoped_and_cursor_stable(
    db_session,
    test_tenants,
):
    seeded = await _seed_project_list_rows(db_session, test_tenants)
    service = ProjectService(
        repository=ProjectRepository(db_session),
        proposal_draft_repository=MagicMock(),
        final_proposal_repository=MagicMock(),
        export_service=MagicMock(),
    )

    first_page, next_cursor = await service.list_projects(
        organization_id=test_tenants["org_a"],
        search=seeded["token"],
        limit=2,
    )

    assert [item.id for item in first_page] == [
        seeded["projects"]["newest"],
        seeded["projects"]["tie_high"],
    ]
    assert next_cursor

    second_page, second_cursor = await service.list_projects(
        organization_id=test_tenants["org_a"],
        search=seeded["token"],
        limit=2,
        cursor=next_cursor,
    )

    assert [item.id for item in second_page] == [seeded["projects"]["tie_low"]]
    assert seeded["projects"]["other_org"] not in {
        *(item.id for item in first_page),
        *(item.id for item in second_page),
    }
    assert set(item.id for item in first_page).isdisjoint(item.id for item in second_page)
    assert second_cursor is None


# ─────────────────────────────────────────────────────────────────────────────
# ProjectRepository.get_project_lean — org-scope + no selectinload
# ─────────────────────────────────────────────────────────────────────────────

async def test_get_project_lean_returns_project_for_correct_org(db_session, test_tenants):
    """get_project_lean returns the Project row when org matches."""
    seeded = await _seed_project_photo_rows(db_session, test_tenants)
    repo = ProjectRepository(db_session)

    result = await repo.get_project_lean(seeded["projects"]["a"], organization_id=test_tenants["org_a"])

    assert result is not None
    assert result.id == seeded["projects"]["a"]
    assert result.organization_id == test_tenants["org_a"]


async def test_get_project_lean_returns_none_for_wrong_org(db_session, test_tenants):
    """get_project_lean enforces org isolation identically to get_project."""
    seeded = await _seed_project_photo_rows(db_session, test_tenants)
    repo = ProjectRepository(db_session)

    result = await repo.get_project_lean(seeded["projects"]["a"], organization_id=test_tenants["org_b"])

    assert result is None


async def test_get_project_lean_returns_none_for_missing_project(db_session, test_tenants):
    """get_project_lean returns None when the project_id does not exist."""
    repo = ProjectRepository(db_session)

    result = await repo.get_project_lean("prj_does_not_exist", organization_id=test_tenants["org_a"])

    assert result is None


async def test_get_project_lean_org_none_bypasses_org_filter(db_session, test_tenants):
    """get_project_lean with organization_id=None skips the org filter (superadmin path)."""
    seeded = await _seed_project_photo_rows(db_session, test_tenants)
    repo = ProjectRepository(db_session)

    result = await repo.get_project_lean(seeded["projects"]["a"], organization_id=None)

    assert result is not None
    assert result.id == seeded["projects"]["a"]


async def test_get_project_lean_does_not_load_relations(db_session, test_tenants):
    """get_project_lean must not eagerly load any relationship (no selectinload overhead)."""
    from sqlalchemy import inspect as sa_inspect
    seeded = await _seed_project_photo_rows(db_session, test_tenants)
    repo = ProjectRepository(db_session)

    result = await repo.get_project_lean(seeded["projects"]["a"], organization_id=test_tenants["org_a"])

    assert result is not None
    state = sa_inspect(result)
    # Relationships that get_project() loads eagerly must NOT be present in
    # the instance dict after a lean fetch.  SQLAlchemy marks unloaded
    # relationships as expired/deferred; they are absent from the loaded attrs.
    loaded_attrs = {key for key, _ in state.attrs.items() if not state.attrs[key].history.unchanged == ()}
    for rel in ("photos", "client", "proposal_draft", "final_proposals",
                "analysis_results", "quote_variants"):
        assert rel not in loaded_attrs, f"get_project_lean must not eagerly load '{rel}'"
