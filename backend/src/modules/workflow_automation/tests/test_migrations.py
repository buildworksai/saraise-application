"""Reversible legacy-upgrade and PostgreSQL RLS migration evidence."""

from __future__ import annotations

import time
import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

APP = "workflow_automation"
LEGACY = (APP, "0001_initial")
LATEST = (APP, "0006_remove_unsafe_legacy_contract")


def _executor() -> MigrationExecutor:
    return MigrationExecutor(connection)


def test_forward_reverse_forward_preserves_existing_workflow() -> None:
    started = time.monotonic()
    executor = _executor()
    executor.migrate([LEGACY])
    legacy_apps = executor.loader.project_state([LEGACY]).apps
    LegacyWorkflow = legacy_apps.get_model(APP, "Workflow")
    LegacyStep = legacy_apps.get_model(APP, "WorkflowStep")
    LegacyInstance = legacy_apps.get_model(APP, "WorkflowInstance")

    tenant_id = uuid.uuid4()
    workflow_id = uuid.uuid4()
    workflow = LegacyWorkflow.objects.create(
        id=workflow_id,
        tenant_id=tenant_id,
        name="Legacy purchase approval",
        description="Must survive the v2 upgrade",
        status="draft",
        trigger_type="manual",
    )
    step = LegacyStep.objects.create(
        tenant_id=None if hasattr(LegacyStep, "tenant_id") else None,
        workflow=workflow,
        name="Approve",
        step_type="approval",
        order=1,
        config={},
    ) if hasattr(LegacyStep, "tenant_id") else LegacyStep.objects.create(
        workflow=workflow,
        name="Approve",
        step_type="approval",
        order=1,
        config={},
    )
    instance = LegacyInstance.objects.create(
        tenant_id=tenant_id,
        workflow=workflow,
        current_step=step,
        state="pending",
        context_data={},
    )

    executor = _executor()
    executor.migrate([LATEST])
    current_apps = executor.loader.project_state([LATEST]).apps
    CurrentWorkflow = current_apps.get_model(APP, "Workflow")
    CurrentStep = current_apps.get_model(APP, "WorkflowStep")
    CurrentInstance = current_apps.get_model(APP, "WorkflowInstance")
    upgraded = CurrentWorkflow.objects.get(id=workflow_id)
    upgraded_step = CurrentStep.objects.get(id=step.id)
    upgraded_instance = CurrentInstance.objects.get(id=instance.id)
    assert upgraded.name == "Legacy purchase approval"
    assert upgraded.key
    assert upgraded.version == 1
    assert upgraded_step.tenant_id == tenant_id
    assert upgraded_instance.workflow_version == 1
    assert upgraded_instance.idempotency_key
    assert isinstance(upgraded_instance.transition_history, list)

    executor = _executor()
    executor.migrate([LEGACY])
    reverse_apps = executor.loader.project_state([LEGACY]).apps
    assert reverse_apps.get_model(APP, "Workflow").objects.filter(id=workflow_id).exists()
    assert reverse_apps.get_model(APP, "WorkflowStep").objects.filter(id=step.id).exists()

    executor = _executor()
    executor.migrate([LATEST])
    final_apps = executor.loader.project_state([LATEST]).apps
    assert final_apps.get_model(APP, "Workflow").objects.filter(id=workflow_id).exists()
    assert time.monotonic() - started < 120


@pytest.mark.postgresql
def test_postgresql_forces_tenant_rls_on_every_evidence_table() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL-specific RLS verification")
    expected = {
        "workflow_definitions",
        "workflow_steps",
        "workflow_instances",
        "workflow_tasks",
        "workflow_step_executions",
    }
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            WHERE c.relname = ANY(%s)
            """,
            [list(expected)],
        )
        flags = {name: (enabled, forced) for name, enabled, forced in cursor.fetchall()}
        cursor.execute(
            """
            SELECT tablename, qual, with_check
            FROM pg_policies
            WHERE schemaname = current_schema() AND tablename = ANY(%s)
            """,
            [list(expected)],
        )
        policies = {name: f"{qual} {check}" for name, qual, check in cursor.fetchall()}
    assert set(flags) == expected
    assert all(enabled and forced for enabled, forced in flags.values())
    assert set(policies) == expected
    assert all("app.tenant_id" in policy and "tenant_id" in policy for policy in policies.values())
