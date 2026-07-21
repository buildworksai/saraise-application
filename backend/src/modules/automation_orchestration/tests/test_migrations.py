"""Migration-state, reversibility, and PostgreSQL RLS verification."""

from __future__ import annotations

import importlib
import uuid

import pytest
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.operations.special import SeparateDatabaseAndState


class _Connection:
    def __init__(self, vendor: str) -> None:
        self.vendor = vendor


class _SchemaEditor:
    def __init__(self, vendor: str) -> None:
        self.connection = _Connection(vendor)
        self.statements: list[str] = []

    def execute(self, sql: str) -> None:
        self.statements.append(sql)


def test_rls_migration_is_postgresql_only_typed_and_reversible() -> None:
    migration = importlib.import_module("src.modules.automation_orchestration.migrations.0003_enable_orchestration_rls")
    postgres = _SchemaEditor("postgresql")
    migration.enable_orchestration_rls(None, postgres)

    assert len(postgres.statements) == 8
    assert all("saraise_enable_rls" in statement and "::REGCLASS" in statement for statement in postgres.statements)
    assert all(table in "\n".join(postgres.statements) for table in migration.TENANT_TABLES)

    migration.disable_orchestration_rls(None, postgres)
    reverse_sql = "\n".join(postgres.statements[8:])
    assert reverse_sql.count("DROP POLICY IF EXISTS") == 8
    assert reverse_sql.count("NO FORCE ROW LEVEL SECURITY") == 8
    assert reverse_sql.count("DISABLE ROW LEVEL SECURITY") == 8

    sqlite = _SchemaEditor("sqlite")
    migration.enable_orchestration_rls(None, sqlite)
    migration.disable_orchestration_rls(None, sqlite)
    assert sqlite.statements == []


@pytest.mark.django_db
def test_migration_state_removes_runtime_scaffold_without_dropping_legacy_table() -> None:
    executor = MigrationExecutor(connection)
    state_0001 = executor.loader.project_state([("automation_orchestration", "0001_initial")])
    state_0002 = executor.loader.project_state([("automation_orchestration", "0002_create_orchestration_domain")])

    assert ("automation_orchestration", "automationorchestrationresource") in state_0001.models
    assert ("automation_orchestration", "automationorchestrationresource") not in state_0002.models
    assert {
        "orchestrationdefinition",
        "orchestrationnode",
        "orchestrationedge",
        "orchestrationschedule",
        "orchestrationrun",
        "orchestrationtaskrun",
        "retryattempt",
        "orchestrationevent",
    } <= {model_name for app_label, model_name in state_0002.models if app_label == "automation_orchestration"}

    migration = importlib.import_module(
        "src.modules.automation_orchestration.migrations.0002_create_orchestration_domain"
    )
    state_only_delete = [
        operation for operation in migration.Migration.operations if isinstance(operation, SeparateDatabaseAndState)
    ]
    assert len(state_only_delete) == 1
    assert state_only_delete[0].database_operations == []


