"""Expand/contract, constraint, and typed-RLS migration evidence."""

from importlib import import_module
from pathlib import Path
from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


M0001 = "0001_initial"
M0002 = "0002_expand_and_backfill"
M0003 = "0003_constraints_and_indexes"
M0004 = "0004_enable_rls"


class PostgreSQLEditor:
    class Connection:
        vendor = "postgresql"

    connection = Connection()

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: object) -> None:
        self.statements.append(str(statement))

    @staticmethod
    def quote_name(value: str) -> str:
        return f'"{value}"'


def test_expand_preflight_precedes_fk_contract_and_never_invents_leave_allocation() -> None:
    migration = import_module(f"src.modules.human_resources.migrations.{M0002}")
    operations = migration.Migration.operations
    run_python_index = next(index for index, item in enumerate(operations) if type(item).__name__ == "RunPython")
    leave_balance_index = next(
        index
        for index, item in enumerate(operations)
        if type(item).__name__ == "CreateModel" and item.name == "LeaveBalance"
    )
    nonnull_balance_index = max(
        index
        for index, item in enumerate(operations)
        if type(item).__name__ == "AlterField" and item.model_name == "leaverequest"
    )
    assert leave_balance_index < run_python_index < nonnull_balance_index
    source = Path(migration.__file__).read_text()
    assert "explicit leave-allocation input" in source
    assert "LeaveBalance.objects.create" not in source
    assert "cross-tenant" in source


def test_contract_migration_declares_every_required_constraint_and_index() -> None:
    migration = import_module(f"src.modules.human_resources.migrations.{M0003}")
    names = {
        getattr(operation, "constraint", None).name
        for operation in migration.Migration.operations
        if getattr(operation, "constraint", None) is not None
    }
    assert {
        "hr_dept_live_code_uniq",
        "hr_dept_not_self_parent_ck",
        "hr_emp_live_number_uniq",
        "hr_emp_live_email_ci_uniq",
        "hr_emp_active_sync_ck",
        "hr_att_live_employee_date_uq",
        "hr_att_hours_range_ck",
        "hr_bal_live_period_uniq",
        "hr_bal_capacity_ck",
        "hr_req_date_order_ck",
        "hr_req_approved_meta_ck",
        "hr_req_rejected_meta_ck",
        "hr_req_cancelled_meta_ck",
    }.issubset(names)
    indexes = {
        operation.index.name
        for operation in migration.Migration.operations
        if getattr(operation, "index", None) is not None
    }
    assert len(indexes) == 22
    assert {"hr_dept_t_parent_idx", "hr_emp_t_mgr_status_idx", "hr_req_t_type_dates_idx"}.issubset(indexes)


def test_rls_uses_typed_regclass_and_reverses_all_tables_in_reverse_order() -> None:
    migration = import_module(f"src.modules.human_resources.migrations.{M0004}")
    assert migration.Migration.dependencies == [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("human_resources", M0003),
    ]
    forward = PostgreSQLEditor()
    migration.enable_hr_rls(None, forward)
    assert len(forward.statements) == 5
    assert all("saraise_enable_rls" in item and "::REGCLASS" in item for item in forward.statements)

    reverse = PostgreSQLEditor()
    migration.disable_hr_rls(None, reverse)
    assert len(reverse.statements) == 15
    first_reverse_table = migration.TENANT_TABLES[-1]
    assert first_reverse_table in reverse.statements[0]
    assert "DROP POLICY IF EXISTS" in reverse.statements[0]
    assert "NO FORCE ROW LEVEL SECURITY" in reverse.statements[1]
    assert "DISABLE ROW LEVEL SECURITY" in reverse.statements[2]


@pytest.mark.django_db(transaction=True)
def test_forward_reverse_forward_preserves_legacy_employee_rows() -> None:
    old_target = [("human_resources", M0001)]
    new_target = [("human_resources", M0004)]
    executor = MigrationExecutor(connection)
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps
    LegacyEmployee = old_apps.get_model("human_resources", "Employee")
    tenant_id = uuid4()
    employee = LegacyEmployee.objects.create(
        tenant_id=tenant_id,
        employee_number="LEGACY-1",
        first_name="Legacy",
        last_name="Employee",
        email="legacy@example.test",
        hire_date="2024-01-01",
        employment_type="full-time",
        is_active=True,
    )

    executor = MigrationExecutor(connection)
    executor.migrate(new_target)
    current_apps = executor.loader.project_state(new_target).apps
    CurrentEmployee = current_apps.get_model("human_resources", "Employee")
    current = CurrentEmployee.objects.get(pk=employee.pk)
    assert current.employment_type == "full_time"
    assert current.employment_status == "active"
    assert current.created_by == ""

    executor = MigrationExecutor(connection)
    executor.migrate(old_target)
    restored_apps = executor.loader.project_state(old_target).apps
    RestoredEmployee = restored_apps.get_model("human_resources", "Employee")
    restored = RestoredEmployee.objects.get(pk=employee.pk)
    assert restored.employee_number == "LEGACY-1"
    assert restored.employment_type == "full_time"
    assert restored.is_active is True

    executor = MigrationExecutor(connection)
    executor.migrate(new_target)
    final_apps = executor.loader.project_state(new_target).apps
    FinalEmployee = final_apps.get_model("human_resources", "Employee")
    assert FinalEmployee.objects.filter(pk=employee.pk).exists()


@pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL RLS contract")
@pytest.mark.django_db(transaction=True)
def test_postgresql_rls_requires_non_bypass_role_and_forces_all_hr_tables() -> None:
    migration = import_module(f"src.modules.human_resources.migrations.{M0004}")
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        superuser, bypasses = cursor.fetchone()
        assert not superuser and not bypasses
        cursor.execute(
            """SELECT relname, relrowsecurity, relforcerowsecurity
               FROM pg_class WHERE relname = ANY(%s)""",
            [list(migration.TENANT_TABLES)],
        )
        flags = {name: (enabled, forced) for name, enabled, forced in cursor.fetchall()}
        assert set(flags) == set(migration.TENANT_TABLES)
        assert all(enabled and forced for enabled, forced in flags.values())


def test_migration_runbook_documents_destructive_v2_export_before_rollback() -> None:
    runbook = Path(__file__).parents[1] / "migrations" / "README.md"
    content = runbook.read_text()
    for phrase in (
        "explicit allocation",
        "forward/reverse/forward",
        "PostgreSQL 17",
        "NOSUPERUSER",
        "NOBYPASSRLS",
        "export",
        "transition",
    ):
        assert phrase.lower() in content.lower()

