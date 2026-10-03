"""Real CLI migrations on empty PostgreSQL 16 databases, outside tests/conftest.py.

MIGRATION_TEST_ADMIN_URL must name a disposable PostgreSQL 16 server and a role
with CREATE DATABASE permission. Missing configuration is an error, never a skip.
Only randomly named databases created by this module are dropped during cleanup.
"""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import subprocess
import sys
from uuid import uuid4

from dotenv import dotenv_values
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


BACKEND_ROOT = Path(__file__).resolve().parents[1]
HEAD = "20261003_0056"
PREVIOUS_HEAD = "20260527_0055"
BASELINE_TABLES = {
    "organizations",
    "users",
    "clients",
    "projects",
    "project_photos",
    "analysis_jobs",
    "analysis_results",
    "pricing_profiles",
    "suppliers",
    "material_catalog",
    "supplier_material_prices",
    "quote_variants",
    "quote_items",
}


@pytest.fixture(scope="session")
def admin_engine():
    value = os.environ.get("MIGRATION_TEST_ADMIN_URL")
    if not value:
        pytest.fail("MIGRATION_TEST_ADMIN_URL is required; PostgreSQL migration tests cannot skip.")
    url = sa.make_url(value)
    if url.drivername != "postgresql+psycopg":
        pytest.fail("MIGRATION_TEST_ADMIN_URL must use postgresql+psycopg.")
    engine = sa.create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            version = int(connection.scalar(sa.text("SHOW server_version_num")))
            assert 160000 <= version < 170000, "Migration regressions require PostgreSQL 16."
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def database(admin_engine):
    name = "novu_migration_test_" + uuid4().hex
    quoted_name = admin_engine.dialect.identifier_preparer.quote(name)
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f"CREATE DATABASE {quoted_name} TEMPLATE template0")
    engine = sa.create_engine(admin_engine.url.set(database=name))
    try:
        with engine.connect() as connection:
            assert sa.inspect(connection).get_table_names(schema="public") == []
            assert connection.scalar(sa.text("SELECT to_regclass('public.alembic_version')")) is None
        yield engine
    finally:
        engine.dispose()
        # Never target the configured admin database or any pre-existing database.
        assert name.startswith("novu_migration_test_") and name != admin_engine.url.database
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE {quoted_name}")


def _cli(engine, *arguments, succeeds=True):
    # Use the committed strict profile, not a developer's local .env files.
    values = {
        key: value
        for key, value in dotenv_values(BACKEND_ROOT / ".env.production.example").items()
        if value is not None
    }
    values.update(
        {
            "APP_ENV": "production",
            "APP_BASE_URL": "https://migration-regression.test",
            "CORS_ALLOWED_ORIGINS": "https://migration-regression.test",
            "DATABASE_URL": engine.url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False),
            "DATABASE_URL_SYNC": engine.url.render_as_string(hide_password=False),
            "DB_AUTO_CREATE_SCHEMA": "false",
            "DB_SEED_ON_STARTUP": "false",
            "AI_ANALYSIS_PROVIDER": "mock",
            "AI_OFFER_PROVIDER": "mock",
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY": "",
            "JWT_SECRET": secrets.token_hex(32),
            "METRICS_AUTH_TOKEN": secrets.token_hex(32),
            "REDIS_URL": "redis://:" + secrets.token_hex(24) + "@127.0.0.1:6379/0",
            "MINIO_ROOT_USER": "migration-regression",
            "MINIO_ROOT_PASSWORD": secrets.token_hex(24),
            "S3_ACCESS_KEY_ID": secrets.token_hex(16),
            "S3_SECRET_ACCESS_KEY": secrets.token_hex(32),
            "S3_ENDPOINT_URL": "http://127.0.0.1:9000",
        }
    )
    env = os.environ.copy()
    env.update(values)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = result.stdout + result.stderr
    for value in [
        engine.url.password,
        *(
            values[key]
            for key in (
                "JWT_SECRET",
                "METRICS_AUTH_TOKEN",
                "REDIS_URL",
                "MINIO_ROOT_PASSWORD",
                "S3_ACCESS_KEY_ID",
                "S3_SECRET_ACCESS_KEY",
            )
        ),
    ]:
        if value:
            output = output.replace(value, "[REDACTED]")
    if succeeds:
        assert result.returncode == 0, output
    else:
        assert result.returncode != 0, "Incompatible schema unexpectedly migrated successfully."
    return output