@pytest.mark.django_db
def test_domain_tables_and_legacy_table_physically_coexist() -> None:
    tables = set(connection.introspection.table_names())
    assert {
        "automation_orchestration_resources",
        "automation_orchestration_definitions",
        "automation_orchestration_nodes",
        "automation_orchestration_edges",
        "automation_orchestration_schedules",
        "automation_orchestration_runs",
        "automation_orchestration_task_runs",
        "automation_orchestration_retry_attempts",
        "automation_orchestration_events",
    } <= tables


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_postgresql_17_forward_reverse_forward_preserves_legacy_and_schema() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL migration behavior requires the PostgreSQL test database")

    with connection.cursor() as cursor:
        cursor.execute("SHOW server_version_num")
        assert int(cursor.fetchone()[0]) >= 170000

    executor = MigrationExecutor(connection)
    target_0001 = [("automation_orchestration", "0001_initial")]
    target_latest = [("automation_orchestration", "0003_enable_orchestration_rls")]
    legacy_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())

    executor.migrate(target_0001)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO automation_orchestration_resources
                    (tenant_id, created_at, updated_at, id, name, description, is_active, config, created_by)
                VALUES (%s, NOW(), NOW(), %s, %s, %s, TRUE, %s::jsonb, %s)
                """,
                [tenant_id, legacy_id, "legacy", "unchanged", '{"opaque":[1,2,3]}', actor_id],
            )
            cursor.execute(
                "SELECT tenant_id, id, name, description, is_active, config::text, created_by "
                "FROM automation_orchestration_resources WHERE id = %s",
                [legacy_id],
            )
            original = cursor.fetchone()

        executor = MigrationExecutor(connection)
        executor.migrate(target_latest)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tenant_id, id, name, description, is_active, config::text, created_by "
                "FROM automation_orchestration_resources WHERE id = %s",
                [legacy_id],
            )
            assert cursor.fetchone() == original
            cursor.execute("""
                SELECT relname, relrowsecurity, relforcerowsecurity
                FROM pg_class
                WHERE relname LIKE 'automation_orchestration_%'
                """)
            rls = {name: (enabled, forced) for name, enabled, forced in cursor.fetchall()}
            rls_migration = importlib.import_module(
                "src.modules.automation_orchestration.migrations.0003_enable_orchestration_rls"
            )
            assert all(rls[table] == (True, True) for table in rls_migration.TENANT_TABLES)
            cursor.execute("SELECT conname FROM pg_constraint WHERE conname LIKE 'ao_%'")
            assert len({row[0] for row in cursor.fetchall()}) >= 20
            cursor.execute("SELECT indexname FROM pg_indexes WHERE indexname LIKE 'ao_%'")
            assert len({row[0] for row in cursor.fetchall()}) >= 20

        executor = MigrationExecutor(connection)
        executor.migrate(target_0001)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tenant_id, id, name, description, is_active, config::text, created_by "
                "FROM automation_orchestration_resources WHERE id = %s",
                [legacy_id],
            )
            assert cursor.fetchone() == original
            cursor.execute("SELECT to_regclass('automation_orchestration_definitions')")
            assert cursor.fetchone()[0] is None

        executor = MigrationExecutor(connection)
        executor.migrate(target_latest)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tenant_id, id, name, description, is_active, config::text, created_by "
                "FROM automation_orchestration_resources WHERE id = %s",
                [legacy_id],
            )
            assert cursor.fetchone() == original
    finally:
        MigrationExecutor(connection).migrate(target_latest)


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_postgresql_rls_isolates_tenant_reads_and_writes_for_non_owner() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL RLS behavior requires the PostgreSQL test database")

    role_name = f"ao_rls_{uuid.uuid4().hex[:12]}"
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    event_a = uuid.uuid4()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE ROLE "{role_name}" NOLOGIN NOSUPERUSER NOBYPASSRLS')
            cursor.execute(f'GRANT USAGE ON SCHEMA public TO "{role_name}"')
            cursor.execute(f'GRANT SELECT, INSERT ON automation_orchestration_events TO "{role_name}"')
            cursor.execute(f'SET ROLE "{role_name}"')
            cursor.execute("SELECT set_config('app.tenant_id', %s, FALSE)", [str(tenant_a)])
            cursor.execute(
                """
                INSERT INTO automation_orchestration_events
                    (tenant_id, id, aggregate_type, aggregate_id, event_type, correlation_id, payload, occurred_at)
                VALUES (%s, %s, 'run', %s, 'run.created', %s, '{}'::jsonb, NOW())
                """,
                [str(tenant_a), str(event_a), str(event_a), uuid.uuid4().hex],
            )
            cursor.execute("SELECT id FROM automation_orchestration_events")
            assert cursor.fetchall() == [(event_a,)]
            cursor.execute("SELECT set_config('app.tenant_id', %s, FALSE)", [str(tenant_b)])
            cursor.execute("SELECT id FROM automation_orchestration_events")
            assert cursor.fetchall() == []
            with pytest.raises(Exception):
                with transaction.atomic():
                    cursor.execute(
                        """
                        INSERT INTO automation_orchestration_events (
                            tenant_id, id, aggregate_type, aggregate_id,
                            event_type, correlation_id, payload, occurred_at
                        )
                        VALUES (%s, %s, 'run', %s, 'run.created', %s, '{}'::jsonb, NOW())
                        """,
                        [str(tenant_a), str(uuid.uuid4()), str(event_a), uuid.uuid4().hex],
                    )
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f'DROP OWNED BY "{role_name}"')
            cursor.execute(f'DROP ROLE IF EXISTS "{role_name}"')
