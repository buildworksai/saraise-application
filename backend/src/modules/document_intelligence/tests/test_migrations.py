"""Migration graph, legacy preservation, reversibility, and PostgreSQL RLS proof."""

from __future__ import annotations

import importlib
import json
import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

DOMAIN_TABLES = {
    "document_intelligence_extractions",
    "document_intelligence_extraction_pages",
    "document_intelligence_classifications",
    "document_intelligence_classification_scores",
    "document_intelligence_classifier_training_jobs",
    "document_intelligence_classifier_model_versions",
    "document_intelligence_extraction_templates",
    "document_intelligence_extraction_template_zones",
}
LEGACY_TABLE = "document_intelligence_resources"
LATEST = ("document_intelligence", "0005_register_domain_contract")
LEGACY = ("document_intelligence", "0001_initial")


def _tables() -> set[str]:
    return set(connection.introspection.table_names())


def _legacy_snapshot(identifier: str) -> tuple[object, ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT id, tenant_id, name, description, is_active, config, created_by "
            f'FROM "{LEGACY_TABLE}" WHERE id = %s',
            [identifier],
        )
        row = cursor.fetchone()
    assert row is not None
    return row


@pytest.mark.django_db(transaction=True)
def test_forward_reverse_forward_preserves_legacy_bytes_and_domain_schema() -> None:
    executor = MigrationExecutor(connection)
    executor.migrate([LEGACY])
    legacy_apps = executor.loader.project_state([LEGACY]).apps
    LegacyResource = legacy_apps.get_model("document_intelligence", "DocumentIntelligenceResource")
    identifier = str(uuid.uuid4())
    tenant = str(uuid.uuid4())
    actor = str(uuid.uuid4())
    LegacyResource.objects.create(
        id=identifier,
        tenant_id=tenant,
        name="Unclassified legacy record",
        description="Must remain untouched",
        is_active=True,
        config={"opaque": [1, "two", {"do_not_convert": True}]},
        created_by=actor,
    )
    original = _legacy_snapshot(identifier)

    executor = MigrationExecutor(connection)
    executor.migrate([LATEST])
    latest_state = executor.loader.project_state([LATEST]).apps
    assert "DocumentIntelligenceResource" not in {
        model.__name__ for model in latest_state.get_models() if model._meta.app_label == "document_intelligence"
    }
    assert DOMAIN_TABLES <= _tables()
    assert LEGACY_TABLE in _tables()
    assert _legacy_snapshot(identifier) == original

    executor = MigrationExecutor(connection)
    executor.migrate([LEGACY])
    assert DOMAIN_TABLES.isdisjoint(_tables())
    assert LEGACY_TABLE in _tables()
    assert _legacy_snapshot(identifier) == original

    executor = MigrationExecutor(connection)
    executor.migrate([LATEST])
    assert DOMAIN_TABLES <= _tables()
    assert _legacy_snapshot(identifier) == original


def test_detach_migration_uses_separate_database_and_state_without_drop() -> None:
    migration = importlib.import_module(
        "src.modules.document_intelligence.migrations.0002_detach_legacy_resource_state"
    ).Migration
    assert len(migration.operations) == 1
    operation = migration.operations[0]
    assert operation.__class__.__name__ == "SeparateDatabaseAndState"
    assert [item.__class__.__name__ for item in operation.state_operations] == ["DeleteModel"]
    assert all(item.__class__.__name__ != "DeleteModel" for item in operation.database_operations)


def test_domain_migration_declares_all_tables_uuid_tenants_and_real_reverse_operations() -> None:
    module = importlib.import_module("src.modules.document_intelligence.migrations.0003_domain_schema")
    creates = [operation for operation in module.Migration.operations if operation.__class__.__name__ == "CreateModel"]
    assert len(creates) == 8
    assert {operation.options["db_table"] for operation in creates} == DOMAIN_TABLES
    for operation in creates:
        tenant_field = dict(operation.fields)["tenant_id"]
        assert tenant_field.__class__.__name__ == "UUIDField"
        assert tenant_field.db_index is True

    registration = importlib.import_module("src.modules.document_intelligence.migrations.0005_register_domain_contract")
    operation = registration.Migration.operations[0]
    assert operation.reverse_code is not None
    assert registration.MANIFEST["metadata"]["api_version"] == "v2"
    assert len(registration.PERMISSIONS) == len(set(registration.PERMISSIONS))
    json.dumps(registration.MANIFEST, sort_keys=True)


def test_rls_migration_covers_exact_domain_tables_and_depends_on_typed_core_function() -> None:
    module = importlib.import_module("src.modules.document_intelligence.migrations.0004_domain_rls")
    assert {table for table, _policy in module.TABLE_POLICIES} == DOMAIN_TABLES
    assert ("core", "0011_apply_typed_rls_to_notifications") in module.Migration.dependencies
    assert len({policy for _table, policy in module.TABLE_POLICIES}) == 8


@pytest.mark.django_db(transaction=True)
def test_postgresql_rls_is_enabled_forced_and_has_using_with_check_policies() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL 17 RLS catalog assertions run in the PostgreSQL gate")
    with connection.cursor() as cursor:
        cursor.execute("SHOW server_version_num")
        assert int(cursor.fetchone()[0]) >= 170000
        cursor.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   p.polqual IS NOT NULL, p.polwithcheck IS NOT NULL
              FROM pg_class c
              JOIN pg_policy p ON p.polrelid = c.oid
             WHERE c.relname = ANY(%s)
            """,
            [list(DOMAIN_TABLES)],
        )
        rows = cursor.fetchall()
    assert len(rows) == 8
    assert all(enabled and forced and using and checking for _, enabled, forced, using, checking in rows)
