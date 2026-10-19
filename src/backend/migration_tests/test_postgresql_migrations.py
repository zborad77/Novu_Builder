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
HEAD = "20261017_0059"
SOFT_DELETE_REVISION = "20261017_0058"
RBAC_REVISION = "20261017_0057"
SUPERADMIN_FLAG_REVISION = "20261003_0056"
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
    if succeeds is None:
        pass
    elif succeeds:
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


def _roles(engine):
    with engine.connect() as connection:
        return list(connection.scalars(sa.text("SELECT role FROM users ORDER BY id")))


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
        # 0057 removes the manager rows seeded by 0018 (SA-01).
        assert permissions == {
            ("superadmin", "admin:read"),
            ("superadmin", "admin:write"),
            ("superadmin", "admin:jobs"),
            ("superadmin", "admin:impersonate"),
        }
        assert _assert_superadmin(inspector)["default"] is None
        assert {
            "ck_users_role_valid",
            "ck_users_superadmin_requires_flag",
        } <= {check["name"] for check in inspector.get_check_constraints("users")}

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
    # A "superadmin" role without the flag is never promoted; 0057 demotes it.
    assert _roles(database) == ["technician", "manager"]
    with database.connect() as connection:
        assert _assert_superadmin(sa.inspect(connection))["default"] is None


@pytest.mark.parametrize("default", ["", " DEFAULT false", " DEFAULT ('false'::boolean)"])
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
    assert _roles(database) == ["technician", "manager"]
    with database.connect() as connection:
        assert _assert_superadmin(sa.inspect(connection)) == before