def _version(engine):
    with engine.connect() as connection:
        return list(connection.scalars(sa.text("SELECT version_num FROM alembic_version")))


def _columns(inspector, table):
    return {column["name"]: column for column in inspector.get_columns(table)}


def _assert_superadmin(inspector):
    column = _columns(inspector, "users")["is_superadmin"]
    assert isinstance(column["type"], sa.Boolean)
    assert column["nullable"] is False
    # Reflected TypeEngine instances differ by identity across connections.
    return column | {"type": str(column["type"])}


def _seed_users(engine, flags=None):
    with engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO organizations (id, name, default_currency) VALUES ('org', 'Migration fixture', 'CZK')")
        )
        for index, role in enumerate(("superadmin", "manager")):
            # The role must not be used to infer the superadmin flag in 0056.
            column = ", is_superadmin" if flags is not None else ""
            value = ", :flag" if flags is not None else ""
            connection.execute(
                sa.text(
                    "INSERT INTO users (id, organization_id, email, password_hash, full_name, role, is_active"
                    + column
                    + ")"
                    + " VALUES (:id, 'org', :email, 'unused-fixture-hash', 'Fixture', :role, true"
                    + value
                    + ")"
                ),
                {
                    "id": f"user{index}",
                    "email": f"user{index}@migration.test",
                    "role": role,
                    "flag": flags[index] if flags is not None else None,
                },
            )


def _flags(engine):
    with engine.connect() as connection:
        return list(connection.scalars(sa.text("SELECT is_superadmin FROM users ORDER BY id")))


