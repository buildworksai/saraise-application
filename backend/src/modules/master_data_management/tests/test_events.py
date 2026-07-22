"""Transactional, sanitized MDM event contract tests."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.db import transaction

from src.core.async_jobs.models import OutboxEvent
from src.modules.master_data_management.events import (
    EVENT_TYPES,
    SAFE_PAYLOAD_KEYS,
    SCHEMA_VERSION,
    publish_domain_event,
)

pytestmark = pytest.mark.django_db


def test_required_event_taxonomy_is_registered() -> None:
    required = {
        "mdm.entity_type.created",
        "mdm.entity.created",
        "mdm.entity.updated",
        "mdm.entity.archived",
        "mdm.entity.restored",
        "mdm.entity.quality_scored",
        "mdm.quality_issue.opened",
        "mdm.quality_issue.resolved",
        "mdm.match_candidate.created",
        "mdm.match_candidate.reviewed",
        "mdm.entities.merged",
        "mdm.merge.reversed",
    }
    assert required <= EVENT_TYPES
    assert SCHEMA_VERSION >= 1


def test_publish_persists_complete_versioned_tenant_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    aggregate_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    monkeypatch.setattr(
        "src.modules.master_data_management.events.get_correlation_id",
        lambda: "corr-event-test",
    )

    event = publish_domain_event(
        tenant_id,
        "mdm.entity.updated",
        "master_data_entity",
        aggregate_id,
        actor_id=actor_id,
        causation_id="cause-1",
        payload={
            "changed_fields": ["entity_name"],
            "version": 2,
            "quality_score": Decimal("75.50"),
        },
    )

    event.refresh_from_db()
    assert event.tenant_id == tenant_id
    assert event.aggregate_id == aggregate_id
    assert event.event_type == "mdm.entity.updated"
    assert event.status == "pending"
    assert event.payload == {
        **event.payload,
        "event_id": str(event.id),
        "schema_id": "mdm.entity.updated.v1",
        "schema_version": SCHEMA_VERSION,
        "event_type": "mdm.entity.updated",
        "tenant_id": str(tenant_id),
        "aggregate_type": "master_data_entity",
        "aggregate_id": str(aggregate_id),
        "actor_id": str(actor_id),
        "correlation_id": "corr-event-test",
        "causation_id": "cause-1",
    }
    assert event.payload["occurred_at"]
    assert event.payload["payload"] == {
        "changed_fields": ["entity_name"],
        "version": 2,
        "quality_score": "75.50",
    }


@pytest.mark.parametrize(
    ("event_type", "aggregate_type", "payload", "message"),
    [
        ("mdm.fabricated.success", "entity", {}, "unsupported MDM event type"),
        ("mdm.entity.created", "", {}, "aggregate_type"),
        ("mdm.entity.created", "entity", {"data": {"tax_id": "secret"}}, "non-allowlisted"),
        ("mdm.entity.created", "entity", {"snapshot": {"bank": "secret"}}, "non-allowlisted"),
    ],
)
def test_event_publisher_rejects_unknown_or_sensitive_contract_data(
    event_type: str,
    aggregate_type: str,
    payload: dict[str, object],
    message: str,
) -> None:
    before = OutboxEvent.objects.count()
    with pytest.raises(ValueError, match=message):
        publish_domain_event(
            uuid.uuid4(),
            event_type,
            aggregate_type,
            uuid.uuid4(),
            actor_id=uuid.uuid4(),
            payload=payload,
        )
    assert OutboxEvent.objects.count() == before


def test_payload_allowlist_has_no_raw_domain_or_secret_fields() -> None:
    forbidden = {
        "data",
        "data_snapshot",
        "source_snapshot",
        "golden_snapshot_before",
        "golden_snapshot_after",
        "evidence",
        "tax_id",
        "bank_details",
        "credentials",
    }
    assert SAFE_PAYLOAD_KEYS.isdisjoint(forbidden)


def test_domain_event_participates_in_callers_transaction() -> None:
    tenant_id = uuid.uuid4()
    with pytest.raises(RuntimeError, match="abort mutation"):
        with transaction.atomic():
            publish_domain_event(
                tenant_id,
                "mdm.entity.created",
                "master_data_entity",
                uuid.uuid4(),
                actor_id=uuid.uuid4(),
                payload={"changed_fields": ["entity_code"]},
            )
            raise RuntimeError("abort mutation")

    assert not OutboxEvent.objects.for_tenant(tenant_id).exists()


def test_events_are_queryable_through_explicit_tenant_scope() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    event_a = publish_domain_event(
        tenant_a,
        "mdm.entity.created",
        "master_data_entity",
        uuid.uuid4(),
        actor_id=uuid.uuid4(),
    )
    event_b = publish_domain_event(
        tenant_b,
        "mdm.entity.created",
        "master_data_entity",
        uuid.uuid4(),
        actor_id=uuid.uuid4(),
    )

    assert list(OutboxEvent.objects.for_tenant(tenant_a).values_list("id", flat=True)) == [event_a.id]
    assert event_b.id not in OutboxEvent.objects.for_tenant(tenant_a).values_list("id", flat=True)
