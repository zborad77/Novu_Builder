import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A minimal PostgreSQL URL that satisfies all schema/hostname validators.
_PG_URL = "postgresql+asyncpg://novu:test-pass@localhost:5432/novu_dev"
_SQLITE_MEM_URL = "sqlite+aiosqlite:///:memory:"


def _pool_settings(**overrides) -> Settings:
    """Settings with the test-only engine profile explicitly switched off.

    These tests assert the *production* pool contract, but they run inside a
    pytest process that sets APP_ENV=development and — when the suite is pointed
    at PostgreSQL — DB_TEST_DISABLE_POOLING / DB_TEST_SEARCH_PATH. Without
    pinning them here the assertions would silently describe whatever profile
    the process happened to be started with.

    APP_ENV is deliberately NOT pinned to "production": the strict profile
    requires DB_POOL_SIZE and friends to be set explicitly, which would defeat
    the very defaults these tests exist to verify. Pinning the two test-profile
    inputs is what actually removes the dependency on the process environment.
    """
    return Settings(
        DATABASE_URL=_PG_URL,
        DB_TEST_DISABLE_POOLING=False,
        DB_TEST_SEARCH_PATH="",
        **overrides,
    )


# ===========================================================================
# Existing tests — API pool defaults and individual-parameter validation
# ===========================================================================


def test_db_pool_defaults_are_conservative_and_explicit():
    settings = _pool_settings()

    assert settings.db_pool_size == 10
    assert settings.db_max_overflow == 10
    assert settings.db_pool_timeout == 30
    assert settings.db_pool_recycle == 1800
    assert settings.worker_concurrency == 1
    assert settings.database_engine_kwargs == {
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 1800,
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"DB_POOL_SIZE": 0}, "DB_POOL_SIZE must be > 0"),
        ({"DB_MAX_OVERFLOW": -1}, "DB_MAX_OVERFLOW must be >= 0"),
        ({"DB_POOL_TIMEOUT": 0}, "DB_POOL_TIMEOUT must be > 0"),
        ({"DB_POOL_RECYCLE": 0}, "DB_POOL_RECYCLE must be -1 or > 0"),
        ({"WORKER_CONCURRENCY": 0}, "WORKER_CONCURRENCY must be > 0"),
    ],
)
def test_db_pool_settings_reject_invalid_values(overrides, message):
    with pytest.raises(ValidationError, match=message):
        Settings(**overrides)


def test_db_pool_settings_create_tuned_queue_pool_for_backend_urls():
    settings = _pool_settings(
        DB_POOL_SIZE=7,
        DB_MAX_OVERFLOW=9,
        DB_POOL_TIMEOUT=11,
        DB_POOL_RECYCLE=13,
    )

    engine = create_async_engine(
        settings.database_url,
        echo=settings.app_debug,
        future=True,
        **settings.database_engine_kwargs,
    )
    try:
        pool = engine.sync_engine.pool
        assert pool.size() == 7
        assert pool.timeout() == 11
        assert pool._max_overflow == 9
        assert pool._recycle == 13
    finally:
        engine.sync_engine.dispose()


def test_db_pool_settings_keep_sqlite_memory_compatible():
    settings = Settings(DATABASE_URL=_SQLITE_MEM_URL)

    assert settings.database_engine_kwargs == {"pool_pre_ping": True}

    engine = create_async_engine(
        settings.database_url,
        echo=settings.app_debug,
        future=True,
        **settings.database_engine_kwargs,
    )
    try:
        assert type(engine.sync_engine.pool).__name__ == "StaticPool"
    finally:
        engine.sync_engine.dispose()


# ===========================================================================
# Worker pool — separate engine, isolated from API pool
# ===========================================================================
# Model:
#   API engine:    pool_size=DB_POOL_SIZE, max_overflow=DB_MAX_OVERFLOW
#   Worker engine: pool_size=effective_worker_db_pool_size, max_overflow=0
#
#   effective_worker_db_pool_size:
#     = WORKER_DB_POOL_SIZE   if WORKER_DB_POOL_SIZE > 0
#     = WORKER_CONCURRENCY    if WORKER_DB_POOL_SIZE == 0 (default auto-derive)


