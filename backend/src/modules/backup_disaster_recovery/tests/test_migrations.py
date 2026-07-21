"""Migration contract tests for additive schema creation and typed RLS."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

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
