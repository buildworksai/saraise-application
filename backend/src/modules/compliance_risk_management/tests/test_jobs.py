"""Durable handler registration, tenant isolation, and truthful outcomes."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import get_handler

from ..integrations import IntegrationRegistry, IntegrationUnavailable, set_integration_registry
from ..jobs import (
    DISPATCH_REMINDERS,
    GENERATE_RECURRING_CONTROL_TESTS,
    MARK_CALENDAR_OVERDUE,
    MARK_REMEDIATION_OVERDUE,
    REGISTERED_COMMANDS,
    dispatch_reminders_handler,
    generate_recurring_control_tests_handler,
    mark_calendar_overdue_handler,
    mark_remediation_overdue_handler,
)
from ..models import ControlTest
from .factories import (
    ComplianceCalendarEntryFactory,
    ControlFactory,
    RemediationActionFactory,
)

pytestmark = pytest.mark.django_db


def _job(command: str, tenant_id: uuid.UUID, actor_id: uuid.UUID, *, as_of: object) -> AsyncJob:
    return AsyncJob(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        actor_id=str(actor_id),
        command=command,
        idempotency_key=f"test:{command}:{uuid.uuid4()}",
        payload={"as_of": as_of},
        correlation_id=str(uuid.uuid4()),
    )


def test_all_commands_are_registered_with_the_expected_handler() -> None:
    expected = {
        MARK_CALENDAR_OVERDUE: mark_calendar_overdue_handler,
        MARK_REMEDIATION_OVERDUE: mark_remediation_overdue_handler,
        DISPATCH_REMINDERS: dispatch_reminders_handler,
        GENERATE_RECURRING_CONTROL_TESTS: generate_recurring_control_tests_handler,
    }
    assert set(REGISTERED_COMMANDS) == set(expected)
    for command, handler in expected.items():
        assert get_handler(command) is handler


def test_calendar_overdue_handler_mutates_only_its_job_tenant() -> None:
    tenant_a, tenant_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    as_of = timezone.localdate()
    entry_a = ComplianceCalendarEntryFactory(tenant_id=tenant_a, scheduled_date=as_of - timedelta(days=1))
    entry_b = ComplianceCalendarEntryFactory(tenant_id=tenant_b, scheduled_date=as_of - timedelta(days=1))

    result = mark_calendar_overdue_handler(_job(MARK_CALENDAR_OVERDUE, tenant_a, actor, as_of=as_of.isoformat()))

    entry_a.refresh_from_db()
    entry_b.refresh_from_db()
    assert result == {"entries_marked_overdue": 1}
    assert entry_a.status == "overdue"
    assert entry_b.status == "upcoming"


def test_remediation_overdue_handler_mutates_only_its_job_tenant() -> None:
    tenant_a, tenant_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    as_of = timezone.localdate()
    action_a = RemediationActionFactory(tenant_id=tenant_a, due_date=as_of - timedelta(days=1))
    action_b = RemediationActionFactory(tenant_id=tenant_b, due_date=as_of - timedelta(days=1))

    result = mark_remediation_overdue_handler(_job(MARK_REMEDIATION_OVERDUE, tenant_a, actor, as_of=as_of.isoformat()))

    action_a.refresh_from_db()
    action_b.refresh_from_db()
    assert result == {"actions_marked_overdue": 1}
    assert action_a.status == "overdue"
    assert action_b.status == "planned"


def test_recurring_test_handler_schedules_due_active_controls_only_for_tenant() -> None:
    tenant_a, tenant_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    as_of = timezone.localdate()
    due = ControlFactory(tenant_id=tenant_a, status="active", next_test_due=as_of - timedelta(days=1))
    ControlFactory(tenant_id=tenant_a, status="active", next_test_due=as_of + timedelta(days=1))
    ControlFactory(tenant_id=tenant_b, status="active", next_test_due=as_of - timedelta(days=1))

    result = generate_recurring_control_tests_handler(
        _job(GENERATE_RECURRING_CONTROL_TESTS, tenant_a, actor, as_of=as_of.isoformat())
    )

    assert result == {"controls_evaluated": 1, "tests_scheduled": 1}
    assert ControlTest.objects.for_tenant(tenant_a).filter(control=due, scheduled_for=as_of).exists()
    assert not ControlTest.objects.for_tenant(tenant_b).exists()


def test_reminder_handler_fails_truthfully_when_notification_adapter_is_unavailable() -> None:
    tenant, actor, as_of = uuid.uuid4(), uuid.uuid4(), timezone.localdate()
    ComplianceCalendarEntryFactory(tenant_id=tenant, scheduled_date=as_of + timedelta(days=1), reminder_days=[1])
    set_integration_registry(IntegrationRegistry())

    with pytest.raises(IntegrationUnavailable):
        dispatch_reminders_handler(_job(DISPATCH_REMINDERS, tenant, actor, as_of=as_of.isoformat()))


def test_handler_rejects_missing_deterministic_as_of_without_mutation() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    action = RemediationActionFactory(tenant_id=tenant, due_date=timezone.localdate() - timedelta(days=1))

    with pytest.raises(ValueError, match="requires an ISO as_of date"):
        mark_remediation_overdue_handler(_job(MARK_REMEDIATION_OVERDUE, tenant, actor, as_of=None))

    action.refresh_from_db()
    assert action.status == "planned"