def test_empty_database_upgrade_head_and_repeat_is_noop(database):
    _cli(database, "upgrade", "head")
    assert _cli(database, "heads").strip() == f"{HEAD} (head)"
    assert f"{HEAD} (head)" in _cli(database, "current")
    assert _version(database) == [HEAD]

    with database.connect() as connection:
        inspector = sa.inspect(connection)
        tables = set(inspector.get_table_names())
        assert len(tables) == 56  # 13 baseline + 42 later tables + alembic_version.
        assert {
            "revoked_tokens",
            "work_categories",
            "work_types",
            "work_type_parameters",
            "project_work_items",
            "project_work_item_values",
            "vision_detections",
            "catalog_analysis_profiles",
            "catalog_pricing_profiles",
            "work_type_components",
            "tenant_work_type_extra_parameters",
            "project_status_history",
            "reconciler_events",
        } <= tables
        revoked = _columns(inspector, "revoked_tokens")
        assert set(revoked) == {"jti", "expires_at", "created_at"}
        assert isinstance(revoked["jti"]["type"], sa.String) and revoked["jti"]["type"].length == 64
        assert inspector.get_pk_constraint("revoked_tokens")["constrained_columns"] == ["jti"]
        for name in ("expires_at", "created_at"):
            assert isinstance(revoked[name]["type"], sa.DateTime) and revoked[name]["type"].timezone
            assert revoked[name]["nullable"] is False
        revoked_indexes = {index["name"]: index for index in inspector.get_indexes("revoked_tokens")}
        assert revoked_indexes["ix_revoked_tokens_expires_at"]["column_names"] == ["expires_at"]
        assert revoked_indexes["idx_revoked_tokens_expires_at"]["column_names"] == ["expires_at"]
        results = _columns(inspector, "analysis_results")
        for name in ("estimated_duration_days", "labor_hours_total"):
            assert isinstance(results[name]["type"], sa.Float)
        assert {
            "parent_job_id",
            "retry_count",
            "error_traceback",
            "input_payload",
            "output_summary",
            "lease_token",
            "worker_id",
            "leased_at",
            "heartbeat_at",
            "attempt_count",
            "input_payload_storage_key",
        } <= _columns(inspector, "analysis_jobs").keys()
        assert "marker_source" in _columns(inspector, "markers")
        jobs = _columns(inspector, "offer_jobs")
        for name in ("lease_version", "error_repeat_count"):
            assert isinstance(jobs[name]["type"], sa.Integer) and jobs[name]["nullable"] is False
        outbox = _columns(inspector, "outbox_events")
        assert isinstance(outbox["seq"]["type"], sa.BigInteger)
        assert outbox["seq"]["identity"]["always"] is True
        seq_index = next(i for i in inspector.get_indexes("outbox_events") if i["name"] == "idx_outbox_events_seq")
        assert seq_index["unique"] and seq_index["column_names"] == ["seq"]
        assert any(
            c["name"] == "uq_agent_runs_offer_job" and c["column_names"] == ["offer_job_id"]
            for c in inspector.get_unique_constraints("agent_runs")
        )
        assert isinstance(_columns(inspector, "reconciler_events")["extra"]["type"], JSONB)
        assert any(
            fk["constrained_columns"] == ["analysis_result_id"]
            and fk["referred_table"] == "analysis_results"
            and fk["referred_columns"] == ["id"]
            and fk["options"]["ondelete"] == "SET NULL"
            for fk in inspector.get_foreign_keys("project_final_proposals")
        )
        assert any(
            i["name"] == "idx_project_final_proposals_analysis_result_id"
            and i["column_names"] == ["analysis_result_id"]
            for i in inspector.get_indexes("project_final_proposals")
        )
        for table, field in (
            ("pricing_profiles", "hourly_rate"),
            ("material_catalog", "default_unit_price"),
            ("supplier_material_prices", "unit_price"),
            ("quote_variants", "total_inc_vat"),
            ("quote_items", "unit_price"),
            ("project_proposal_drafts", "transport_cost"),
            ("project_final_proposals", "total_price"),
        ):
            number = _columns(inspector, table)[field]["type"]
            assert isinstance(number, sa.Numeric) and (number.precision, number.scale) == (14, 4)
        permissions = set(connection.execute(sa.text("SELECT role, capability FROM role_permissions")))
        assert permissions == {
            ("superadmin", "admin:read"),
            ("superadmin", "admin:write"),
            ("superadmin", "admin:jobs"),
            ("superadmin", "admin:impersonate"),
            ("manager", "admin:read"),
            ("manager", "admin:write"),
        }
        assert _assert_superadmin(inspector)["default"] is None

    # Exercise the actual GENERATED ALWAYS contract, not only reflected metadata.
    with database.begin() as connection:
        for index in range(2):
            connection.execute(
                sa.text(
                    "INSERT INTO outbox_events (id, event_type, aggregate_type, aggregate_id, organization_id, payload) "
                    "VALUES (:id, 'fixture', 'fixture', 'fixture', 'fixture', '{}'::jsonb)"
                ),
                {"id": f"event{index}"},
            )
        sequence = list(connection.scalars(sa.text("SELECT seq FROM outbox_events ORDER BY seq")))
        assert sequence[0] < sequence[1]
    with database.connect() as connection:
        with pytest.raises(sa.exc.ProgrammingError, match="non-DEFAULT value"):
            connection.execute(
                sa.text(
                    "INSERT INTO outbox_events (id, event_type, aggregate_type, aggregate_id, organization_id, payload, seq) "
                    "VALUES ('explicit', 'fixture', 'fixture', 'fixture', 'fixture', '{}'::jsonb, 99)"
                )
            )
    with database.connect() as connection:
        before = {table: connection.scalar(sa.text(f'SELECT count(*) FROM "{table}"')) for table in tables}
        definitions = connection.execute(
            sa.text(
                "SELECT oid, relname, relkind FROM pg_class WHERE relnamespace = 'public'::regnamespace ORDER BY oid"
            )
        ).all()
    assert "Running upgrade" not in _cli(database, "upgrade", "head")
    assert _version(database) == [HEAD]
    with database.connect() as connection:
        assert before == {table: connection.scalar(sa.text(f'SELECT count(*) FROM "{table}"')) for table in tables}
        assert (
            definitions
            == connection.execute(
                sa.text(
                    "SELECT oid, relname, relkind FROM pg_class WHERE relnamespace = 'public'::regnamespace ORDER BY oid"
                )
            ).all()
        )


