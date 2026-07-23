from __future__ import annotations

import importlib
from unittest.mock import Mock


def test_migration_files_and_dependencies_are_staged():
    m2 = importlib.import_module("src.modules.sales_management.migrations.0002_complete_sales_domain")
    m3 = importlib.import_module("src.modules.sales_management.migrations.0003_backfill_sales_domain")
    m4 = importlib.import_module("src.modules.sales_management.migrations.0004_enforce_sales_constraints")
    m5 = importlib.import_module("src.modules.sales_management.migrations.0005_enable_sales_rls")
    assert m2.Migration.dependencies == [("sales_management", "0001_initial")]
    assert m3.Migration.dependencies == [("sales_management", "0002_complete_sales_domain")]
    assert m4.Migration.dependencies == [("sales_management", "0003_backfill_sales_domain")]
    assert ("sales_management", "0004_enforce_sales_constraints") in m5.Migration.dependencies


def test_rls_forward_and_reverse_cover_every_sales_table():
    migration = importlib.import_module("src.modules.sales_management.migrations.0005_enable_sales_rls")
    editor = Mock()
    editor.connection.vendor = "postgresql"
    migration.enable_sales_rls(Mock(), editor)
    forward = [call.args[0] for call in editor.execute.call_args_list]
    assert len(forward) == 10
    assert all("saraise_enable_rls" in sql and "::REGCLASS" in sql for sql in forward)
    editor.reset_mock()
    migration.disable_sales_rls(Mock(), editor)
    reverse = [call.args[0] for call in editor.execute.call_args_list]
    assert len(reverse) == 30
    assert all(any(table in sql for table in migration.TENANT_TABLES) for sql in reverse)
    assert sum("DROP POLICY" in sql for sql in reverse) == 10
    assert sum("DISABLE ROW LEVEL SECURITY" in sql for sql in reverse) == 10


def test_constraint_migration_declares_composite_tenant_guards():
    migration = importlib.import_module("src.modules.sales_management.migrations.0004_enforce_sales_constraints")
    editor = Mock()
    editor.connection.vendor = "postgresql"
    migration.install_composite_tenant_guards(Mock(), editor)
    sql = " ".join(call.args[0] for call in editor.execute.call_args_list)
    assert len(migration.COMPOSITE_FOREIGN_KEYS) == 10
    assert sql.count('FOREIGN KEY ("tenant_id"') == 10
    assert "sales_cfg_hist_parent_tenant_fk" in sql


def test_rls_is_noop_on_sqlite():
    migration = importlib.import_module("src.modules.sales_management.migrations.0005_enable_sales_rls")
    editor = Mock()
    editor.connection.vendor = "sqlite"
    migration.enable_sales_rls(Mock(), editor)
    editor.execute.assert_not_called()
