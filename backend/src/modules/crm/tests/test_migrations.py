"""Forward/reverse safety, reconciliation, guards, and typed RLS evidence."""

import uuid
from importlib import import_module
from pathlib import Path

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from src.core.tenancy import tenant_context

M0005 = "0005_reconcile_crm_persistence"
M0008 = "0008_enable_crm_rls"


class PostgreSQLEditor:
    class Connection:
        vendor = "postgresql"

    connection = Connection()

    def __init__(self):
        self.statements = []

    def execute(self, statement):
        self.statements.append(str(statement))


def test_reconciliation_is_ordered_reversible_and_non_destructive():
    migration = import_module(f"src.modules.crm.migrations.{M0005}")
    operation_names = [type(operation).__name__ for operation in migration.Migration.operations]
    assert migration.Migration.dependencies == [("crm", "0004_alter_activity_owner_id_alter_opportunity_owner_id")]
    assert "RunPython" in operation_names
    assert not {"DeleteModel", "RemoveField"}.intersection(operation_names)
    assert callable(migration.reconcile_rows) and callable(migration.restore_rows)
    assert migration.MARKER == "__crm_0005_original__"


def test_actor_widening_has_a_lossless_rollback_compatibility_strategy():
    migration = import_module(f"src.modules.crm.migrations.{M0005}")
    editor = PostgreSQLEditor()
    migration.widen_actor_columns(None, editor)
    assert len(editor.statements) == 5
    assert all("varchar(255)" in statement for statement in editor.statements)
    reverse_editor = PostgreSQLEditor()
    migration.preserve_wide_actor_columns(None, reverse_editor)
    assert reverse_editor.statements == []


def test_constraints_follow_validation_and_composite_indexes_are_non_atomic():
    migration = import_module("src.modules.crm.migrations.0006_validate_constraints_and_indexes")
    names = [type(operation).__name__ for operation in migration.Migration.operations]
    assert migration.Migration.atomic is False
    assert names[0] == "RunPython"
    assert "AddConstraint" in names[1:]
    assert names[-1] == "SeparateDatabaseAndState"
    assert sum(len(indexes) for indexes in migration.INDEXES.values()) == 26


def test_reference_guards_are_reversible_and_cover_every_logical_relationship():
    migration = import_module("src.modules.crm.migrations.0007_same_tenant_reference_guards")
    sql = migration.INSTALL_GUARDS
    for trigger in (
        "crm_account_parent_guard",
        "crm_contact_account_guard",
        "crm_opportunity_reference_guard",
        "crm_activity_reference_guard",
        "crm_activity_immutable_guard",
    ):
        assert f"CREATE TRIGGER {trigger}" in sql
        assert f"DROP TRIGGER IF EXISTS {trigger}" in migration.REMOVE_GUARDS
    assert "tenant_id = NEW.tenant_id" in sql
    assert "hierarchy cannot exceed three nodes" in sql


def test_rls_uses_typed_regclass_and_reverses_all_five_tables():
    migration = import_module(f"src.modules.crm.migrations.{M0008}")
    editor = PostgreSQLEditor()
    migration.enable_rls(None, editor)
    assert len(editor.statements) == 5
    assert all("saraise_enable_rls" in statement and "::REGCLASS" in statement for statement in editor.statements)
    reverse = PostgreSQLEditor()
    migration.disable_rls(None, reverse)
    assert len(reverse.statements) == 5
    assert all("NO FORCE ROW LEVEL SECURITY" in statement for statement in reverse.statements)


@pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL RLS contract")
@pytest.mark.django_db(transaction=True)
def test_postgresql_rls_fails_closed_for_non_bypass_application_role():
    from src.modules.crm.models import Lead

    with connection.cursor() as cursor:
        cursor.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        is_superuser, bypasses_rls = cursor.fetchone()
        assert (
            not is_superuser and not bypasses_rls
        ), "CRM RLS tests must use a NOSUPERUSER NOBYPASSRLS application role"
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    with tenant_context(tenant_a):
        Lead.objects.create(tenant_id=tenant_a, last_name="Tenant A")
    with tenant_context(tenant_b):
        Lead.objects.create(tenant_id=tenant_b, last_name="Tenant B")
    with tenant_context(tenant_a), connection.cursor() as cursor:
        cursor.execute("SELECT tenant_id FROM crm_leads ORDER BY tenant_id")
        assert cursor.fetchall() == [(tenant_a,)]
    with connection.cursor() as cursor:
        cursor.execute("SELECT tenant_id FROM crm_leads")
        assert cursor.fetchall() == []


@pytest.mark.django_db(transaction=True)
def test_forward_reverse_forward_preserves_existing_rows_and_wide_actors():
    executor = MigrationExecutor(connection)
    old_target = [("crm", "0004_alter_activity_owner_id_alter_opportunity_owner_id")]
    new_target = [("crm", M0008)]
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps
    LegacyLead = old_apps.get_model("crm", "Lead")
    tenant_id = uuid.uuid4()
    first = LegacyLead.objects.create(
        tenant_id=tenant_id,
        last_name="First",
        email="Case@Example.test",
        grade="",
        created_by="legacy-actor",
    )
    second = LegacyLead.objects.create(
        tenant_id=tenant_id,
        last_name="Second",
        email="case@example.test",
        grade="",
        created_by="legacy-actor",
    )

    executor = MigrationExecutor(connection)
    executor.migrate(new_target)
    new_apps = executor.loader.project_state(new_target).apps
    CurrentLead = new_apps.get_model("crm", "Lead")
    with tenant_context(tenant_id):
        reconciled = list(CurrentLead.objects.filter(id__in=[first.id, second.id]).order_by("created_at"))
        assert len(reconciled) == 2
        assert [row.grade for row in reconciled] == ["D", "D"]
        assert sum(not row.is_deleted for row in reconciled) == 1
        wide_actor = "actor:" + "x" * 240
        CurrentLead.objects.filter(pk=first.pk).update(created_by=wide_actor)

    executor = MigrationExecutor(connection)
    executor.migrate(old_target)
    restored_apps = executor.loader.project_state(old_target).apps
    RestoredLead = restored_apps.get_model("crm", "Lead")
    restored = list(RestoredLead.objects.filter(id__in=[first.id, second.id]).order_by("created_at"))
    assert len(restored) == 2
    assert [row.email for row in restored] == ["Case@Example.test", "case@example.test"]
    assert all(not row.is_deleted for row in restored)
    assert RestoredLead.objects.get(pk=first.pk).created_by == wide_actor

    executor = MigrationExecutor(connection)
    executor.migrate(new_target)
    final_apps = executor.loader.project_state(new_target).apps
    FinalLead = final_apps.get_model("crm", "Lead")
    with tenant_context(tenant_id):
        assert FinalLead.objects.filter(id__in=[first.id, second.id]).count() == 2
        assert FinalLead.objects.get(pk=first.pk).created_by == wide_actor


def test_runbook_documents_locking_compatibility_and_rollback():
    readme = Path(__file__).parents[1] / "migrations" / "README.md"
    contents = readme.read_text()
    for phrase in (
        "Deployment order and compatibility window",
        "lock",
        "python manage.py migrate crm 0004",
        "forward/reverse/forward",
        "NOSUPERUSER",
        "varchar(255)",
    ):
        assert phrase in contents
