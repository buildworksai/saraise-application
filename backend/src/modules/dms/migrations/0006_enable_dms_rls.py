"""Install database-enforced tenant guards on canonical DMS tables.

PostgreSQL is the only supported runtime database and receives FORCE RLS.
The explicitly selected in-memory SQLite test backend cannot implement
row-level read policies, so it receives database triggers that prevent tenant
ownership reassignment and cross-tenant relationships.  The API/service
isolation suite then proves row visibility and mutation denial on that test
backend.  Every other backend fails closed instead of silently running without
an isolation primitive.
"""

from __future__ import annotations

import os

from django.db import migrations
from django.db.utils import NotSupportedError

TENANT_TABLES = (
    "dms_folders",
    "dms_documents",
    "dms_document_versions",
    "dms_document_permissions",
    "dms_document_shares",
)

SQLITE_TEST_ENVIRONMENT = "DJANGO_USE_SQLITE_FOR_TESTS"

SQLITE_RELATIONSHIPS = (
    ("dms_folders", "parent_id", "dms_folders", None),
    ("dms_documents", "folder_id", "dms_folders", None),
    ("dms_documents", "current_version_id", "dms_document_versions", None),
    ("dms_document_versions", "document_id", "dms_documents", None),
    ("dms_document_versions", "source_version_id", "dms_document_versions", None),
    ("dms_document_permissions", "document_id", "dms_documents", None),
    ("dms_document_shares", "document_id", "dms_documents", None),
    ("dms_document_shares", "version_id", "dms_document_versions", "document_id"),
)


def _backend(connection) -> str:
    """Return the enforced isolation implementation or reject the backend."""

    if connection.vendor == "postgresql":
        return "postgresql"
    if connection.vendor == "sqlite" and os.getenv(SQLITE_TEST_ENVIRONMENT) == "1":
        database_name = str(getattr(connection, "settings_dict", {}).get("NAME", ""))
        if database_name == ":memory:" or database_name.startswith("file:memorydb_"):
            return "sqlite"
    raise NotSupportedError(
        "DMS tenant isolation requires PostgreSQL; SQLite is permitted only "
        "for the explicitly configured in-memory test database."
    )


def _sqlite_trigger_name(table_name: str, suffix: str) -> str:
    return f"{table_name}_{suffix}"


def _install_sqlite_guards(schema_editor) -> None:
    """Install ownership and same-tenant relationship enforcement for tests."""

    for table_name in TENANT_TABLES:
        trigger_name = _sqlite_trigger_name(table_name, "tenant_id_immutable")
        schema_editor.execute(f"""
            CREATE TRIGGER {trigger_name}
            BEFORE UPDATE OF tenant_id ON {table_name}
            FOR EACH ROW
            WHEN NEW.tenant_id <> OLD.tenant_id
            BEGIN
                SELECT RAISE(ABORT, 'DMS tenant ownership is immutable');
            END
            """)

    for table_name, column_name, related_table, related_document_column in SQLITE_RELATIONSHIPS:
        suffix = f"{column_name}_same_tenant"
        related_document_check = (
            f" AND related.{related_document_column} = NEW.document_id" if related_document_column else ""
        )
        predicate = (
            f"NEW.{column_name} IS NOT NULL AND NOT EXISTS ("
            f"SELECT 1 FROM {related_table} AS related "
            f"WHERE related.id = NEW.{column_name} "
            f"AND related.tenant_id = NEW.tenant_id{related_document_check})"
        )
        operations = (
            ("insert", "BEFORE INSERT"),
            ("update", f"BEFORE UPDATE OF {column_name}, tenant_id"),
        )
        for operation, timing in operations:
            trigger_name = _sqlite_trigger_name(table_name, f"{suffix}_{operation}")
            schema_editor.execute(f"""
                CREATE TRIGGER {trigger_name}
                {timing} ON {table_name}
                FOR EACH ROW
                WHEN {predicate}
                BEGIN
                    SELECT RAISE(ABORT, 'DMS relationship crosses tenant boundary');
                END
                """)


def _remove_sqlite_guards(schema_editor) -> None:
    for table_name, column_name, _related_table, _related_document_column in reversed(SQLITE_RELATIONSHIPS):
        suffix = f"{column_name}_same_tenant"
        for operation in ("update", "insert"):
            trigger_name = _sqlite_trigger_name(table_name, f"{suffix}_{operation}")
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {trigger_name};")
    for table_name in reversed(TENANT_TABLES):
        trigger_name = _sqlite_trigger_name(table_name, "tenant_id_immutable")
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {trigger_name};")


def enable_dms_rls(apps, schema_editor) -> None:
    del apps
    backend = _backend(schema_editor.connection)
    if backend == "sqlite":
        _install_sqlite_guards(schema_editor)
        return
    for table_name in TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table_name}'::REGCLASS);")


def disable_dms_rls(apps, schema_editor) -> None:
    del apps
    backend = _backend(schema_editor.connection)
    if backend == "sqlite":
        _remove_sqlite_guards(schema_editor)
        return
    for table_name in reversed(TENANT_TABLES):
        quoted_table = schema_editor.quote_name(table_name)
        quoted_policy = schema_editor.quote_name(f"tenant_isolation_{table_name}")
        schema_editor.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table};")
        schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("dms", "0005_swap_v2_tables"),
    ]

    operations = [migrations.RunPython(enable_dms_rls, disable_dms_rls)]
