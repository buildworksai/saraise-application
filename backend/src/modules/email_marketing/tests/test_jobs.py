"""Durable handler registration and tenant worker contracts."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import get_handler
from src.core.tenancy import MissingTenantContext
from src.modules.email_marketing import events, jobs

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db


def _job(tenant_id: uuid.UUID, command: str, payload: dict[str, object]) -> AsyncJob:
    return AsyncJob.objects.create(
        tenant_id=tenant_id,
        actor_id=str(uuid.uuid4()),
        command=command,
        idempotency_key=f"{command}:{uuid.uuid4()}",
        payload=payload,
        correlation_id=str(uuid.uuid4()),
    )


def test_all_handlers_are_registered_without_replacement() -> None:
    jobs.register_job_handlers()
    for command in jobs.COMMANDS:
        assert get_handler(command) is jobs._HANDLERS[command]


def test_generic_worker_requires_tenant_and_forwards_canonical_uuid(monkeypatch) -> None:
    with pytest.raises(MissingTenantContext):
        jobs.execute_email_marketing_job(job_id=uuid.uuid4())  # type: ignore[call-arg]
    observed: list[tuple[uuid.UUID, uuid.UUID]] = []
    monkeypatch.setattr(jobs, "execute", lambda job_id, tenant_id: observed.append((job_id, tenant_id)))
    job_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    jobs.execute_email_marketing_job(job_id=job_id, tenant_id=str(tenant_id))  # type: ignore[arg-type]
    assert observed == [(job_id, tenant_id)]


def test_command_worker_cannot_execute_another_tenants_job(monkeypatch) -> None:
    owner = uuid.uuid4()
    foreign = uuid.uuid4()
    job = _job(owner, jobs.SEND_CAMPAIGN_COMMAND, {"campaign_id": str(uuid.uuid4())})
    called = False

    def fake_execute(job_id: uuid.UUID, tenant_id: uuid.UUID) -> object:
        nonlocal called
        called = True
        return object()

    monkeypatch.setattr(jobs, "execute", fake_execute)
    with pytest.raises(AsyncJob.DoesNotExist):
        jobs.send_campaign_worker(job_id=job.id, tenant_id=foreign)
    assert called is False


def test_resolve_handler_returns_persisted_resolution_evidence() -> None:
    tenant_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    job = _job(tenant_id, jobs.RESOLVE_AUDIENCE_COMMAND, {"campaign_id": str(campaign_id)})
    result = SimpleNamespace(candidates=(object(), object()), resolver_key="manual")
    with patch("src.modules.email_marketing.services.AudienceService.resolve", return_value=result) as resolve:
        payload = jobs.resolve_audience_handler(job)
    resolve.assert_called_once()
    assert payload == {
        "campaign_id": str(campaign_id),
        "resolver_key": "manual",
        "resolved_recipient_count": 2,
    }


def test_campaign_handler_rejects_sensitive_or_undeclared_result_fields() -> None:
    job = _job(uuid.uuid4(), jobs.SEND_CAMPAIGN_COMMAND, {"campaign_id": str(uuid.uuid4())})
    with patch(
        "src.modules.email_marketing.services.DeliveryService.process_campaign_job",
        return_value={"campaign_id": str(uuid.uuid4()), "raw_provider_response": "secret"},
    ):
        with pytest.raises(ValueError, match="non-allowlisted"):
            jobs.send_campaign_handler(job)


def test_provider_event_handler_rehydrates_only_verified_contract() -> None:
    tenant_id = uuid.uuid4()
    occurred_at = "2026-07-22T12:00:00+00:00"
    job = _job(
        tenant_id,
        jobs.PROCESS_PROVIDER_EVENT_COMMAND,
        {
            "gateway_key": "provider",
            "event": {
                "provider_event_id": "evt-1",
                "provider_message_id": "msg-1",
                "event_type": "delivered",
                "occurred_at": occurred_at,
                "metadata": {"source": "webhook"},
            },
        },
    )
    persisted = SimpleNamespace(id=uuid.uuid4(), event_type="delivered")
    with patch(
        "src.modules.email_marketing.services.DeliveryService.record_provider_event",
        return_value=persisted,
    ) as record:
        payload = jobs.process_provider_event_handler(job)
    assert payload == {"delivery_event_id": str(persisted.id), "event_type": "delivered"}
    verified = record.call_args.args[2]
    assert verified.provider_event_id == "evt-1"
    assert verified.occurred_at.isoformat() == occurred_at


def test_versioned_domain_event_persists_complete_sanitized_envelope() -> None:
    tenant_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    event = events.publish_domain_event(
        tenant_id,
        "email_marketing.campaign.send_queued.v1",
        "email_campaign",
        campaign_id,
        actor_id=uuid.uuid4(),
        correlation_id=str(uuid.uuid4()),
        job_id=uuid.uuid4(),
        payload={"eligible_recipient_count": 12, "status": "queueing"},
    )
    envelope = event.payload
    assert envelope["schema_id"] == event.event_type
    assert envelope["schema_version"] == 1
    assert envelope["event_version"] == 1
    assert envelope["tenant_id"] == str(tenant_id)
    assert envelope["aggregate_id"] == str(campaign_id)
    assert envelope["payload"] == {"eligible_recipient_count": 12, "status": "queueing"}


@pytest.mark.parametrize("unsafe_key", ["email", "body", "token", "raw_provider_response"])
def test_domain_event_rejects_private_payload_fields(unsafe_key: str) -> None:
    with pytest.raises(ValueError, match="non-allowlisted"):
        events.publish_domain_event(
            uuid.uuid4(),
            "email_marketing.email.sent.v1",
            "campaign_recipient",
            uuid.uuid4(),
            payload={unsafe_key: "must-not-persist"},
        )
