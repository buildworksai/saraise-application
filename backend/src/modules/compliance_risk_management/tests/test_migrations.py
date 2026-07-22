"""Forward/reverse preservation and module-owned RLS migration proof."""

from __future__ import annotations

import importlib
import uuid
from types import SimpleNamespace

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

DOMAIN_MIGRATION = ("compliance_risk_management", "0002_domain_completion")
LEGACY_MIGRATION = ("compliance_risk_management", "0001_initial")
RLS_MIGRATION = ("compliance_risk_management", "0003_rls_policies")


@pytest.mark.django_db(transaction=True)
def test_legacy_risk_survives_forward_reverse_and_forward_again() -> None:
    executor = MigrationExecutor(connection)
    executor.migrate([LEGACY_MIGRATION])
    legacy_apps = executor.loader.project_state([LEGACY_MIGRATION]).apps
    LegacyRisk = legacy_apps.get_model("compliance_risk_management", "ComplianceRisk")
    tenant_id = uuid.uuid4()
    risk_id = uuid.uuid4()
    LegacyRisk.objects.create(
        id=risk_id,
        tenant_id=tenant_id,
        risk_code=" legacy-001 ",
        risk_name="Legacy risk",
        description="Preserved description",
        risk_level="high",
        status="mitigated",
        mitigation_plan="Preserved mitigation",
    )

    executor = MigrationExecutor(connection)
    executor.migrate([DOMAIN_MIGRATION])
    domain_apps = executor.loader.project_state([DOMAIN_MIGRATION]).apps
    RiskAssessment = domain_apps.get_model("compliance_risk_management", "RiskAssessment")
    migrated = RiskAssessment.objects.get(pk=risk_id)
    assert migrated.tenant_id == tenant_id
    assert migrated.risk_code == "LEGACY-001"
    assert migrated.name == "Legacy risk"
    assert migrated.description == "Preserved description"
    assert migrated.mitigation_strategy == "Preserved mitigation"
    assert migrated.status == "mitigating"
    assert migrated.risk_level == "high"
    assert migrated.created_by_id == uuid.UUID("00000000-0000-0000-0000-00000000c0de")

    executor = MigrationExecutor(connection)
    executor.migrate([LEGACY_MIGRATION])
    reversed_apps = executor.loader.project_state([LEGACY_MIGRATION]).apps
    restored = reversed_apps.get_model("compliance_risk_management", "ComplianceRisk").objects.get(pk=risk_id)
    assert restored.risk_name == "Legacy risk"
    assert restored.status == "mitigated"
    assert restored.mitigation_plan == "Preserved mitigation"

    executor = MigrationExecutor(connection)
    executor.migrate([RLS_MIGRATION])
    final_apps = executor.loader.project_state([RLS_MIGRATION]).apps
    remigrated = final_apps.get_model("compliance_risk_management", "RiskAssessment").objects.get(pk=risk_id)
    assert remigrated.risk_code == "LEGACY-001"
    assert remigrated.status == "mitigating"


@pytest.mark.django_db(transaction=True)
def test_domain_reversal_guard_rejects_dependent_records() -> None:
    executor = MigrationExecutor(connection)
    executor.migrate([DOMAIN_MIGRATION])
    apps = executor.loader.project_state([DOMAIN_MIGRATION]).apps
    Requirement = apps.get_model("compliance_risk_management", "ComplianceRequirement")
    Requirement.objects.create(
        tenant_id=uuid.uuid4(),
        created_by_id=uuid.uuid4(),
        regulation_code="REG",
        requirement_code="REQ-1",
        regulation_name="Regulation",
        title="Requirement",
        description="Required control",
        applicability="mandatory",
        owner_id=uuid.uuid4(),
    )
    migration = importlib.import_module("src.modules.compliance_risk_management.migrations.0002_domain_completion")

    with pytest.raises(RuntimeError, match="Cannot reverse.*ComplianceRequirement"):
        migration.guard_domain_reversal(apps, None)

    Requirement.objects.all().delete()
    MigrationExecutor(connection).migrate([RLS_MIGRATION])


def test_rls_migration_targets_every_module_tenant_table_and_reverses_exactly() -> None:
    migration = importlib.import_module("src.modules.compliance_risk_management.migrations.0003_rls_policies")

    class Recorder:
        connection = SimpleNamespace(vendor="postgresql")

        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement: str) -> None:
            self.statements.append(statement)

    forward = Recorder()
    migration.install_rls(None, forward)
    assert forward.statements == [
        f"SELECT saraise_enable_rls('{table}'::REGCLASS);" for table in migration.TENANT_TABLES
    ]

    reverse = Recorder()
    migration.remove_rls(None, reverse)
    assert len(reverse.statements) == len(migration.TENANT_TABLES) * 3
    for table in migration.TENANT_TABLES:
        assert f'DROP POLICY IF EXISTS "tenant_isolation_{table}" ON "{table}";' in reverse.statements
        assert f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;' in reverse.statements
        assert f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;' in reverse.statements


@pytest.mark.django_db
def test_postgresql_catalog_has_forced_rls_for_every_module_table() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL 17 catalog proof runs in the PostgreSQL migration gate")
    migration = importlib.import_module("src.modules.compliance_risk_management.migrations.0003_rls_policies")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   EXISTS (
                       SELECT 1 FROM pg_policies p
                       WHERE p.schemaname = current_schema() AND p.tablename = c.relname
                   )
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema() AND c.relname = ANY(%s)
            """,
            [list(migration.TENANT_TABLES)],
        )
        rows = cursor.fetchall()
    assert {name for name, enabled, forced, policy in rows if enabled and forced and policy} == set(
        migration.TENANT_TABLES
    )
