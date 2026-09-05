import os
import pathlib
import shutil
import tempfile
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_TESTS_ROOT = pathlib.Path(__file__).resolve().parent
_TEST_RUNTIME_ROOT = _TESTS_ROOT.parent / ".tmp_test_runtime"
_TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
_TEST_SESSION_ROOT = _TEST_RUNTIME_ROOT / f"session_{uuid.uuid4().hex[:8]}"
_TEST_SESSION_ROOT.mkdir(parents=True, exist_ok=True)
_PYTEST_TEMP_ROOT = _TEST_SESSION_ROOT / "tmp"
_PYTEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
_TMP_STORAGE = _TEST_SESSION_ROOT / "storage"
_TMP_STORAGE.mkdir(parents=True, exist_ok=True)

_TMP_DB_DIR = _TEST_SESSION_ROOT / "db"
_TMP_DB_DIR.mkdir(parents=True, exist_ok=True)
_TEST_DB_PATH = _TMP_DB_DIR / "test_e2e_tenant.db"
_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{_TEST_DB_PATH}"
_USING_LOCAL_SQLITE = "TEST_DATABASE_URL" not in os.environ

os.environ["TMP"] = str(_PYTEST_TEMP_ROOT)
os.environ["TEMP"] = str(_PYTEST_TEMP_ROOT)
os.environ["TMPDIR"] = str(_PYTEST_TEMP_ROOT)
tempfile.tempdir = str(_PYTEST_TEMP_ROOT)

if _USING_LOCAL_SQLITE and _TEST_DB_PATH.exists():
    _TEST_DB_PATH.unlink(missing_ok=True)

os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ["DB_SEED_ON_STARTUP"] = "false"
os.environ["APP_ENV"] = "development"
os.environ["DB_AUTO_CREATE_SCHEMA"] = "true"
os.environ["JWT_SECRET"] = "test-e2e-jwt-secret-x99-32bytes-min"
os.environ["STORAGE_ROOT"] = str(_TMP_STORAGE)
os.environ["APP_DEBUG"] = "false"
os.environ["RATE_LIMIT_LOGIN"] = "1000/minute"
os.environ["RATE_LIMIT_ADMIN"] = "1000/minute"
os.environ["METRICS_AUTH_ENABLED"] = "false"
os.environ["WORKER_HEAVY_CONCURRENCY"] = "1"

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db.base import Base  # noqa: E402
from app.models import MaterialCatalog, Organization, PricingProfile, Supplier, User  # noqa: E402
from app.services.auth_service import hash_password  # noqa: E402


# Mirror the application engine's profile. Both engines talk to the same test
# database, so they must agree on pooling and (for PostgreSQL) search_path —
# otherwise fixture DB writes and HTTP-driven writes land in different places.
_test_engine = create_async_engine(
    _TEST_DB_URL, echo=False, **get_settings().database_engine_kwargs
)
_TestSession = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


async def _install_sqlite_outbox_seq_emulation(conn) -> None:
    """Emulate PostgreSQL's DB-managed outbox seq in SQLite test databases."""
    if _test_engine.sync_engine.dialect.name != "sqlite":
        return

    await conn.execute(text("DROP TABLE IF EXISTS outbox_events"))
    await conn.execute(
        text(
            """
            CREATE TABLE outbox_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                id VARCHAR(64) NOT NULL UNIQUE,
                event_type VARCHAR(128) NOT NULL,
                aggregate_type VARCHAR(64) NOT NULL,
                aggregate_id VARCHAR(64) NOT NULL,
                organization_id VARCHAR(64) NOT NULL,
                payload JSON NOT NULL,
                published BOOLEAN NOT NULL DEFAULT 0,
                published_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
            """
        )
    )
    await conn.execute(
        text(
            "CREATE INDEX idx_outbox_events_unpublished "
            "ON outbox_events (published, created_at)"
        )
    )
    await conn.execute(
        text(
            "CREATE INDEX idx_outbox_events_aggregate "
            "ON outbox_events (aggregate_type, aggregate_id)"
        )
    )