def test_previous_head_missing_flag_backfills_false(database):
    _cli(database, "upgrade", PREVIOUS_HEAD)
    assert _version(database) == [PREVIOUS_HEAD]
    with database.connect() as connection:
        assert "is_superadmin" not in _columns(sa.inspect(connection), "users")
    _seed_users(database)
    _cli(database, "upgrade", "head")
    assert _version(database) == [HEAD]
    assert _flags(database) == [False, False]
    with database.connect() as connection:
        assert _assert_superadmin(sa.inspect(connection))["default"] is None


@pytest.mark.parametrize("default", ["", " DEFAULT false"])
def test_previous_head_existing_valid_flag_preserves_values(database, default):
    _cli(database, "upgrade", PREVIOUS_HEAD)
    with database.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN is_superadmin BOOLEAN NOT NULL" + default)
    _seed_users(database, flags=[False, True])
    with database.connect() as connection:
        before = _assert_superadmin(sa.inspect(connection))
    _cli(database, "upgrade", "head")
    assert _version(database) == [HEAD]
    assert _flags(database) == [False, True]
    with database.connect() as connection:
        assert _assert_superadmin(sa.inspect(connection)) == before


@pytest.mark.parametrize(
    "definition, flags",
    [
        ("INTEGER NOT NULL DEFAULT 0", [0, 1]),
        ("BOOLEAN", [None, True]),
        ("BOOLEAN GENERATED ALWAYS AS (true) STORED NOT NULL", None),
    ],
)
def test_previous_head_incompatible_flag_fails_closed(database, definition, flags):
    _cli(database, "upgrade", PREVIOUS_HEAD)
    with database.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN is_superadmin " + definition)
    _seed_users(database, flags=flags)
    before = _flags(database)
    output = _cli(database, "upgrade", "head", succeeds=False)
    assert "Incompatible users.is_superadmin" in output
    assert _version(database) == [PREVIOUS_HEAD]
    assert _flags(database) == before


def test_frozen_baseline_owns_only_historical_objects(database):
    _cli(database, "upgrade", "20260318_0001")
    with database.connect() as connection:
        inspector = sa.inspect(connection)
        assert set(inspector.get_table_names()) == BASELINE_TABLES | {"alembic_version"}
        assert "is_superadmin" not in _columns(inspector, "users")
        assert "estimated_duration_days" not in _columns(inspector, "analysis_results")
        assert "is_analysis_reference" not in _columns(inspector, "project_photos")
        assert "reference_expectations_json" not in _columns(inspector, "projects")
        assert isinstance(_columns(inspector, "pricing_profiles")["hourly_rate"]["type"], sa.Float)
        connection.rollback()
        connection.exec_driver_sql("CREATE TABLE unrelated_fixture (id integer PRIMARY KEY)")
        connection.commit()
    _cli(database, "downgrade", "base")
    with database.connect() as connection:
        assert set(sa.inspect(connection).get_table_names()) == {"alembic_version", "unrelated_fixture"}
        assert list(connection.scalars(sa.text("SELECT version_num FROM alembic_version"))) == []


def test_superadmin_downgrade_drops_flag_and_reupgrade_does_not_restore_privileges(database):
    _cli(database, "upgrade", "head")
    _seed_users(database, flags=[False, True])
    _cli(database, "downgrade", PREVIOUS_HEAD)
    assert _version(database) == [PREVIOUS_HEAD]
    with database.connect() as connection:
        assert "is_superadmin" not in _columns(sa.inspect(connection), "users")
        assert connection.scalar(sa.text("SELECT count(*) FROM users")) == 2
    _cli(database, "upgrade", "head")
    assert _flags(database) == [False, False]
