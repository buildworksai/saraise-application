"""Migration contract tests for additive schema creation and typed RLS."""

from __future__ import annotations

import importlib
import re
import uuid
from types import SimpleNamespace

import pytest
from django.db import migrations

EXPECTED_TABLES = {
    "bdr_recovery_points",
    "bdr_restore_runs",
    "bdr_runbooks",
    "bdr_runbook_steps",
    "bdr_exercises",
    "bdr_step_executions",
}


def test_domain_migration_creates_six_tables_and_preserves_legacy_table() -> None:
    migration = importlib.import_module("src.modules.backup_disaster_recovery.migrations.0002_domain_models").Migration
    creates = [operation for operation in migration.operations if isinstance(operation, migrations.CreateModel)]
    assert {operation.options["db_table"] for operation in creates} == EXPECTED_TABLES

    state_only = next(
        operation for operation in migration.operations if isinstance(operation, migrations.SeparateDatabaseAndState)
    )
    assert state_only.database_operations == []
    assert isinstance(state_only.state_operations[0], migrations.DeleteModel)
    assert state_only.state_operations[0].name == "BackupDisasterRecoveryResource"


class _SchemaEditor:
    def __init__(self, vendor: str) -> None:
        self.connection = SimpleNamespace(vendor=vendor)
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


def test_rls_migration_is_postgresql_only_complete_and_reversible() -> None:
    module = importlib.import_module("src.modules.backup_disaster_recovery.migrations.0003_enable_rls")
    postgres = _SchemaEditor("postgresql")
    sqlite = _SchemaEditor("sqlite")

    module.enable_rls(None, postgres)
    module.disable_rls(None, postgres)
    module.enable_rls(None, sqlite)
    module.disable_rls(None, sqlite)

    assert len(postgres.statements) == len(EXPECTED_TABLES) * 2
    assert sqlite.statements == []
    for table in EXPECTED_TABLES:
        assert any(f"saraise_enable_rls('{table}'::REGCLASS)" in sql for sql in postgres.statements)
        assert any(f"DROP POLICY IF EXISTS tenant_isolation_{table}" in sql for sql in postgres.statements)
        assert any(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY" in sql for sql in postgres.statements)


class _LegacyCursor:
    def __init__(self, rows: list[tuple[object, object, object]]) -> None:
        self.rows = rows
        self.statements: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    def execute(self, statement: str) -> None:
        self.statements.append(statement)

    def fetchall(self) -> list[tuple[object, object, object]]:
        return self.rows


class _LegacySchemaEditor:
    def __init__(
        self,
        vendor: str,
        tables: set[str],
        rows: list[tuple[object, object, object]] | None = None,
    ) -> None:
        self.tables = tables
        self.cursor = _LegacyCursor(rows or [])
        self.connection = SimpleNamespace(
            vendor=vendor,
            introspection=SimpleNamespace(table_names=lambda: list(self.tables)),
            cursor=lambda: self.cursor,
        )
        self.statements: list[str] = []

    def quote_name(self, value: str) -> str:
        return f'"{value}"'

    def execute(self, statement: str) -> None:
        self.statements.append(statement)
        if " RENAME TO " in statement:
            source, target = re.findall(r'"([^"]+)"', statement)[:2]
            self.tables.discard(source)
            self.tables.add(target)


def test_compliance_migration_validates_legacy_uuid_data_before_mutation() -> None:
    module = importlib.import_module("src.modules.backup_disaster_recovery.migrations.0004_compliance_configuration")
    valid = str(uuid.uuid4())
    valid_editor = _LegacySchemaEditor(
        "postgresql",
        {module.LEGACY_TABLE},
        [(valid, valid, valid)],
    )
    module.validate_legacy_ids(None, valid_editor)
    assert valid_editor.cursor.statements

    invalid_editor = _LegacySchemaEditor(
        "postgresql",
        {module.LEGACY_TABLE},
        [("not-a-uuid", valid, valid)],
    )
    with pytest.raises(RuntimeError, match="invalid UUID"):
        module.validate_legacy_ids(None, invalid_editor)
    assert invalid_editor.statements == []


@pytest.mark.parametrize("vendor", ["postgresql", "sqlite"])
def test_compliance_migration_archives_and_restores_legacy_table(vendor: str) -> None:
    module = importlib.import_module("src.modules.backup_disaster_recovery.migrations.0004_compliance_configuration")
    editor = _LegacySchemaEditor(vendor, {module.LEGACY_TABLE})

    module.archive_legacy_table(None, editor)
    assert module.LEGACY_TABLE not in editor.tables
    assert module.LEGACY_ARCHIVE_TABLE in editor.tables
    assert any("RENAME TO" in statement for statement in editor.statements)
    if vendor == "postgresql":
        assert sum("TYPE uuid" in statement for statement in editor.statements) == 3

    module.restore_legacy_table(None, editor)
    assert module.LEGACY_TABLE in editor.tables
    assert module.LEGACY_ARCHIVE_TABLE not in editor.tables
    if vendor == "postgresql":
        assert sum("TYPE varchar(36)" in statement for statement in editor.statements) == 3


def test_compliance_migration_adds_tenant_uuid_models_and_is_reversible() -> None:
    module = importlib.import_module("src.modules.backup_disaster_recovery.migrations.0004_compliance_configuration")
    creates = [operation for operation in module.Migration.operations if isinstance(operation, migrations.CreateModel)]
    assert {operation.options["db_table"] for operation in creates} == {
        "bdr_configurations",
        "bdr_configuration_versions",
        "bdr_recovery_point_evidence",
    }
    for operation in creates:
        tenant_field = dict(operation.fields)["tenant_id"]
        assert tenant_field.get_internal_type() == "UUIDField"
        assert tenant_field.db_index is True
    python_operations = [
        operation for operation in module.Migration.operations if isinstance(operation, migrations.RunPython)
    ]
    assert python_operations
    assert all(operation.reversible for operation in python_operations)
