"""Reversible legacy evolution and PostgreSQL RLS migration contracts."""

from __future__ import annotations

import importlib
import uuid
from types import SimpleNamespace

import pytest
from django.db import connection, migrations
from django.db.migrations.executor import MigrationExecutor

EXPECTED_DOMAIN_TABLES = {
    "mdm_entity_types",
    "mdm_entities",
    "mdm_entity_versions",
    "mdm_quality_rules",
    "mdm_quality_issues",
    "mdm_matching_rules",
    "mdm_match_candidates",
    "mdm_merge_history",
    "mdm_merge_participants",
}


def migration(number_and_name: str):
    return importlib.import_module(
        f"src.modules.master_data_management.migrations.{number_and_name}"
    )


def test_migration_graph_has_exact_reversible_sequence_and_preserves_0001() -> None:
    names = [
        "0001_initial",
        "0002_add_entity_types_and_entity_evolution",
        "0003_backfill_entity_types",
        "0004_add_quality_matching_merge_versions",
        "0005_enforce_entity_contract",
        "0006_add_concurrent_indexes",
        "0007_enable_domain_rls",
    ]
    loaded = [migration(name).Migration for name in names]
    assert loaded[0].dependencies == []
    for index in range(1, 7):
        expected_previous = names[index - 1]
        assert ("master_data_management", expected_previous) in loaded[index].dependencies
    assert ("core", "0011_apply_typed_rls_to_notifications") in loaded[-1].dependencies

    initial_creates = [
        operation for operation in loaded[0].operations if isinstance(operation, migrations.CreateModel)
    ]
    assert len(initial_creates) == 1
    legacy = initial_creates[0]
    assert legacy.name == "MasterDataEntity"
    assert legacy.options["db_table"] == "mdm_entities"
    assert {field_name for field_name, _ in legacy.fields} == {
        "id",
        "tenant_id",
        "entity_type",
        "entity_code",
        "entity_name",
        "data",
        "is_active",
        "created_at",
        "updated_at",
    }


def test_domain_creation_migration_defines_all_supporting_tables() -> None:
    type_migration = migration("0002_add_entity_types_and_entity_evolution").Migration
    domain_migration = migration("0004_add_quality_matching_merge_versions").Migration
    created = {
        operation.options["db_table"]
        for operation in (*type_migration.operations, *domain_migration.operations)
        if isinstance(operation, migrations.CreateModel)
    }
    # mdm_entities is preserved and evolved from 0001, so the later migrations
    # create every other required table exactly once.
    assert created == EXPECTED_DOMAIN_TABLES - {"mdm_entities"}


def test_backfill_is_reversible_collision_safe_and_uses_stable_migration_actor() -> None:
    module = migration("0003_backfill_entity_types")
    operation = module.Migration.operations[0]
    assert isinstance(operation, migrations.RunPython)
    assert operation.code is module.backfill_entity_types
    assert operation.reverse_code is module.restore_legacy_values
    tenant = uuid.uuid4()
    assert module._system_actor(tenant) == module._system_actor(tenant)
    assert module._system_actor(tenant) != module._system_actor(uuid.uuid4())
    assert module.KEY_PATTERN.fullmatch("paid_industry_type")
    assert module.KEY_PATTERN.fullmatch("Vendor") is None


def test_contract_migration_verifies_before_removing_legacy_columns() -> None:
    module = migration("0005_enforce_entity_contract")
    operations = module.Migration.operations
    verification_index = next(
        index
        for index, operation in enumerate(operations)
        if isinstance(operation, migrations.RunPython)
        and operation.code is module.verify_canonical_entity_values
    )
    removals = {
        operation.name: index
        for index, operation in enumerate(operations)
        if isinstance(operation, migrations.RemoveField)
    }
    assert set(removals) == {"legacy_entity_type", "is_active"}
    assert all(verification_index < index for index in removals.values())
    verification = operations[verification_index]
    assert verification.reverse_code is module.reconstruct_removed_legacy_columns


def test_large_indexes_are_declared_non_atomic_and_reversible() -> None:
    module = migration("0006_add_concurrent_indexes")
    assert module.Migration.atomic is False
    assert {index.name for index in module.INDEXES} == {
        "mdm_entity_type_stat_code_idx",
        "mdm_entity_type_quality_idx",
        "mdm_entity_golden_idx",
        "mdm_entity_source_idx",
        "mdm_entity_deleted_upd_idx",
    }
    operation = module.Migration.operations[0]
    assert isinstance(operation, migrations.SeparateDatabaseAndState)
    run_python = operation.database_operations[0]
    assert isinstance(run_python, migrations.RunPython)
    assert run_python.code is module.create_indexes
    assert run_python.reverse_code is module.drop_indexes
    assert run_python.atomic is False


class RecordingSchemaEditor:
    def __init__(self, vendor: str) -> None:
        self.connection = SimpleNamespace(vendor=vendor)
        self.statements: list[str] = []

    @staticmethod
    def quote_name(value: str) -> str:
        return f'"{value}"'

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


