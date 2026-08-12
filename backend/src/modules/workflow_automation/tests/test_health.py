"""Sanitized, fail-closed readiness tests."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent, OutboxStatus

from .. import health
from ..models import WorkflowStep
from ..services import WorkflowConfigurationService
from .test_services import action_payload, publish


def _set_checks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    database: bool = True,
    jobs: bool = True,
    outbox: bool = True,
    extensions: bool = True,
) -> None:
    monkeypatch.setattr(health, "_database_ready", lambda tenant_id: database)
    monkeypatch.setattr(health, "_handlers_registered", lambda: jobs)
    monkeypatch.setattr(health, "_outbox_fresh", lambda tenant_id: outbox)
    monkeypatch.setattr(health, "_required_extensions_ready", lambda tenant_id: extensions)


def test_readiness_is_healthy_only_when_every_required_capability_is_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_checks(monkeypatch)
    result = health.module_readiness(uuid.uuid4())
    assert result.healthy is True
    assert set(result.details) == {
        "database_rls",
        "async_handlers",
        "outbox_worker",
        "notifications",
        "required_extensions",
    }


@pytest.mark.parametrize("failed", ["database", "jobs", "outbox", "extensions"])
def test_each_required_dependency_fails_readiness(monkeypatch: pytest.MonkeyPatch, failed: str) -> None:
    values = {"database": True, "jobs": True, "outbox": True, "extensions": True}
    values[failed] = False
    _set_checks(monkeypatch, **values)
    payload, status_code = health.sanitized_health_payload(uuid.uuid4())
    assert status_code == 503
    assert payload["status"] == "not_ready"


def test_health_payload_never_leaks_tenant_counts_urls_or_exception_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_checks(monkeypatch, database=False)
    payload, _ = health.sanitized_health_payload(uuid.uuid4())
    rendered = repr(payload).lower()
    for forbidden in ("tenant_id", "row_count", "exception", "password", "http://", "https://"):
        assert forbidden not in rendered


def test_module_health_registration_is_idempotent() -> None:
    health.register_module_health()
    health.register_module_health()


def test_readiness_treats_invalid_tenant_identifier_as_process_level_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []

    def database_ready(tenant_id):
        seen.append(tenant_id)
        return True

    monkeypatch.setattr(health, "_database_ready", database_ready)
    monkeypatch.setattr(health, "_handlers_registered", lambda: True)
    monkeypatch.setattr(health, "_outbox_fresh", lambda tenant_id: tenant_id is None)
    monkeypatch.setattr(health, "_required_extensions_ready", lambda tenant_id: True)

    result = health.module_readiness("not-a-uuid")
    assert result.healthy is True
    assert seen == [None]


def test_outbox_readiness_uses_tenant_configured_staleness(tenant_a, tenant_a_user) -> None:
    document = WorkflowConfigurationService.get_configuration(tenant_a.id).document
    document = {
        **document,
        "operational": {**document["operational"], "outbox_stale_seconds": 30},
    }
    WorkflowConfigurationService.update_configuration(
        tenant_a.id,
        tenant_a_user,
        document,
        expected_version=1,
        change_reason="tighten stale outbox window",
    )
    event = OutboxEvent.objects.for_tenant(tenant_a.id).create(
        tenant_id=tenant_a.id,
        aggregate_type="workflow",
        aggregate_id=uuid.uuid4(),
        event_type="workflow.test",
        payload={},
        status=OutboxStatus.PENDING,
    )
    OutboxEvent.objects.for_tenant(tenant_a.id).filter(id=event.id).update(
        created_at=timezone.now() - timedelta(minutes=5)
    )

    assert health._outbox_fresh(tenant_a.id) is False


def test_required_extensions_readiness_rejects_published_contract_drift(tenant_a, tenant_a_user) -> None:
    workflow = publish(tenant_a.id, tenant_a_user, action_payload(key="health-contract"))
    step = WorkflowStep.objects.for_tenant(tenant_a.id).get(workflow=workflow)
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {WorkflowStep._meta.db_table} SET handler_contract_fingerprint = %s WHERE id = %s",
            ["stale-contract", step.id.hex],
        )
        assert cursor.rowcount == 1

    assert health._required_extensions_ready(tenant_a.id) is False


def test_required_extensions_readiness_returns_false_when_notification_mapping_is_invalid(
    tenant_a,
    tenant_a_user,
) -> None:
    published = publish(tenant_a.id, tenant_a_user, action_payload(key="bad-health"))
    step = WorkflowStep.objects.for_tenant(tenant_a.id).get(workflow=published)
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {WorkflowStep._meta.db_table} SET step_type = %s, config = %s WHERE id = %s",
            ["notification", json.dumps({"channel": "missing"}), step.id.hex],
        )
        assert cursor.rowcount == 1

    assert health._required_extensions_ready(published.tenant_id) is False
