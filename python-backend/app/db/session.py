from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# SESSION FACTORY ROUTING RULE
#
#   AsyncSessionFactory       — all HTTP-originated operations
#     • HTTP route / service reads and writes
#     • Short request-bound sessions (~100 ms)
#     • Operations that depend on auth / tenant request context
#
#   WorkerAsyncSessionFactory — background runner execution path only
#     • Dequeue / claim / mark-running / fail / persist worker results
#     • Nothing triggered directly by an HTTP request
#
# Rule of thumb: "Was this call initiated by an HTTP request?"
#   Yes → AsyncSessionFactory    No → WorkerAsyncSessionFactory
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# API engine — shared by all HTTP request handlers via FastAPI dependencies.
# Pool: DB_POOL_SIZE + DB_MAX_OVERFLOW.  Session lifetime ≈ one HTTP request.
# ---------------------------------------------------------------------------
engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,
    future=True,
    **settings.database_engine_kwargs,
)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        yield session


# ---------------------------------------------------------------------------
# Worker engine — isolated pool used exclusively by background job execution.
#
# Design invariants:
#   • max_overflow = 0: pool is exactly sized (no overflow connections).
#   • Sessions are opened and closed within each Phase of execute_job;
#     NO session is held during the AI analysis call (Phase 2).
#   • Pool size = WORKER_CONCURRENCY (auto-derived) so every concurrent
#     worker slot has exactly one dedicated pooled connection available.
#
# Keeping pools separate prevents workers from starving API connections
# regardless of concurrency level or AI call duration.
# ---------------------------------------------------------------------------
worker_engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,
    future=True,
    **settings.worker_database_engine_kwargs,
)

WorkerAsyncSessionFactory = async_sessionmaker(
    bind=worker_engine,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)