@pytest.mark.parametrize(
    "definition, flags",
    [
        ("INTEGER NOT NULL DEFAULT 0", [0, 1]),
        ("BOOLEAN", [None, True]),
        ("BOOLEAN GENERATED ALWAYS AS (true) STORED NOT NULL", None),
        ("BOOLEAN NOT NULL DEFAULT true", [False, True]),
        ("BOOLEAN NOT NULL DEFAULT (true AND false)", [False, True]),
        ("BOOLEAN NOT NULL DEFAULT (random() > 0.5)", [False, True]),
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
    # Seed at 0056: from 0057 on the role/flag mismatch below is rejected.
    _cli(database, "upgrade", SUPERADMIN_FLAG_REVISION)
    _seed_users(database, flags=[False, True])
    _cli(database, "downgrade", PREVIOUS_HEAD)
    assert _version(database) == [PREVIOUS_HEAD]
    with database.connect() as connection:
        assert "is_superadmin" not in _columns(sa.inspect(connection), "users")
        assert connection.scalar(sa.text("SELECT count(*) FROM users")) == 2
    _cli(database, "upgrade", "head")
    assert _flags(database) == [False, False]
    assert _roles(database) == ["technician", "manager"]


def _seed_rbac_fixture(engine):
    """Users as an existing 0056 database may hold them, including the SA-01 escalation."""
    rows = [
        # id, role, is_superadmin, token_version
        ("u_admin_flag", "superadmin", True, 0),  # legitimate CLI-created superadmin
        ("u_escalated", "superadmin", False, 3),  # manager that PATCHed itself to "superadmin"
        ("u_manager", "manager", False, 0),
        ("u_dispatcher", "dispatcher", False, 1),  # former AdminUserCreate default
        ("u_technician", "technician", False, 0),
    ]
    with engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO organizations (id, name, default_currency) VALUES ('org', 'Migration fixture', 'CZK')")
        )
        for user_id, role, flag, version in rows:
            connection.execute(
                sa.text(
                    "INSERT INTO users (id, organization_id, email, password_hash, full_name, role, is_active,"
                    " is_superadmin, token_version)"
                    " VALUES (:id, 'org', :email, 'unused-fixture-hash', 'Fixture', :role, true, :flag, :version)"
                ),
                {"id": user_id, "email": f"{user_id}@migration.test", "role": role, "flag": flag, "version": version},
            )


def _users(engine):
    with engine.connect() as connection:
        return {
            row.id: row
            for row in connection.execute(
                sa.text("SELECT id, role, is_superadmin, token_version, tokens_valid_after FROM users")
            )
        }


def test_rbac_repair_on_existing_database(database):
    _cli(database, "upgrade", SUPERADMIN_FLAG_REVISION)
    _seed_rbac_fixture(database)
    with database.connect() as connection:
        assert ("manager", "admin:write") in set(
            connection.execute(sa.text("SELECT role, capability FROM role_permissions"))
        )

    _cli(database, "upgrade", "head")
    assert _version(database) == [HEAD]

    users = _users(database)
    # Legitimate superadmin and valid tenant roles are untouched.
    assert (users["u_admin_flag"].role, users["u_admin_flag"].is_superadmin) == ("superadmin", True)
    assert users["u_admin_flag"].token_version == 0
    assert users["u_manager"].role == "manager" and users["u_manager"].token_version == 0
    assert users["u_technician"].role == "technician"
    # Escalated and unknown roles drop to the least-privileged role; tokens die.
    for user_id, version in (("u_escalated", 4), ("u_dispatcher", 2)):
        assert users[user_id].role == "technician"
        assert users[user_id].is_superadmin is False
        assert users[user_id].token_version == version
        assert users[user_id].tokens_valid_after is not None

    with database.connect() as connection:
        assert {row.role for row in connection.execute(sa.text("SELECT role FROM role_permissions"))} == {"superadmin"}
        repairs = {
            row.resource_id: row.detail
            for row in connection.execute(
                sa.text("SELECT resource_id, detail FROM audit_logs WHERE action = 'migration.rbac_role_repair'")
            )
        }
        assert set(repairs) == {"u_escalated", "u_dispatcher"}
        assert repairs["u_escalated"]["previous_role"] == "superadmin"
        assert repairs["u_dispatcher"]["previous_role"] == "dispatcher"
        revoked = connection.scalar(
            sa.text("SELECT detail FROM audit_logs WHERE action = 'migration.rbac_permissions_revoked'")
        )
        assert {"role": "manager", "capability": "admin:write"} in revoked["revoked"]

    # The database itself now refuses both escalation shapes.
    for role, flag in (("superadmin", False), ("dispatcher", False)):
        with database.connect() as connection:
            with pytest.raises(sa.exc.IntegrityError):
                connection.execute(
                    sa.text(
                        "INSERT INTO users (id, organization_id, email, password_hash, full_name, role, is_active,"
                        " is_superadmin) VALUES ('u_new', 'org', 'new@migration.test', 'x', 'X', :role, true, :flag)"
                    ),
                    {"role": role, "flag": flag},
                )
    with database.connect() as connection:
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(sa.text("UPDATE users SET role = 'superadmin' WHERE id = 'u_manager'"))

    # Re-running upgrade is a no-op.
    assert "Running upgrade" not in _cli(database, "upgrade", "head")


def test_rbac_downgrade_drops_constraints_but_never_regrants_manager_permissions(database):
    _cli(database, "upgrade", SUPERADMIN_FLAG_REVISION)
    _seed_rbac_fixture(database)
    _cli(database, "upgrade", "head")
    _cli(database, "downgrade", SUPERADMIN_FLAG_REVISION)
    assert _version(database) == [SUPERADMIN_FLAG_REVISION]
    with database.connect() as connection:
        names = {check["name"] for check in sa.inspect(connection).get_check_constraints("users")}
        assert not names & {"ck_users_role_valid", "ck_users_superadmin_requires_flag"}
        assert {row.role for row in connection.execute(sa.text("SELECT role FROM role_permissions"))} == {"superadmin"}
    assert _users(database)["u_escalated"].role == "technician"
    _cli(database, "upgrade", "head")
    assert _version(database) == [HEAD]


def test_photo_soft_delete_columns_keep_existing_pending_deletes(database):
    _cli(database, "upgrade", RBAC_REVISION)
    with database.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO organizations (id, name, default_currency) VALUES ('org', 'Migration fixture', 'CZK')")
        )
        connection.execute(
            sa.text(
                "INSERT INTO users (id, organization_id, email, password_hash, full_name, role, is_active,"
                " is_superadmin) VALUES ('usr', 'org', 'usr@migration.test', 'x', 'Fixture', 'manager', true, false)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO projects (id, organization_id, created_by_user_id, title, status)"
                " VALUES ('prj', 'org', 'usr', 'Fixture', 'draft')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO project_photos (id, project_id, status, storage_key, original_filename, mime_type,"
                " file_size, processing_status, is_primary, is_analysis_reference, sort_order)"
                " VALUES ('pho', 'prj', 'pending_delete', 'k', 'a.jpg', 'image/jpeg', 1, 'ready', false, false, 1)"
            )
        )
    _cli(database, "upgrade", "head")
    with database.connect() as connection:
        columns = _columns(sa.inspect(connection), "project_photos")
        assert columns["deleted_at"]["nullable"] and columns["deleted_by_user_id"]["nullable"]
        assert any(
            fk["constrained_columns"] == ["deleted_by_user_id"]
            and fk["referred_table"] == "users"
            and fk["options"].get("ondelete") == "SET NULL"
            for fk in sa.inspect(connection).get_foreign_keys("project_photos")
        )
        # Legacy pending deletes keep NULL and are purged by the worker as before.
        row = connection.execute(
            sa.text("SELECT status, deleted_at, deleted_by_user_id FROM project_photos WHERE id = 'pho'")
        ).one()
        assert tuple(row) == ("pending_delete", None, None)
    _cli(database, "downgrade", RBAC_REVISION)
    with database.connect() as connection:
        assert "deleted_at" not in _columns(sa.inspect(connection), "project_photos")
        assert connection.scalar(sa.text("SELECT status FROM project_photos WHERE id = 'pho'")) == "pending_delete"


