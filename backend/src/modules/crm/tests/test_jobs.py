"""Durable CRM command and transactional event tests."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import get_handler
from src.modules.crm.integrations import InvalidIntegrationResponse
from src.modules.crm.jobs import (
    EXTERNAL_ACTIVITY_COMMAND,
    FULFILLMENT_ACK_COMMAND,
    LEAD_SCORING_COMMAND,
    STALE_DEAL_COMMAND,
    JobIdempotencyConflict,
    enqueue_fulfillment_acknowledgement_job,
    enqueue_stale_deal_scan,
    publish_crm_event,
    scan_stale_deals,
)
from src.modules.crm.models import Account, Lead, LeadStatus, Opportunity, OpportunityStage, OpportunityStatus
from src.modules.crm.state_machines import apply_lead_command, apply_opportunity_command

pytestmark = pytest.mark.django_db(transaction=True)


def test_handlers_are_registered_for_every_published_command() -> None:
    assert callable(get_handler(STALE_DEAL_COMMAND))
    assert callable(get_handler(LEAD_SCORING_COMMAND))
    assert callable(get_handler(EXTERNAL_ACTIVITY_COMMAND))
    assert callable(get_handler(FULFILLMENT_ACK_COMMAND))


def test_stale_scan_enqueue_is_durable_idempotent_and_tenant_scoped() -> None:
    tenant = uuid.uuid4()
    other = uuid.uuid4()
    actor = "worker-scheduler"
    as_of = timezone.now()
    first = enqueue_stale_deal_scan(
        tenant,
        as_of=as_of,
        idempotency_key="daily-2026-07-22",
        actor_id=actor,
        correlation_id="req_stale_scan_1",
    )
    replay = enqueue_stale_deal_scan(
        tenant,
        as_of=as_of,
        idempotency_key="daily-2026-07-22",
        actor_id=actor,
        correlation_id="req_stale_scan_1",
    )
    other_job = enqueue_stale_deal_scan(
        other,
        as_of=as_of,
        idempotency_key="daily-2026-07-22",
        actor_id=actor,
        correlation_id="req_stale_scan_2",
    )
    assert replay.id == first.id
    assert other_job.id != first.id
    assert AsyncJob.objects.filter(tenant_id=tenant, command=STALE_DEAL_COMMAND).count() == 1
    assert OutboxEvent.objects.filter(tenant_id=tenant, aggregate_id=first.id).exists()


def test_namespaced_idempotency_key_rejects_payload_conflict() -> None:
    tenant = uuid.uuid4()
    first_time = timezone.now()
    enqueue_stale_deal_scan(
        tenant,
        as_of=first_time,
        idempotency_key="same-key",
        actor_id="scheduler",
        correlation_id="req_stale_conflict",
    )
    with pytest.raises(JobIdempotencyConflict):
        enqueue_stale_deal_scan(
            tenant,
            as_of=first_time + timedelta(minutes=1),
            idempotency_key="same-key",
            actor_id="scheduler",
            correlation_id="req_stale_conflict",
        )


def test_event_envelope_is_versioned_and_payload_allowlisted() -> None:
    tenant = uuid.uuid4()
    aggregate = uuid.uuid4()
    event = publish_crm_event(
        tenant,
        event_type="crm.lead.scored",
        aggregate_type="lead",
        aggregate_id=aggregate,
        actor_id="actor-1",
        correlation_id="req_score_event",
        payload={"score": 80, "grade": "A", "provider": "provider-key", "version": 2},
    )
    assert event.payload["schema_id"] == "crm.lead.scored.v1"
    assert event.payload["tenant_id"] == str(tenant)
    assert event.payload["payload"]["score"] == 80
    with pytest.raises(ValueError):
        publish_crm_event(
            tenant,
            event_type="crm.lead.scored",
            aggregate_type="lead",
            aggregate_id=aggregate,
            actor_id="actor-1",
            correlation_id="req_score_event",
            payload={"email": "must-not-enter-outbox@example.invalid"},
        )


def test_stale_scan_emits_once_per_interval_without_cross_tenant_data() -> None:
    tenant = uuid.uuid4()
    other = uuid.uuid4()
    account = Account.objects.create(tenant_id=tenant, name="Example Account")
    other_account = Account.objects.create(tenant_id=other, name="Other Account")
    as_of = timezone.now()
    common = {
        "amount": Decimal("1250.00"),
        "currency": "USD",
        "probability": 10,
        "stage": OpportunityStage.PROSPECTING,
        "status": OpportunityStatus.OPEN,
        "close_date": timezone.localdate() + timedelta(days=30),
        "last_activity_at": as_of - timedelta(days=30),
    }
    opportunity = Opportunity.objects.create(
        tenant_id=tenant, account_id=account.id, name="Tenant opportunity", **common
    )
    Opportunity.objects.create(tenant_id=other, account_id=other_account.id, name="Other opportunity", **common)
    assert scan_stale_deals(tenant_id=tenant, as_of=as_of) == {"emitted_alerts": 1}
    assert scan_stale_deals(tenant_id=tenant, as_of=as_of) == {"emitted_alerts": 0}
    events = OutboxEvent.objects.filter(tenant_id=tenant, event_type="crm.stale_deal.detected")
    assert events.count() == 1
    assert events.get().aggregate_id == opportunity.id
    assert not OutboxEvent.objects.filter(tenant_id=other, event_type="crm.stale_deal.detected").exists()


def test_effect_aware_transitions_persist_constrained_fields_atomically() -> None:
    tenant = uuid.uuid4()
    account = Account.objects.create(tenant_id=tenant, name="Transition Account")
    opportunity = Opportunity.objects.create(
        tenant_id=tenant,
        account_id=account.id,
        name="Transition opportunity",
        amount=Decimal("2500.00"),
        currency="USD",
        probability=10,
        stage=OpportunityStage.PROSPECTING,
        status=OpportunityStatus.OPEN,
        close_date=timezone.localdate() + timedelta(days=30),
    )
    lead = Lead.objects.create(
        tenant_id=tenant,
        first_name="",
        last_name="Qualified",
        email="qualified@example.invalid",
        status=LeadStatus.QUALIFIED,
    )
    converted = apply_lead_command(
        tenant,
        lead_id=lead.id,
        command="convert",
        transition_key="lead-convert-1",
        actor_id="seller-1",
        correlation_id="req_convert_1",
        expected_version=1,
        opportunity_id=opportunity.id,
        context={
            "account_id": account.id,
            "opportunity_id": opportunity.id,
            "opportunity_amount": opportunity.amount,
        },
    )
    assert converted.status == LeadStatus.CONVERTED
    assert converted.converted_at is not None
    assert converted.converted_to_opportunity_id == opportunity.id
    assert converted.version == 2
    assert len(converted.transition_history) == 1

    lost = apply_opportunity_command(
        tenant,
        opportunity_id=opportunity.id,
        command="close_lost",
        transition_key="opp-loss-1",
        actor_id="seller-1",
        correlation_id="req_loss_1",
        expected_version=1,
        reason="Budget unavailable",
    )
    assert lost.stage == OpportunityStage.CLOSED_LOST
    assert lost.status == OpportunityStatus.LOST
    assert lost.probability == 0
    assert lost.closed_at is not None
    assert lost.loss_reason == "Budget unavailable"
    assert lost.version == 2
    replay = apply_opportunity_command(
        tenant,
        opportunity_id=opportunity.id,
        command="close_lost",
        transition_key="opp-loss-1",
        actor_id="seller-1",
        correlation_id="req_loss_1",
        expected_version=1,
        reason="Budget unavailable",
    )
    assert replay.version == 2
    assert len(replay.transition_history) == 1


def test_fulfillment_acknowledgement_is_verified_before_durable_enqueue() -> None:
    tenant = uuid.uuid4()
    event = {
        "event_type": "sales_management.order.created.v1",
        "event_id": str(uuid.uuid4()),
        "tenant_id": str(tenant),
        "opportunity_id": str(uuid.uuid4()),
        "order_id": str(uuid.uuid4()),
        "correlation_id": "req_order_ack_job",
        "delivery_verified": True,
    }
    job = enqueue_fulfillment_acknowledgement_job(
        tenant,
        event=event,
        idempotency_key="order-ack-1",
        actor_id="event-dispatcher",
        correlation_id="req_order_ack_job",
    )
    assert job.command == FULFILLMENT_ACK_COMMAND
    assert job.payload["event"]["delivery_verified"] is True
    with pytest.raises(InvalidIntegrationResponse):
        enqueue_fulfillment_acknowledgement_job(
            tenant,
            event={**event, "delivery_verified": False},
            idempotency_key="order-ack-2",
            actor_id="event-dispatcher",
            correlation_id="req_order_ack_job",
        )