class TestWorkerPoolDefaults:
    """Worker pool defaults and auto-derive behaviour."""

    def test_worker_db_pool_size_defaults_to_zero(self):
        s = _pool_settings()
        assert s.worker_db_pool_size == 0

    def test_effective_pool_size_auto_derives_from_worker_concurrency(self):
        s = _pool_settings(WORKER_CONCURRENCY=3)
        assert s.effective_worker_db_pool_size == 3

    def test_effective_pool_size_uses_explicit_when_set(self):
        s = _pool_settings(WORKER_CONCURRENCY=2, WORKER_DB_POOL_SIZE=5)
        assert s.effective_worker_db_pool_size == 5

    def test_worker_engine_kwargs_include_max_overflow_zero(self):
        s = _pool_settings(WORKER_CONCURRENCY=4)
        kwargs = s.worker_database_engine_kwargs
        assert kwargs["max_overflow"] == 0
        assert kwargs["pool_size"] == 4  # auto-derived

    def test_worker_engine_kwargs_explicit_pool_size(self):
        s = _pool_settings(WORKER_CONCURRENCY=2, WORKER_DB_POOL_SIZE=6)
        kwargs = s.worker_database_engine_kwargs
        assert kwargs["pool_size"] == 6
        assert kwargs["max_overflow"] == 0

    def test_worker_engine_kwargs_sqlite_memory_returns_minimal(self):
        s = Settings(DATABASE_URL=_SQLITE_MEM_URL, WORKER_CONCURRENCY=3)
        assert s.worker_database_engine_kwargs == {"pool_pre_ping": True}

    def test_worker_db_pool_capacity_property_matches_effective(self):
        s = _pool_settings(WORKER_CONCURRENCY=5)
        assert s.worker_db_pool_capacity == 5
        assert s.worker_db_safe_concurrency_limit == 5

    def test_worker_db_safe_concurrency_limit_equals_effective_pool_size(self):
        s = _pool_settings(WORKER_CONCURRENCY=2, WORKER_DB_POOL_SIZE=8)
        assert s.worker_db_safe_concurrency_limit == 8

    def test_api_and_worker_pools_are_independent(self):
        """API pool params do not constrain worker pool and vice-versa."""
        s = Settings(
            DATABASE_URL=_PG_URL,
            DB_POOL_SIZE=3,
            DB_MAX_OVERFLOW=2,
            WORKER_CONCURRENCY=10,  # exceeds API pool capacity — fine with separate pools
            WORKER_DB_POOL_SIZE=10,
        )
        assert s.db_pool_size == 3
        assert s.effective_worker_db_pool_size == 10

    def test_worker_engine_creates_pool_with_correct_size(self):
        """The SQLAlchemy worker engine actually respects the configured pool size."""
        s = _pool_settings(WORKER_CONCURRENCY=3, WORKER_DB_POOL_SIZE=3)
        engine = create_async_engine(
            s.database_url,
            echo=s.app_debug,
            future=True,
            **s.worker_database_engine_kwargs,
        )
        try:
            pool = engine.sync_engine.pool
            assert pool.size() == 3
            assert pool._max_overflow == 0
        finally:
            engine.sync_engine.dispose()


