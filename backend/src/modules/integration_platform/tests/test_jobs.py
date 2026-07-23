"""Durable delivery retry, redelivery, and stale recovery tests."""

import uuid
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue

from ..models import DeliveryStatus, ImmutableRecordError, WebhookDeliveryAttempt
from ..services import WebhookDeliveryWorker
from ..state_machines import DELIVERY_STATE_MACHINE
from .factories import delivery_factory

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def encryption_key(settings):
    settings.SARAISE_ENCRYPTION_KEY = Fernet.generate_key().decode()


def test_retry_creates_a_future_durable_job_and_outbox():
    delivery = delivery_factory()
    delivery = DELIVERY_STATE_MACHINE.apply(delivery, "start", tenant_id=delivery.tenant_id, transition_key="start")
    delivery.attempt_count = 1
    delivery.save(update_fields=("attempt_count", "updated_at"))
    result = WebhookDeliveryWorker().schedule_retry(delivery.tenant_id, delivery.id, TimeoutError())
    delivery.refresh_from_db()
    assert result.status == "failed" and delivery.status == DeliveryStatus.RETRYING
    retry_job = AsyncJob.objects.get(id=delivery.job_id)
    event = OutboxEvent.objects.get(aggregate_id=retry_job.id, event_type="async_job.enqueued")
    assert event.available_at == delivery.next_attempt_at
    attempt = WebhookDeliveryAttempt.objects.get(
        tenant_id=delivery.tenant_id,
        delivery=delivery,
        attempt_number=1,
    )
    assert attempt.outcome == "retrying"
    attempt.outcome = "tampered"
    with pytest.raises(ImmutableRecordError):
        attempt.save()
    with pytest.raises(ImmutableRecordError):
        WebhookDeliveryAttempt.objects.filter(pk=attempt.pk).delete()


def test_recover_stale_is_tenant_scoped():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    stale = enqueue(tenant, actor, "tests.stale", {}, "stale")
    stale.status = "running"
    stale.save(update_fields=("status", "updated_at"))
    AsyncJob.objects.filter(pk=stale.pk).update(updated_at=timezone.now() - timedelta(hours=2))
    recovered = WebhookDeliveryWorker().recover_stale(tenant, timezone.now() - timedelta(hours=1))
    assert [job.id for job in recovered] == [stale.id]