class _InMemoryAuthRedisPipeline:
    def __init__(self, redis: "_InMemoryAuthRedis") -> None:
        self._redis = redis
        self._operations: list[tuple[str, str, int | None]] = []

    def incr(self, key: str):
        self._operations.append(("incr", key, None))
        return self

    def expire(self, key: str, ttl_seconds: int):
        self._operations.append(("expire", key, ttl_seconds))
        return self

    async def execute(self):
        results: list[int | bool] = []
        for operation, key, ttl_seconds in self._operations:
            if operation == "incr":
                results.append(await self._redis.incr(key))
            elif operation == "expire" and ttl_seconds is not None:
                results.append(await self._redis.expire(key, ttl_seconds))
        self._operations.clear()
        return results


class _InMemoryAuthRedis:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._expires_at: dict[str, datetime] = {}

    def _purge_if_expired(self, key: str) -> None:
        expires_at = self._expires_at.get(key)
        if expires_at is None:
            return
        if expires_at <= datetime.now(UTC):
            self._expires_at.pop(key, None)
            self._values.pop(key, None)

    async def get(self, key: str):
        self._purge_if_expired(key)
        return self._values.get(key)

    async def set(self, key: str, value, ex: int | None = None) -> bool:
        self._values[key] = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        if ex is not None:
            self._expires_at[key] = datetime.now(UTC) + timedelta(seconds=max(1, int(ex)))
        else:
            self._expires_at.pop(key, None)
        return True

    async def setex(self, key: str, ttl_seconds: int, value) -> bool:
        self._values[key] = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        self._expires_at[key] = datetime.now(UTC) + timedelta(seconds=max(1, int(ttl_seconds)))
        return True

    async def mget(self, keys: list) -> list:
        result = []
        for key in keys:
            k = key.decode("utf-8") if isinstance(key, bytes) else str(key)
            self._purge_if_expired(k)
            v = self._values.get(k)
            result.append(v.encode("utf-8") if v is not None else None)
        return result

    async def scan_iter(self, match: str = "*"):
        import fnmatch
        for key in list(self._values.keys()):
            self._purge_if_expired(key)
            if key in self._values and fnmatch.fnmatch(key, match):
                yield key.encode("utf-8")

    async def llen(self, key: str) -> int:
        return 0

    async def zcard(self, key: str) -> int:
        return 0

    async def zcount(self, key: str, min, max) -> int:
        return 0

    async def scard(self, key: str) -> int:
        return 0

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            self._purge_if_expired(key)
            if key in self._values:
                deleted += 1
            self._values.pop(key, None)
            self._expires_at.pop(key, None)
        return deleted

    async def incr(self, key: str) -> int:
        self._purge_if_expired(key)
        next_value = int(self._values.get(key, "0")) + 1
        self._values[key] = str(next_value)
        return next_value

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        self._purge_if_expired(key)
        if key not in self._values:
            return False
        self._expires_at[key] = datetime.now(UTC) + timedelta(seconds=max(1, int(ttl_seconds)))
        return True

    def pipeline(self) -> _InMemoryAuthRedisPipeline:
        return _InMemoryAuthRedisPipeline(self)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    def clear(self) -> None:
        self._values.clear()
        self._expires_at.clear()


@pytest.fixture
def tmp_path():
    path = _PYTEST_TEMP_ROOT / f"case_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_test_db():
    """Create a clean schema once per test session."""
    async with _test_engine.begin() as conn:
        if not _USING_LOCAL_SQLITE:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await _install_sqlite_outbox_seq_emulation(conn)
    yield
    await _test_engine.dispose()
    shutil.rmtree(_TEST_SESSION_ROOT, ignore_errors=True)