class TestWorkerPoolParamValidation:
    """Validation of worker-specific pool parameters."""

    def test_negative_worker_db_pool_size_rejected(self):
        with pytest.raises(ValidationError, match="WORKER_DB_POOL_SIZE must be >= 0"):
            _pool_settings(WORKER_DB_POOL_SIZE=-1)

    def test_zero_worker_db_pool_timeout_rejected(self):
        with pytest.raises(ValidationError, match="WORKER_DB_POOL_TIMEOUT must be > 0"):
            _pool_settings(WORKER_DB_POOL_TIMEOUT=0)

    def test_zero_worker_instance_count_rejected(self):
        with pytest.raises(ValidationError, match="WORKER_INSTANCE_COUNT must be >= 1"):
            _pool_settings(WORKER_INSTANCE_COUNT=0)

    def test_negative_worker_instance_count_rejected(self):
        with pytest.raises(ValidationError, match="WORKER_INSTANCE_COUNT must be >= 1"):
            _pool_settings(WORKER_INSTANCE_COUNT=-1)

    def test_valid_explicit_worker_db_pool_size_accepted(self):
        s = _pool_settings(WORKER_CONCURRENCY=3, WORKER_DB_POOL_SIZE=5)
        assert s.worker_db_pool_size == 5
        assert s.effective_worker_db_pool_size == 5

    def test_valid_multi_instance_count_accepted(self):
        s = _pool_settings(WORKER_INSTANCE_COUNT=5)
        assert s.worker_instance_count == 5