def test_photo_ownership_and_purge_state_on_existing_database(database):
    _cli(database, "upgrade", SOFT_DELETE_REVISION)
    with database.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO organizations (id, name, default_currency) VALUES ('org', 'Migration fixture', 'CZK')")
        )
        connection.execute(
            sa.text(
                "INSERT INTO users (id, organization_id, email, password_hash, full_name, role, is_active,"
                " is_superadmin) VALUES ('usr', 'org', 'usr@migration.test', 'x', 'Fixture', 'manager', true, false)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO projects (id, organization_id, created_by_user_id, title, status)"
                " VALUES ('prj', 'org', 'usr', 'Fixture', 'draft')"
            )
        )
        for photo_id, status in (("pho_active", "active"), ("pho_soft", "pending_delete")):
            connection.execute(
                sa.text(
                    "INSERT INTO project_photos (id, project_id, status, storage_key, original_filename, mime_type,"
                    " file_size, processing_status, is_primary, is_analysis_reference, sort_order)"
                    " VALUES (:id, 'prj', :status, 'k', 'a.jpg', 'image/jpeg', 1, 'ready', false, false, 1)"
                ),
                {"id": photo_id, "status": status},
            )
        with pytest.raises(sa.exc.IntegrityError):
            with connection.begin_nested():
                connection.execute(sa.text("UPDATE project_photos SET status = 'purge_pending' WHERE id = 'pho_active'"))

    _cli(database, "upgrade", "head")
    assert _version(database) == [HEAD]
    with database.begin() as connection:
        # Existing photos keep an unknown author; nothing is inferred.
        assert set(connection.execute(sa.text("SELECT id, uploaded_by_user_id FROM project_photos"))) == {
            ("pho_active", None),
            ("pho_soft", None),
        }
        connection.execute(sa.text("UPDATE project_photos SET uploaded_by_user_id = 'usr' WHERE id = 'pho_soft'"))
        connection.execute(sa.text("UPDATE project_photos SET status = 'purge_pending' WHERE id = 'pho_active'"))
        with pytest.raises(sa.exc.IntegrityError):
            with connection.begin_nested():
                connection.execute(sa.text("UPDATE project_photos SET status = 'gone' WHERE id = 'pho_active'"))

    # Downgrade refuses while a permanent deletion is unfinished.
    output = _cli(database, "downgrade", SOFT_DELETE_REVISION, succeeds=False)
    assert "purge_pending" in output
    assert _version(database) == [HEAD]

    with database.begin() as connection:
        connection.execute(sa.text("UPDATE project_photos SET status = 'deleted' WHERE id = 'pho_active'"))
        connection.execute(sa.text("DELETE FROM projects WHERE id = 'prj'"))  # cascade: photos
        connection.execute(
            sa.text(
                "INSERT INTO projects (id, organization_id, created_by_user_id, title, status)"
                " VALUES ('prj2', 'org', 'usr', 'Fixture', 'draft')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO users (id, organization_id, email, password_hash, full_name, role, is_active,"
                " is_superadmin) VALUES ('tech', 'org', 'tech@migration.test', 'x', 'T', 'technician', true, false)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO project_photos (id, project_id, status, storage_key, original_filename, mime_type,"
                " file_size, processing_status, is_primary, is_analysis_reference, sort_order, uploaded_by_user_id)"
                " VALUES ('pho_tech', 'prj2', 'active', 'k', 'a.jpg', 'image/jpeg', 1, 'ready', false, false, 1, 'tech')"
            )
        )
        # Removing the author keeps the photo and clears ownership.
        connection.execute(sa.text("DELETE FROM users WHERE id = 'tech'"))
        assert connection.execute(
            sa.text("SELECT status, uploaded_by_user_id FROM project_photos WHERE id = 'pho_tech'")
        ).one() == ("active", None)

    _cli(database, "downgrade", SOFT_DELETE_REVISION)
    with database.connect() as connection:
        assert "uploaded_by_user_id" not in _columns(sa.inspect(connection), "project_photos")


