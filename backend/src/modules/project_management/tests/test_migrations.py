"""Migration contract checks that remain useful in the SQLite unit profile.

The deployment gate runs the same migration graph forward/reverse/forward on
PostgreSQL 17; these fast tests prove the RLS operation is vendor guarded,
complete, named, and reversible.
"""
import importlib
from types import SimpleNamespace


class Editor:
    def __init__(self, vendor):
        self.connection = SimpleNamespace(vendor=vendor)
        self.statements = []
    def execute(self, statement): self.statements.append(statement)


def test_rls_installs_and_removes_every_tenant_table():
    migration = importlib.import_module("src.modules.project_management.migrations.0003_apply_tenant_rls")
    editor = Editor("postgresql")
    migration.install_rls(None, editor)
    assert len(editor.statements) == len(migration.TABLES)
    assert all("saraise_enable_rls" in statement for statement in editor.statements)
    editor.statements.clear(); migration.remove_rls(None, editor)
    assert len(editor.statements) == len(migration.TABLES) * 3
    assert any("DISABLE ROW LEVEL SECURITY" in statement for statement in editor.statements)


def test_rls_is_noop_on_sqlite():
    migration = importlib.import_module("src.modules.project_management.migrations.0003_apply_tenant_rls")
    editor = Editor("sqlite"); migration.install_rls(None, editor); migration.remove_rls(None, editor)
    assert editor.statements == []
