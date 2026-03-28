# =============================================================================
# E2E test infrastructure — tenant isolation
#
# IMPORTANT: env var setup MUST happen before any app.* imports.
# conftest.py is loaded by pytest before any test module, so this is safe.
# =============================================================================
import os
import pathlib
import tempfile

# ── Test environment — overrides .env before any app module is imported ───────
_TMP_STORAGE = pathlib.Path(tempfile.gettempdir()) / "novu_e2e_test_storage"
_TMP_STORAGE.mkdir(parents=True, exist_ok=True)

_TEST_DB_PATH = pathlib.Path(__file__).parent / "test_e2e_tenant.db"
# R-27: allow CI to inject a PostgreSQL URL via TEST_DATABASE_URL; fall back to SQLite locally
_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{_TEST_DB_PATH}"

os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ["DB_SEED_ON_STARTUP"] = "false"
os.environ["APP_ENV"] = "development"          # enables DB_AUTO_CREATE_SCHEMA
os.environ["DB_AUTO_CREATE_SCHEMA"] = "true"
os.environ["JWT_SECRET"] = "test-e2e-jwt-secret-x99-32bytes-min"
os.environ["STORAGE_ROOT"] = str(_TMP_STORAGE)
os.environ["APP_DEBUG"] = "false"
os.environ["RATE_LIMIT_LOGIN"] = "1000/minute"
os.environ["RATE_LIMIT_ADMIN"] = "1000/minute"
os.environ["METRICS_AUTH_ENABLED"] = "false"

# Clear the lru_cache so Settings re-reads from the updated env vars.
# app.db.session reads settings at module level — cache must be clear
# BEFORE that module is imported anywhere in the test session.
from app.core.config import get_settings  # noqa: E402
get_settings.cache_clear()

# ── Remaining imports (after env setup) ───────────────────────────────────────
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base
from app.models import (  # noqa: E402
    MaterialCatalog,
    Organization,
    PricingProfile,
    Supplier,
    User,
)
from app.services.auth_service import hash_password


# ── Test-specific SQLAlchemy engine (same file as app engine) ─────────────────
# Both use _TEST_DB_URL, so they share the same SQLite file.
_test_engine = create_async_engine(_TEST_DB_URL, echo=False)
_TestSession = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