def test_rls_migration_covers_every_tenant_table_is_postgresql_only_and_reversible() -> None:
    module = migration("0007_enable_domain_rls")
    assert set(module.TENANT_TABLES) == EXPECTED_DOMAIN_TABLES
    postgres = RecordingSchemaEditor("postgresql")
    sqlite = RecordingSchemaEditor("sqlite")

    module.enable_domain_rls(None, postgres)
    module.disable_domain_rls(None, postgres)
    module.enable_domain_rls(None, sqlite)
    module.disable_domain_rls(None, sqlite)

    assert sqlite.statements == []
    assert len(postgres.statements) == len(EXPECTED_DOMAIN_TABLES) * 4
    for table in EXPECTED_DOMAIN_TABLES:
        assert f"SELECT saraise_enable_rls('{table}'::REGCLASS);" in postgres.statements
        assert any(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY' in sql for sql in postgres.statements)
        assert any(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY' in sql for sql in postgres.statements)


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_postgresql_forward_reverse_forward_preserves_legacy_rows_and_enforces_rls() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("The lossless migration/RLS cycle requires PostgreSQL")

    executor = MigrationExecutor(connection)
    start = ("master_data_management", "0001_initial")
    end = ("master_data_management", "0007_enable_domain_rls")
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    executor.migrate([start])
    old_apps = executor.loader.project_state([start]).apps
    LegacyEntity = old_apps.get_model("master_data_management", "MasterDataEntity")
    own = LegacyEntity.objects.create(
        tenant_id=tenant_a,
        entity_type="customer",
        entity_code="CUST-A",
        entity_name="Customer A",
        data={"email": "a@example.test"},
        is_active=True,
    )
    archived = LegacyEntity.objects.create(
        tenant_id=tenant_b,
        entity_type="supplier",
        entity_code="SUP-B",
        entity_name="Supplier B",
        data={"email": "b@example.test"},
        is_active=False,
    )

    executor = MigrationExecutor(connection)
    executor.migrate([end])
    current_apps = executor.loader.project_state([end]).apps
    Entity = current_apps.get_model("master_data_management", "MasterDataEntity")
    EntityType = current_apps.get_model("master_data_management", "MasterEntityType")
    assert Entity.objects.count() == 2
    assert EntityType.objects.count() == 2
    migrated_own = Entity.objects.get(pk=own.pk)
    migrated_archived = Entity.objects.get(pk=archived.pk)
    assert migrated_own.entity_type.key == "customer"
    assert migrated_own.entity_code == "CUST-A"
    assert migrated_own.data == {"email": "a@example.test"}
    assert migrated_own.status == "active" and migrated_own.is_deleted is False
    assert migrated_archived.entity_type.key == "supplier"
    assert migrated_archived.status == "archived" and migrated_archived.is_deleted is True
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT relname, relrowsecurity, relforcerowsecurity
            FROM pg_class
            WHERE relname = ANY(%s)
            """,
            [sorted(EXPECTED_DOMAIN_TABLES)],
        )
        flags = {name: (enabled, forced) for name, enabled, forced in cursor.fetchall()}
    assert flags == {table: (True, True) for table in EXPECTED_DOMAIN_TABLES}

    executor = MigrationExecutor(connection)
    executor.migrate([start])
    reversed_apps = executor.loader.project_state([start]).apps
    ReversedEntity = reversed_apps.get_model("master_data_management", "MasterDataEntity")
    assert ReversedEntity.objects.get(pk=own.pk).entity_type == "customer"
    assert ReversedEntity.objects.get(pk=archived.pk).entity_type == "supplier"
    assert ReversedEntity.objects.get(pk=archived.pk).is_active is False

    executor = MigrationExecutor(connection)
    executor.migrate([end])
    final_apps = executor.loader.project_state([end]).apps
    FinalEntity = final_apps.get_model("master_data_management", "MasterDataEntity")
    assert FinalEntity.objects.count() == 2
    assert FinalEntity.objects.get(pk=own.pk).entity_type.key == "customer"
    assert FinalEntity.objects.get(pk=archived.pk).data == {"email": "b@example.test"}


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_postgresql_backfill_aborts_without_inventing_invalid_key_mapping() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("The migration failure contract requires PostgreSQL")

    expanded = ("master_data_management", "0002_add_entity_types_and_entity_evolution")
    backfilled = ("master_data_management", "0003_backfill_entity_types")
    executor = MigrationExecutor(connection)
    executor.migrate([expanded])
    apps = executor.loader.project_state([expanded]).apps
    Entity = apps.get_model("master_data_management", "MasterDataEntity")
    tenant = uuid.uuid4()
    Entity.objects.create(
        tenant_id=tenant,
        entity_type="Vendor",
        entity_code="LEGACY-INVALID",
        entity_name="Invalid legacy row",
        data={},
        is_active=True,
    )
    executor = MigrationExecutor(connection)
    with pytest.raises(RuntimeError, match="Invalid legacy MDM entity type keys"):
        executor.migrate([backfilled])
    Entity.objects.filter(tenant_id=tenant).delete()
    executor = MigrationExecutor(connection)
    executor.migrate([("master_data_management", "0007_enable_domain_rls")])
