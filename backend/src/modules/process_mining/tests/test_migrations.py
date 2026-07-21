"""Migration reversibility, legacy preservation, and typed RLS contract."""
from importlib import import_module


def test_domain_migration_is_reversible_and_quarantines_legacy():
    migration = import_module("src.modules.process_mining.migrations.0002_process_mining_domain")
    assert callable(migration.quarantine_legacy) and callable(migration.restore_legacy_writes)
    assert len(migration.RELATIONSHIPS) == 7
    assert any(type(operation).__name__ == "SeparateDatabaseAndState" for operation in migration.Migration.operations)


def test_rls_covers_every_domain_table_with_typed_regclass():
    migration = import_module("src.modules.process_mining.migrations.0003_enable_process_mining_rls")
    class Connection: vendor = "postgresql"
    class Editor:
        connection = Connection()
        def __init__(self): self.statements = []
        def execute(self, value): self.statements.append(value)
    editor = Editor(); migration.enable_rls(None, editor)
    assert len(editor.statements) == 11
    assert all("saraise_enable_rls" in value and "::REGCLASS" in value for value in editor.statements)
    reverse = Editor(); migration.disable_rls(None, reverse)
    assert all("DISABLE ROW LEVEL SECURITY" in value for value in reverse.statements)