# ---------------------------------------------------------------------------
# Modulární refaktor (B0): schéma po čisté instalaci a shoda ORM × migrace.
# Baseline vznikla na 3f581d7 před prvním přesunem kódu. Refaktor nesmí změnit
# ani schéma vytvořené migracemi, ani metadata modelů vůči tomuto schématu.
# Přegenerování (jen pro schválenou změnu schématu):
#     NC_UPDATE_SCHEMA_BASELINE=1 python -m pytest migration_tests -k schema_baseline
# ---------------------------------------------------------------------------

SCHEMA_BASELINE = BACKEND_ROOT / "migration_tests" / "baseline" / "pg_schema.json"


def _reflect_schema(engine):
    queries = {
        "columns": """
            SELECT table_name, column_name, ordinal_position, data_type, udt_name, is_nullable,
                   column_default, character_maximum_length, numeric_precision, numeric_scale
            FROM information_schema.columns WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position""",
        "constraints": """
            SELECT rel.relname AS table_name, con.conname, con.contype,
                   pg_get_constraintdef(con.oid, true) AS definition
            FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace ns ON ns.oid = rel.relnamespace
            WHERE ns.nspname = 'public' ORDER BY rel.relname, con.conname""",
        "indexes": """
            SELECT tablename, indexname, indexdef FROM pg_indexes
            WHERE schemaname = 'public' ORDER BY tablename, indexname""",
        "enums": """
            SELECT t.typname, e.enumlabel, e.enumsortorder FROM pg_type t
            JOIN pg_enum e ON e.enumtypid = t.oid ORDER BY t.typname, e.enumsortorder""",
        "alembic_version": "SELECT version_num FROM alembic_version",
    }
    with engine.connect() as connection:
        return {
            name: [
                {key: (str(value) if value is not None and not isinstance(value, (int, str)) else value)
                 for key, value in row._mapping.items()}
                for row in connection.execute(sa.text(sql))
            ]
            for name, sql in queries.items()
        }


def test_fresh_install_schema_matches_baseline(database):
    import json

    _cli(database, "upgrade", "head")
    schema = _reflect_schema(database)
    rendered = json.dumps(schema, indent=1, ensure_ascii=False) + "\n"
    if os.environ.get("NC_UPDATE_SCHEMA_BASELINE") == "1":
        SCHEMA_BASELINE.parent.mkdir(parents=True, exist_ok=True)
        SCHEMA_BASELINE.write_bytes(rendered.encode("utf-8"))
    assert SCHEMA_BASELINE.is_file(), "missing baseline; see NC_UPDATE_SCHEMA_BASELINE"
    assert json.loads(SCHEMA_BASELINE.read_text(encoding="utf-8")) == schema


def _normalized_metadata_diff(engine):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.platform.db.base import Base
    from app.composition.models import import_all_models

    import_all_models()

    def render(value):
        arg = getattr(value, "arg", None)
        if arg is not None:
            return str(getattr(arg, "text", arg))
        return str(value)

    def describe(diff):
        if isinstance(diff, list):  # modify_* operace jsou zabalené v seznamu
            return [entry for item in diff for entry in describe(item)]
        op, *rest = diff
        if op in {"add_table", "remove_table"}:
            return [f"{op}:{rest[0].name}"]
        if op in {"add_index", "remove_index"}:
            return [f"{op}:{rest[0].table.name}:{rest[0].name}"]
        if op in {"add_constraint", "remove_constraint", "add_fk", "remove_fk"}:
            constraint = rest[0]
            return [f"{op}:{constraint.table.name}:{constraint.name}"]
        if op in {"add_column", "remove_column"}:
            return [f"{op}:{rest[1]}:{rest[2].name}"]
        if op.startswith("modify_"):
            _schema, table, column, _info, old, new = rest
            return [f"{op}:{table}:{column}:{render(old)}->{render(new)}"]
        return [f"{op}:{rest!s}"]

    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": True}
        )
        diffs = compare_metadata(context, Base.metadata)
    return sorted(entry for diff in diffs for entry in describe(diff))


def test_orm_metadata_matches_migrated_schema(database):
    """Autogenerate nad hlavou: rozdíl ORM × migrace se refaktorem nesmí změnit.

    Baseline obsahuje už existující rozdíly (např. tabulky vytvořené jen migrací);
    přesun modelů mezi moduly nesmí přidat ani odebrat jediný řádek.
    """
    _cli(database, "upgrade", "head")
    import re

    entries = [re.sub(r" at 0x[0-9A-Fa-f]+", "", line) for line in _normalized_metadata_diff(database)]
    rendered = "\n".join(entries) + "\n"
    baseline = BACKEND_ROOT / "migration_tests" / "baseline" / "metadata_diff.txt"
    if os.environ.get("NC_UPDATE_SCHEMA_BASELINE") == "1":
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_bytes(rendered.encode("utf-8"))
    assert baseline.read_text(encoding="utf-8") == rendered