# ── Session-scoped DB setup ───────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_test_db():
    """Drop and recreate all tables once per test session → clean slate."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await _test_engine.dispose()
    # Leave the file on disk so failures can be inspected; CI should clean tmp.


@pytest_asyncio.fixture(scope="session")
async def test_tenants(_setup_test_db):
    """Insert two fully isolated orgs + users + catalog data into the test DB."""
    async with _TestSession() as session:
        # ── Org A ──
        session.add(Organization(
            id="org_e2e_a", name="Tenant A s.r.o.", ico="",
            email="a@test.local", phone="", default_currency="CZK",
        ))
        session.add(User(
            id="usr_e2e_a1",
            organization_id="org_e2e_a",
            email="manager_a@test.local",
            password_hash=hash_password("TestPassA1!"),
            full_name="Manager A",
            role="manager",
            is_active=True,
            is_superadmin=False,
        ))
        session.add(PricingProfile(
            id="pp_e2e_a1",
            organization_id="org_e2e_a",
            name="Cenova sazba A",
            hourly_rate=350.0,
            daily_rate=2800.0,
            labor_hours_per_sqm=0.3,
            margin_economy_pct=10.0,
            margin_standard_pct=18.0,
            margin_premium_pct=28.0,
            vat_pct=21.0,
            currency="CZK",
            is_default=True,
        ))
        session.add(Supplier(
            id="sup_e2e_a1",
            organization_id="org_e2e_a",
            name="Dodavatel Alpha",
            integration_type="manual",
            is_active=True,
        ))
        session.add(MaterialCatalog(
            id="mat_e2e_a1",
            organization_id="org_e2e_a",
            name="Tasovany asfalt A",
            unit="m2",
            norm_per_sqm=1.0,
            default_unit_price=120.0,
            is_active=True,
        ))

        # ── Org B ──
        session.add(Organization(
            id="org_e2e_b", name="Tenant B spol.", ico="",
            email="b@test.local", phone="", default_currency="CZK",
        ))
        session.add(User(
            id="usr_e2e_b1",
            organization_id="org_e2e_b",
            email="manager_b@test.local",
            password_hash=hash_password("TestPassB1!"),
            full_name="Manager B",
            role="manager",
            is_active=True,
            is_superadmin=False,
        ))
        session.add(PricingProfile(
            id="pp_e2e_b1",
            organization_id="org_e2e_b",
            name="Cenova sazba B",
            hourly_rate=400.0,
            daily_rate=3200.0,
            labor_hours_per_sqm=0.35,
            margin_economy_pct=12.0,
            margin_standard_pct=20.0,
            margin_premium_pct=30.0,
            vat_pct=21.0,
            currency="CZK",
            is_default=True,
        ))
        session.add(Supplier(
            id="sup_e2e_b1",
            organization_id="org_e2e_b",
            name="Dodavatel Beta",
            integration_type="manual",
            is_active=True,
        ))
        session.add(MaterialCatalog(
            id="mat_e2e_b1",
            organization_id="org_e2e_b",
            name="Tasovany asfalt B",
            unit="m2",
            norm_per_sqm=1.0,
            default_unit_price=130.0,
            is_active=True,
        ))

        await session.commit()

    return {
        "org_a": "org_e2e_a",
        "org_b": "org_e2e_b",
        "user_a": {"email": "manager_a@test.local", "password": "TestPassA1!"},
        "user_b": {"email": "manager_b@test.local", "password": "TestPassB1!"},
        "pricebook_a": "pp_e2e_a1",
        "pricebook_b": "pp_e2e_b1",
        "supplier_a": "sup_e2e_a1",
        "supplier_b": "sup_e2e_b1",
        "material_a": "mat_e2e_a1",
        "material_b": "mat_e2e_b1",
    }


@pytest_asyncio.fixture
async def db_session(_setup_test_db):
    """Function-scoped async DB session for tests that need direct DB access.

    Uses the same underlying SQLite file as the app, so HTTP-driven writes
    are visible immediately after commit.
    """
    async with _TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def reset_test_user(_setup_test_db):
    """Function-scoped throwaway user for C7 password-reset tests.

    Each test that modifies passwords gets its own user so it cannot
    contaminate session-scoped token_a / token_b fixtures.
    Returns a dict with 'email' and 'user_id'.
    """
    import uuid
    uid = f"usr_reset_{uuid.uuid4().hex[:8]}"
    email = f"reset_{uid}@test.local"
    async with _TestSession() as session:
        session.add(User(
            id=uid,
            organization_id="org_e2e_a",
            email=email,
            password_hash=hash_password("OldResetP@ss1!"),
            full_name="Reset Test User",
            role="manager",
            is_active=True,
            is_superadmin=False,
        ))
        await session.commit()
    yield {"email": email, "user_id": uid}
    # Cleanup: remove the throwaway user (and cascade-delete any reset tokens)
    async with _TestSession() as session:
        user = await session.get(User, uid)
        if user:
            await session.delete(user)
            await session.commit()


@pytest_asyncio.fixture(scope="session")
async def app_client(test_tenants):
    """Real FastAPI ASGI client against the test SQLite database.

    The lifespan runs once: schema is created (no-op, already done by
    _setup_test_db), seeding is disabled, storage dirs are verified.
    """
    from app.main import app as fastapi_app  # noqa: PLC0415 — must be after env setup

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def token_a(app_client, test_tenants):
    """Access token for Tenant A manager (session-scoped, reused across tests)."""
    resp = await app_client.post("/api/v1/auth/login", json=test_tenants["user_a"])
    assert resp.status_code == 200, f"Login A failed: {resp.text}"
    return resp.json()["accessToken"]


@pytest_asyncio.fixture(scope="session")
async def token_b(app_client, test_tenants):
    """Access token for Tenant B manager."""
    resp = await app_client.post("/api/v1/auth/login", json=test_tenants["user_b"])
    assert resp.status_code == 200, f"Login B failed: {resp.text}"
    return resp.json()["accessToken"]


@pytest_asyncio.fixture(scope="session")
async def case_a_id(app_client, token_a):
    """A project created by Tenant A — used across all isolation tests."""
    resp = await app_client.post(
        "/api/v1/cases",
        json={"title": "E2E Isolation Test Case — Tenant A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 201, f"Create case A failed: {resp.text}"
    return resp.json()["id"]


@pytest_asyncio.fixture(scope="session")
async def case_b_id(app_client, token_b):
    """A project created by Tenant B — for positive-path verification."""
    resp = await app_client.post(
        "/api/v1/cases",
        json={"title": "E2E Isolation Test Case — Tenant B"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 201, f"Create case B failed: {resp.text}"
    return resp.json()["id"]


@pytest_asyncio.fixture(scope="session")
async def job_a_id(app_client, token_a, case_a_id):
    """An analysis job created by Tenant A for their own case.

    The mock provider requires at least one photo; the job will be created
    (202) but the background task will fail silently (no photos).  That's
    acceptable — we only need the job ID to test cross-tenant access.
    """
    resp = await app_client.post(
        f"/api/v1/cases/{case_a_id}/analysis-jobs",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 202, f"Create job A failed: {resp.text}"
    return resp.json()["jobId"]
