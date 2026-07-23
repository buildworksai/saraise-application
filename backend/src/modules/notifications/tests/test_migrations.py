from importlib import import_module


def test_rls_migration_covers_every_tenant_table_and_is_reversible():
    migration = import_module("src.modules.notifications.migrations.0002_notifications_rls")
    assert len(migration.TABLES) == 10
    assert all(name.startswith("notifications_") for name in migration.TABLES)
    operation = migration.Migration.operations[0]
    assert operation.code is migration.apply_security
    assert operation.reverse_code is migration.remove_security


def test_legacy_import_and_contract_migrations_have_reverse_paths():
    legacy = import_module("src.modules.notifications.migrations.0003_import_legacy_notifications")
    contract = import_module("src.modules.notifications.migrations.0004_module_contract_and_v1_adapter")
    assert legacy.Migration.operations[0].reverse_code is legacy.reverse_import
    assert contract.Migration.operations[0].reverse_code is contract.unregister_contract

