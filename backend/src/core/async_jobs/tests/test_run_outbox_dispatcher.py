"""Local outbox dispatcher command behavior."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.conf import settings
from django.core.management import call_command

from src.core.async_jobs.models import OutboxEvent, OutboxStatus
from src.core.async_jobs.services import enqueue, register_handler, unregister_handler

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.postgresql,
    pytest.mark.skipif(
        "sqlite" in settings.DATABASES["default"]["ENGINE"],
        reason="outbox dispatcher regression requires PostgreSQL migrations",
    ),
]


def test_dispatcher_executes_async_job_and_marks_outbox_dispatched() -> None:
    tenant_id = uuid.uuid4()
    command = f"test.dispatcher.{uuid.uuid4()}"
    seen: list[uuid.UUID] = []

    def handler(job: Any) -> dict[str, bool]:
        seen.append(job.id)
        return {"ok": True}

    register_handler(command, handler)
    try:
        job = enqueue(
            tenant_id,
            uuid.uuid4(),
            command,
            {"source": "test"},
            f"idem-{uuid.uuid4()}",
        )
        call_command("run_outbox_dispatcher", "--once")
    finally:
        unregister_handler(command)

    event = OutboxEvent.objects.get(aggregate_id=job.id)
    assert seen == [job.id]
    assert event.status == OutboxStatus.DISPATCHED
    assert event.broker_message_id == f"local-execute:{event.id}"


def test_dispatcher_requires_explicit_domain_event_acknowledgement() -> None:
    tenant_id = uuid.uuid4()
    event = OutboxEvent.objects.create(
        tenant_id=tenant_id,
        aggregate_type="security_configuration",
        aggregate_id=uuid.uuid4(),
        event_type="security.configuration.changed",
        payload={"correlation_id": "corr-test"},
    )

    call_command("run_outbox_dispatcher", "--once")
    event.refresh_from_db()
    assert event.status == OutboxStatus.PENDING

    call_command("run_outbox_dispatcher", "--once", "--acknowledge-domain-events")
    event.refresh_from_db()
    assert event.status == OutboxStatus.DISPATCHED
    assert event.broker_message_id == f"local-domain:{event.id}"
