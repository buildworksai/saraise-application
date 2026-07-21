"""Migration graph, legacy preservation, reversibility, and RLS evidence."""

from __future__ import annotations

import importlib

import pytest
from django.db import connection

DOMAIN_TABLES = {
    "customization_field_definitions",
    "customization_field_values",
    "customization_form_definitions",
    "customization_form_layout_versions",
    "customization_business_rules",
    "customization_business_rule_versions",
    "customization_rule_executions",
}
LEGACY_TABLE = "customization_framework_resources"


def test_domain_migration_creates_exact_tables_and_removes_only_legacy_state() -> None:
    module = importlib.import_module(
        "src.modules.customization_framework.migrations.0002_domain_models"
    )
    creates = [
        operation
        for operation in module.Migration.operations
        if operation.__class__.__name__ == "CreateModel"
    ]
    assert {operation.options["db_table"] for operation in creates} == DOMAIN_TABLES
    for operation in creates:
        tenant_field = dict(operation.fields)["tenant_id"]
        assert tenant_field.__class__.__name__ == "UUIDField"
        assert tenant_field.db_index is True

    detached = [
        operation
        for operation in module.Migration.operations
        if operation.__class__.__name__ == "SeparateDatabaseAndState"
    ]
    assert len(detached) == 1
    assert [item.__class__.__name__ for item in detached[0].database_operations] == [
        "RunPython"
    ]
    assert [item.__class__.__name__ for item in detached[0].state_operations] == [
        "DeleteModel"
    ]


def test_rls_migration_covers_every_tenant_table_with_typed_policies() -> None:
    module = importlib.import_module(
        "src.modules.customization_framework.migrations.0003_domain_rls"
    )
    assert set(module.TENANT_TABLES) == DOMAIN_TABLES
    operation = module.Migration.operations[0]
    assert operation.reverse_code is module.disable_domain_rls
    assert (
        "core",
        "0011_apply_typed_rls_to_notifications",
    ) in module.Migration.dependencies
    constants = set(module.enable_domain_rls.__code__.co_consts)
    assert any(
        "saraise_enable_rls" in value
        for value in constants
        if isinstance(value, str)
    )


@pytest.mark.django_db(transaction=True)
def test_current_schema_contains_domain_tables_and_preserved_legacy_table() -> None:
    tables = set(connection.introspection.table_names())
    assert DOMAIN_TABLES <= tables
    assert LEGACY_TABLE in tables


@pytest.mark.django_db(transaction=True)
def test_postgresql_catalog_has_forced_rls_and_bidirectional_policies() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL catalog assertions run in the PostgreSQL 17 gate")
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
    assert len(rows) == len(DOMAIN_TABLES)
    assert all(enabled and forced and using and checking for _, enabled, forced, using, checking in rows)
