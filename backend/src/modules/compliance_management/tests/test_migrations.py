from __future__ import annotations

import importlib
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


MIGRATION_0001 = ("compliance_management", "0001_initial")
MIGRATION_0005 = ("compliance_management", "0005_enforce_append_only_records")


@pytest.mark.django_db(transaction=True)
def test_forward_reverse_forward_preserves_legacy_data():
    executor = MigrationExecutor(connection)
    try:
        executor.migrate([MIGRATION_0001])
        legacy_apps = executor.loader.project_state([MIGRATION_0001]).apps
        Policy = legacy_apps.get_model("compliance_management", "CompliancePolicy")
        Requirement = legacy_apps.get_model("compliance_management", "ComplianceRequirement")
        tenant_id = uuid.uuid4()
        policy_id = uuid.uuid4()
        requirement_id = uuid.uuid4()
        Policy.objects.create(
            id=policy_id,
            tenant_id=tenant_id,
            policy_code="LEG-001",
            policy_name="Legacy Policy",
            regulation_type=" ISO 27001 ",
            description="Original policy body",
            effective_date=date(2025, 1, 1),
            is_active=False,
        )
        Requirement.objects.create(
            id=requirement_id,
            tenant_id=tenant_id,
            policy_id=policy_id,
            requirement_code="A.1",
            requirement_name="Legacy Requirement",
            description="Original requirement",
            status="non_compliant",
        )

        executor = MigrationExecutor(connection)
        executor.migrate([MIGRATION_0005])
        current_apps = executor.loader.project_state([MIGRATION_0005]).apps
        CurrentPolicy = current_apps.get_model("compliance_management", "CompliancePolicy")
        Version = current_apps.get_model("compliance_management", "CompliancePolicyVersion")
        assert CurrentPolicy.objects.get(id=policy_id).title == "Legacy Policy"
        assert Version.objects.get(policy_id=policy_id).content == "Original policy body"

        executor = MigrationExecutor(connection)
        executor.migrate([MIGRATION_0001])
        restored_apps = executor.loader.project_state([MIGRATION_0001]).apps
        RestoredPolicy = restored_apps.get_model("compliance_management", "CompliancePolicy")
        RestoredRequirement = restored_apps.get_model("compliance_management", "ComplianceRequirement")
        restored_policy = RestoredPolicy.objects.get(id=policy_id)
        restored_requirement = RestoredRequirement.objects.get(id=requirement_id)
        assert restored_policy.regulation_type == " ISO 27001 "
        assert restored_policy.description == "Original policy body"
        assert restored_requirement.policy_id == policy_id
        assert restored_requirement.status == "non_compliant"

        executor = MigrationExecutor(connection)
        executor.migrate([MIGRATION_0005])
        assert "compliance_activity" in connection.introspection.table_names()
    finally:
        # A failing assertion must never leave the shared test schema historical.
        MigrationExecutor(connection).migrate([MIGRATION_0005])


class RecordingSchemaEditor:
    def __init__(self, vendor):
        self.connection = SimpleNamespace(vendor=vendor)
        self.statements = []

    def execute(self, sql):
        self.statements.append(" ".join(sql.split()))

    @staticmethod
    def quote_name(value):
        return f'"{value}"'


def test_rls_sql_and_sqlite_safe_conditionals():
    migration = importlib.import_module("src.modules.compliance_management.migrations.0004_enforce_compliance_rls")
    sqlite = RecordingSchemaEditor("sqlite")
    migration.enable_rls(None, sqlite)
    migration.disable_rls(None, sqlite)
    assert sqlite.statements == []

    postgres = RecordingSchemaEditor("postgresql")
    migration.enable_rls(None, postgres)
    assert len(postgres.statements) == len(migration.COMPLIANCE_TABLES)
    assert all("saraise_enable_rls" in statement for statement in postgres.statements)
    migration.disable_rls(None, postgres)
    assert any("DISABLE ROW LEVEL SECURITY" in statement for statement in postgres.statements)


def test_append_only_trigger_sql_and_reverse_are_complete():
    migration = importlib.import_module("src.modules.compliance_management.migrations.0005_enforce_append_only_records")
    sqlite = RecordingSchemaEditor("sqlite")
    migration.install_triggers(None, sqlite)
    migration.remove_triggers(None, sqlite)
    assert sqlite.statements == []

    postgres = RecordingSchemaEditor("postgresql")
    migration.install_triggers(None, postgres)
    sql = " ".join(postgres.statements)
    assert "BEFORE UPDATE OR DELETE" in sql
    assert all(table in sql for table in migration.APPEND_ONLY_TABLES)
    migration.remove_triggers(None, postgres)
    assert any("DROP FUNCTION IF EXISTS" in statement for statement in postgres.statements)


def test_ambiguous_reverse_is_rejected_before_data_loss():
    migration = importlib.import_module("src.modules.compliance_management.migrations.0003_migrate_legacy_compliance_data")

    class Manager:
        def order_by(self, *fields):
            del fields
            return [SimpleNamespace(id=uuid.uuid4(), transition_history=[])]

    policy_model = SimpleNamespace(objects=Manager())
    unused_model = SimpleNamespace(objects=Manager())

    class Apps:
        @staticmethod
        def get_model(app_label, model_name):
            del app_label
            return policy_model if model_name == "CompliancePolicy" else unused_model

    with pytest.raises(RuntimeError, match="provenance is ambiguous"):
        migration.backwards(Apps(), object())