class TestWorkerDbCapacityGuard:
    """Guard: WORKER_CONCURRENCY must not exceed effective worker pool size.

    With auto-derive (WORKER_DB_POOL_SIZE=0), effective == WORKER_CONCURRENCY,
    so the guard only fires when an explicit WORKER_DB_POOL_SIZE is set too low.
    """

    # ------------------------------------------------------------------
    # Safe — auto-derive always passes
    # ------------------------------------------------------------------

    def test_default_config_passes(self):
        """Default WORKER_CONCURRENCY=1, WORKER_DB_POOL_SIZE=0 auto-derives → always safe."""
        s = _pool_settings()
        assert s.worker_concurrency == 1
        assert s.effective_worker_db_pool_size == 1

    def test_auto_derive_any_concurrency_passes(self):
        """Auto-derive (WORKER_DB_POOL_SIZE=0) always passes regardless of WORKER_CONCURRENCY."""
        s = _pool_settings(WORKER_CONCURRENCY=20)
        assert s.effective_worker_db_pool_size == 20

    def test_explicit_pool_size_equal_to_concurrency_passes(self):
        s = _pool_settings(WORKER_CONCURRENCY=5, WORKER_DB_POOL_SIZE=5)
        assert s.effective_worker_db_pool_size == 5

    def test_explicit_pool_size_larger_than_concurrency_passes(self):
        """WORKER_DB_POOL_SIZE > WORKER_CONCURRENCY is valid (provides buffer)."""
        s = _pool_settings(WORKER_CONCURRENCY=4, WORKER_DB_POOL_SIZE=8)
        assert s.effective_worker_db_pool_size == 8

    # ------------------------------------------------------------------
    # Danger — explicit pool size too small
    # ------------------------------------------------------------------

    def test_explicit_pool_size_smaller_than_concurrency_fails(self):
        """Explicit WORKER_DB_POOL_SIZE < WORKER_CONCURRENCY must fail at startup."""
        with pytest.raises(ValidationError, match="WORKER_DB_POOL_SIZE"):
            _pool_settings(WORKER_CONCURRENCY=5, WORKER_DB_POOL_SIZE=4)

    def test_pool_size_one_concurrency_two_fails(self):
        with pytest.raises(ValidationError, match="WORKER_DB_POOL_SIZE"):
            _pool_settings(WORKER_CONCURRENCY=2, WORKER_DB_POOL_SIZE=1)

    # ------------------------------------------------------------------
    # Error message quality
    # ------------------------------------------------------------------

    def test_error_message_contains_explicit_pool_size(self):
        with pytest.raises(ValidationError) as exc_info:
            _pool_settings(WORKER_CONCURRENCY=5, WORKER_DB_POOL_SIZE=3)
        assert "WORKER_DB_POOL_SIZE=3" in str(exc_info.value)

    def test_error_message_contains_concurrency(self):
        with pytest.raises(ValidationError) as exc_info:
            _pool_settings(WORKER_CONCURRENCY=5, WORKER_DB_POOL_SIZE=3)
        assert "WORKER_CONCURRENCY=5" in str(exc_info.value)

    def test_error_message_mentions_fix(self):
        """Error must tell the operator how to fix the configuration."""
        with pytest.raises(ValidationError) as exc_info:
            _pool_settings(WORKER_CONCURRENCY=5, WORKER_DB_POOL_SIZE=3)
        msg = str(exc_info.value)
        assert "Fix" in msg or "fix" in msg or ">= 5" in msg

    def test_error_message_mentions_max_overflow_zero(self):
        """Error must explain why overflow doesn't help (max_overflow=0)."""
        with pytest.raises(ValidationError) as exc_info:
            _pool_settings(WORKER_CONCURRENCY=3, WORKER_DB_POOL_SIZE=2)
        assert "max_overflow" in str(exc_info.value).lower() or "overflow" in str(exc_info.value).lower()

    # ------------------------------------------------------------------
    # SQLite in-memory — guard bypassed
    # ------------------------------------------------------------------

    def test_sqlite_memory_bypasses_guard_completely(self):
        """SQLite :memory: uses StaticPool; worker pool params don't apply."""
        s = Settings(DATABASE_URL=_SQLITE_MEM_URL, WORKER_CONCURRENCY=50, WORKER_DB_POOL_SIZE=1)
        assert s.worker_concurrency == 50  # no failure

    # ------------------------------------------------------------------
    # Multi-instance (WORKER_INSTANCE_COUNT > 1) — no failure, just info
    # ------------------------------------------------------------------

    def test_multi_instance_does_not_fail(self):
        """WORKER_INSTANCE_COUNT > 1 logs a warning but does NOT fail startup."""
        s = Settings(
            DATABASE_URL=_PG_URL,
            WORKER_CONCURRENCY=4,
            WORKER_INSTANCE_COUNT=3,
        )
        assert s.worker_instance_count == 3
        assert s.worker_concurrency == 4

    def test_multi_instance_large_deployment_does_not_fail(self):
        s = Settings(
            DATABASE_URL=_PG_URL,
            WORKER_CONCURRENCY=10,
            WORKER_INSTANCE_COUNT=10,
        )
        assert s.worker_instance_count == 10

    # ------------------------------------------------------------------
    # Regression — param validators run before capacity guard
    # ------------------------------------------------------------------

    def test_invalid_pool_size_error_fires_before_capacity_guard(self):
        """Individual param validation (_check_worker_db_params) fires first."""
        with pytest.raises(ValidationError, match="WORKER_DB_POOL_SIZE must be >= 0"):
            _pool_settings(WORKER_DB_POOL_SIZE=-1, WORKER_CONCURRENCY=5)

    def test_zero_worker_concurrency_fires_before_capacity_guard(self):
        with pytest.raises(ValidationError, match="WORKER_CONCURRENCY must be > 0"):
            _pool_settings(WORKER_CONCURRENCY=0, WORKER_DB_POOL_SIZE=5)

    # ------------------------------------------------------------------
    # API pool is independent — high WORKER_CONCURRENCY is fine with separate pools
    # ------------------------------------------------------------------

    def test_worker_concurrency_higher_than_api_pool_is_now_valid(self):
        """Previously this would have failed the API-headroom guard.
        With separate pools, WORKER_CONCURRENCY > DB_POOL_SIZE + DB_MAX_OVERFLOW
        is valid — the worker has its own pool.
        """
        s = Settings(
            DATABASE_URL=_PG_URL,
            DB_POOL_SIZE=5,
            DB_MAX_OVERFLOW=5,
            WORKER_CONCURRENCY=50,  # far exceeds API pool — fine with separate pools
        )
        assert s.worker_concurrency == 50
        assert s.effective_worker_db_pool_size == 50

    def test_defaults_result_in_correct_both_pools(self):
        """Default config exposes both pools with correct independent settings."""
        s = _pool_settings()
        # API pool
        assert s.database_engine_kwargs["pool_size"] == 10
        assert s.database_engine_kwargs["max_overflow"] == 10
        # Worker pool
        assert s.worker_database_engine_kwargs["pool_size"] == 1  # == WORKER_CONCURRENCY default
        assert s.worker_database_engine_kwargs["max_overflow"] == 0