@pytest_asyncio.fixture(scope="session")
async def test_tenants(_setup_test_db):
    """Ensure two isolated orgs + users + catalog rows exist for smoke/auth tests."""
    seed_rows = [
        Organization(
            id="org_e2e_a",
            name="Tenant A s.r.o.",
            ico="",
            email="a@test.local",
            phone="",
            default_currency="CZK",
        ),
        User(
            id="usr_e2e_a1",
            organization_id="org_e2e_a",
            email="manager_a@test.local",
            password_hash=hash_password("TestPassA1!"),
            full_name="Manager A",
            role="manager",
            is_active=True,
            is_superadmin=False,
        ),
        PricingProfile(
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
        ),
        Supplier(
            id="sup_e2e_a1",
            organization_id="org_e2e_a",
            name="Dodavatel Alpha",
            integration_type="manual",
            is_active=True,
        ),
        MaterialCatalog(
            id="mat_e2e_a1",
            organization_id="org_e2e_a",
            name="Tasovany asfalt A",
            unit="m2",
            norm_per_sqm=1.0,
            default_unit_price=120.0,
            is_active=True,
        ),
        Organization(
            id="org_e2e_b",
            name="Tenant B spol.",
            ico="",
            email="b@test.local",
            phone="",
            default_currency="CZK",
        ),
        User(
            id="usr_e2e_b1",
            organization_id="org_e2e_b",
            email="manager_b@test.local",
            password_hash=hash_password("TestPassB1!"),
            full_name="Manager B",
            role="manager",
            is_active=True,
            is_superadmin=False,
        ),
        PricingProfile(
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
        ),
        Supplier(
            id="sup_e2e_b1",
            organization_id="org_e2e_b",
            name="Dodavatel Beta",
            integration_type="manual",
            is_active=True,
        ),
        MaterialCatalog(
            id="mat_e2e_b1",
            organization_id="org_e2e_b",
            name="Tasovany asfalt B",
            unit="m2",
            norm_per_sqm=1.0,
            default_unit_price=130.0,
            is_active=True,
        ),
    ]

    async with _TestSession() as session:
        for row in seed_rows:
            if await session.get(type(row), row.id) is None:
                session.add(row)
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
    """Function-scoped async DB session for direct DB assertions."""
    async with _TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def reset_test_user(test_tenants):
    """Throwaway user for password-reset tests."""
    import uuid

    uid = f"usr_reset_{uuid.uuid4().hex[:8]}"
    email = f"reset_{uid}@test.local"
    async with _TestSession() as session:
        session.add(
            User(
                id=uid,
                organization_id="org_e2e_a",
                email=email,
                password_hash=hash_password("OldResetP@ss1!"),
                full_name="Reset Test User",
                role="manager",
                is_active=True,
                is_superadmin=False,
            )
        )
        await session.commit()
    yield {"email": email, "user_id": uid}
    async with _TestSession() as session:
        user = await session.get(User, uid)
        if user:
            await session.delete(user)
            await session.commit()


@pytest_asyncio.fixture(scope="session")
async def app_client(test_tenants):
    """Real FastAPI ASGI client against the test database."""
    from app.main import app as fastapi_app  # noqa: PLC0415

    async with fastapi_app.router.lifespan_context(fastapi_app):
        auth_token_store = _InMemoryAuthRedis()
        original_auth_token_store = getattr(fastapi_app.state, "auth_token_store", None)
        fastapi_app.state.auth_token_store = auth_token_store
        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
        fastapi_app.state.auth_token_store = original_auth_token_store


@pytest.fixture(autouse=True)
def _clear_auth_token_store_between_tests():
    from app.main import app as fastapi_app  # noqa: PLC0415

    store = getattr(getattr(fastapi_app, "state", None), "auth_token_store", None)
    if hasattr(store, "clear"):
        store.clear()
    yield
    store = getattr(getattr(fastapi_app, "state", None), "auth_token_store", None)
    if hasattr(store, "clear"):
        store.clear()


@pytest_asyncio.fixture(scope="session")
async def token_a(app_client, test_tenants):
    resp = await app_client.post("/api/v1/auth/login", json=test_tenants["user_a"])
    assert resp.status_code == 200, f"Login A failed: {resp.text}"
    return resp.json()["accessToken"]


@pytest_asyncio.fixture(scope="session")
async def token_b(app_client, test_tenants):
    resp = await app_client.post("/api/v1/auth/login", json=test_tenants["user_b"])
    assert resp.status_code == 200, f"Login B failed: {resp.text}"
    return resp.json()["accessToken"]


@pytest_asyncio.fixture(scope="session")
async def case_a_id(app_client, token_a):
    resp = await app_client.post(
        "/api/v1/cases",
        json={"title": "E2E Isolation Test Case - Tenant A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 201, f"Create case A failed: {resp.text}"
    return resp.json()["id"]


@pytest_asyncio.fixture(scope="session")
async def case_b_id(app_client, token_b):
    resp = await app_client.post(
        "/api/v1/cases",
        json={"title": "E2E Isolation Test Case - Tenant B"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 201, f"Create case B failed: {resp.text}"
    return resp.json()["id"]


@pytest_asyncio.fixture(scope="session")
async def job_a_id(app_client, token_a, case_a_id):
    resp = await app_client.post(
        f"/api/v1/cases/{case_a_id}/analysis-jobs",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 202, f"Create job A failed: {resp.text}"
    return resp.json()["jobId"]
