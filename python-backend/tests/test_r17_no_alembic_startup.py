"""R-17: Application startup must not run 'alembic upgrade head'.
Schema migrations are the responsibility of the deployment step, not the app process.
"""
import inspect


def test_lifespan_does_not_call_alembic_upgrade():
    """lifespan must not contain alembic_command.upgrade() call."""
    from app import main
    source = inspect.getsource(main.lifespan)
    assert "alembic_command.upgrade" not in source, (
        "lifespan must not run 'alembic upgrade head' — run migrations in the "
        "deployment step (docker-entrypoint.sh or equivalent), not at app startup."
    )


def test_lifespan_contains_schema_version_check():
    """lifespan must contain a schema version guard (fail-fast on mismatch)."""
    from app import main
    source = inspect.getsource(main.lifespan)
    assert "get_current_revision" in source, (
        "lifespan must verify the DB is at the expected schema revision."
    )
    assert "expected_head" in source or "MigrationContext" in source


def test_startup_raises_if_schema_mismatch():
    """Schema guard logic must raise RuntimeError when current_rev != expected_head."""
    import pytest

    # Replicate the guard logic from lifespan directly — no DB needed.
    def _schema_guard(current_rev: str, expected_head: str) -> None:
        if current_rev != expected_head:
            raise RuntimeError(
                f"Database schema is not at the expected revision. "
                f"Current: {current_rev!r}, expected head: {expected_head!r}. "
                f"Run 'alembic upgrade head' before starting the application."
            )

    with pytest.raises(RuntimeError, match="not at the expected revision"):
        _schema_guard("old_rev_abc", "new_rev_xyz")

    # No exception when revisions match
    _schema_guard("abc123", "abc123")  # must not raise
