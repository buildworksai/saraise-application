"""Forward/reverse/forward and PostgreSQL tenant-security migration evidence."""

from __future__ import annotations

import importlib
import inspect
from uuid import uuid4

import pytest
from django.db import connection, migrations
from django.db.migrations.executor import MigrationExecutor

APP = "ai_agent_management"
LEGACY = (APP, "0002_approvalrequest_ai_approval_tenant__15d886_idx")
LATEST = (APP, "0009_contract_legacy_columns")
MIGRATION_MODULES = tuple(
    f"src.modules.ai_agent_management.migrations.000{number}_{suffix}"
    for number, suffix in (
        (3, "expand_foundation_schema"),
        (4, "backfill_uuid_and_state"),
        (5, "switch_uuid_relations"),
        (6, "access_quota_projection"),
        (7, "constraints_and_indexes"),
        (8, "tenant_guards_and_rls"),
        (9, "contract_legacy_columns"),
    )
)


def test_all_required_migration_boundaries_exist_and_are_reversible():
    for module_name in MIGRATION_MODULES:
        migration = importlib.import_module(module_name).Migration
        assert migration.dependencies
        assert migration.operations
        for operation in migration.operations:
            assert operation.reversible, f"{module_name}: {operation!r} is irreversible"
            if isinstance(operation, migrations.RunPython):
                assert operation.reverse_code is not None
            if isinstance(operation, migrations.RunSQL):
                assert operation.reverse_sql is not None


def test_expand_backfill_switch_contract_order_is_linear():
    previous = LEGACY[1]
    for module_name in MIGRATION_MODULES:
        migration = importlib.import_module(module_name).Migration
        assert (APP, previous) in migration.dependencies
        previous = module_name.rsplit(".", 1)[-1]


def test_rls_migration_covers_every_tenant_table_and_relation():
    security = importlib.import_module(
        "src.modules.ai_agent_management.migrations.0008_tenant_guards_and_rls"
    )
    assert len(security.TABLES) >= 21
    assert len(security.TENANT_RELATIONS) >= 20
    source = inspect.getsource(security)
    for statement in (
        "ENABLE ROW LEVEL SECURITY",
        "FORCE ROW LEVEL SECURITY",
        "CREATE POLICY",
        "USING",
        "WITH CHECK",
        "CREATE TRIGGER",
        "DROP TRIGGER",
        "DROP POLICY",
        "DISABLE ROW LEVEL SECURITY",
    ):
        assert statement in source


@pytest.mark.django_db(transaction=True)
def test_schema_and_data_survive_forward_reverse_forward_round_trip():
    executor = MigrationExecutor(connection)
    executor.migrate([LEGACY])
    old_apps = executor.loader.project_state([LEGACY]).apps
    LegacyAgent = old_apps.get_model(APP, "Agent")
    tenant_id, agent_id, actor_id = uuid4(), uuid4(), uuid4()
    LegacyAgent.objects.create(
        id=str(agent_id),
        tenant_id=str(tenant_id),
        name="Migration evidence agent",
        identity_type="system_bound",
        subject_id=str(uuid4()),
        framework="reference",
        config={"schema_version": 1},
        created_by=str(actor_id),
    )

    try:
        executor = MigrationExecutor(connection)
        executor.migrate([LATEST])
        latest_apps = executor.loader.project_state([LATEST]).apps
        CurrentAgent = latest_apps.get_model(APP, "Agent")
        current = CurrentAgent.objects.get(pk=agent_id)
        assert current.tenant_id == tenant_id
        assert current.name == "Migration evidence agent"
        assert current.runner_key == "reference"
        assert current.created_by == actor_id

        executor = MigrationExecutor(connection)
        executor.migrate([LEGACY])
        reversed_apps = executor.loader.project_state([LEGACY]).apps
        ReversedAgent = reversed_apps.get_model(APP, "Agent")
        restored = ReversedAgent.objects.get(pk=str(agent_id))
        assert restored.tenant_id == str(tenant_id)
        assert restored.framework == "reference"
        assert restored.created_by == str(actor_id)

        executor = MigrationExecutor(connection)
        executor.migrate([LATEST])
        reapplied_apps = executor.loader.project_state([LATEST]).apps
        ReappliedAgent = reapplied_apps.get_model(APP, "Agent")
        assert ReappliedAgent.objects.filter(pk=agent_id, tenant_id=tenant_id).count() == 1
    finally:
        MigrationExecutor(connection).migrate([LATEST])


@pytest.mark.django_db(transaction=True)
def test_malformed_legacy_uuid_aborts_without_inventing_identity():
    executor = MigrationExecutor(connection)
    executor.migrate([LEGACY])
    old_apps = executor.loader.project_state([LEGACY]).apps
    LegacyAgent = old_apps.get_model(APP, "Agent")
    row = LegacyAgent.objects.create(
        id=str(uuid4()),
        tenant_id="not-a-uuid",
        name="Malformed tenant",
        identity_type="system_bound",
        subject_id=str(uuid4()),
        framework="reference",
        config={},
        created_by=str(uuid4()),
    )
    original_id = row.pk
    try:
        with pytest.raises((ValueError, RuntimeError)):
            MigrationExecutor(connection).migrate([(APP, "0004_backfill_uuid_and_state")])
        old_apps = MigrationExecutor(connection).loader.project_state([LEGACY]).apps
        LegacyAgent = old_apps.get_model(APP, "Agent")
        assert LegacyAgent.objects.filter(pk=original_id, tenant_id="not-a-uuid").count() == 1
    finally:
        # Remove the intentionally invalid row before restoring the shared test schema.
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM ai_agents WHERE id = %s", [original_id])
        MigrationExecutor(connection).migrate([LATEST])
