"""Executable migration-governance checks that also run on the SQLite gate."""

from __future__ import annotations

from importlib import import_module


class PostgreSQLConnection:
    vendor = "postgresql"


class RecordingSchemaEditor:
    connection = PostgreSQLConnection()

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


def migration(number: str):
    return import_module(f"src.modules.inventory_management.migrations.{number}")


def test_all_additive_migration_operations_are_reversible() -> None:
    for name in (
        "0002_domain_foundation",
        "0003_legacy_backfill",
        "0004_constraints_and_indexes",
        "0005_inventory_rls",
    ):
        irreversible = [operation for operation in migration(name).Migration.operations if not operation.reversible]
        assert irreversible == [], f"{name} contains irreversible operations: {irreversible!r}"


def test_rls_forward_and_reverse_cover_only_inventory_tables() -> None:
    module = migration("0005_inventory_rls")
    assert ("core", "0011_apply_typed_rls_to_notifications") in module.Migration.dependencies
    forward = RecordingSchemaEditor()
    module.enable_inventory_rls(None, forward)
    assert len(forward.statements) == len(module.TENANT_TABLES)
    assert all("saraise_enable_rls" in statement for statement in forward.statements)
    for table in module.TENANT_TABLES:
        assert sum(table in statement for statement in forward.statements) == 1

    reverse = RecordingSchemaEditor()
    module.disable_inventory_rls(None, reverse)
    assert len(reverse.statements) == len(module.TENANT_TABLES) * 3
    assert all(
        any(table in statement for table in module.TENANT_TABLES)
        for statement in reverse.statements
    )
    assert not any("saraise_enable_rls" in statement for statement in reverse.statements)


def test_postgres_guards_have_symmetric_removal() -> None:
    module = migration("0004_constraints_and_indexes")
    forward = RecordingSchemaEditor()
    module.add_postgres_guards(None, forward)
    reverse = RecordingSchemaEditor()
    module.remove_postgres_guards(None, reverse)
    assert sum("ADD CONSTRAINT" in statement for statement in forward.statements) == len(module.RELATIONS)
    assert sum("DROP CONSTRAINT IF EXISTS" in statement for statement in reverse.statements) == len(module.RELATIONS)
    assert any("inventory_ledger_immutable" in statement for statement in forward.statements)
    assert any("inventory_config_revision_immutable" in statement for statement in reverse.statements)
