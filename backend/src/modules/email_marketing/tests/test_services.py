"""Service-level evidence for tenant, consent, lifecycle, and idempotency rules."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from src.core.access.entitlements import Entitlement, Quota
from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.modules.email_marketing import adapters
from src.modules.email_marketing.adapters import DeliveryReceipt, DependencyHealth, OperationResult
from src.modules.email_marketing.models import CampaignRecipient, DeliveryAttempt, DeliveryEvent, EmailTemplate
from src.modules.email_marketing.services import (
    AudienceCandidate,
    AudienceService,
    CampaignService,
    ComplianceService,
    ConfigurationService,
    DeliveryService,
    DomainConflict,
    TemplateService,
    _validate_tenant_json,
    get_platform_runtime_defaults,
    validate_configuration_document,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def identity() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.uuid4(), uuid.uuid4()


def template_data(code: str = "welcome") -> dict[str, object]:
    return {
        "template_code": code,
        "template_name": "Welcome",
        "subject": "Hello {{ name }}",
        "body_html": "<p>Hello {{ name }}</p>",
        "body_text": "Hello {{ name }}",
        "design_json": {"version": 1},
    }


def campaign_data(template: EmailTemplate, code: str = "launch") -> dict[str, object]:
    return {
        "campaign_code": code,
        "campaign_name": "Launch",
        "campaign_type": "broadcast",
        "template_id": template.id,
        "subject": "Hello {{ name }}",
        "from_name": "SARAISE",
        "from_email": "Marketing@EXAMPLE.COM",
        "audience_definition": {
            "schema_version": 1,
            "resolver": "manual",
            "recipients": [
                {
                    "email": "Customer@EXAMPLE.COM",
                    "display_name": "Customer",
                    "personalization": {"name": "Customer"},
                }
            ],
        },
        "timezone": "UTC",
    }


class ReadyGateway:
    gateway_key = "django"
    reconciliation_supported = True

    def health(self) -> DependencyHealth:
        return DependencyHealth(
            available=True,
            code="ready",
            checked_at=timezone.now(),
            circuit_state="closed",
            reconciliation_supported=True,
        )

    def submit(self, message, idempotency_key: str, correlation_id: str) -> OperationResult[DeliveryReceipt]:
        return OperationResult.success(
            DeliveryReceipt(
                provider_message_id=f"provider-{idempotency_key[-12:]}",
                gateway_key=self.gateway_key,
                acknowledgement="provider_accepted",
                accepted_at=timezone.now(),
                evidence={"correlation_id": correlation_id, "recipient": message.recipient},
            )
        )


class FailingGateway(ReadyGateway):
    def submit(self, message, idempotency_key: str, correlation_id: str) -> OperationResult[DeliveryReceipt]:
        return OperationResult.failure(
            "temporary_gateway_failure",
            retryable=True,
            ambiguous=True,
            detail="Provider timed out after accepting the request envelope.",
        )


class LookupGateway(ReadyGateway):
    def __init__(self, result: OperationResult[DeliveryReceipt]) -> None:
        self.result = result

    def lookup(self, provider_message_id: str) -> OperationResult[DeliveryReceipt]:
        assert provider_message_id == "provider-timeout"
        return self.result


class InvalidAcknowledgementGateway(ReadyGateway):
    def submit(self, message, idempotency_key: str, correlation_id: str) -> OperationResult[object]:
        del message, idempotency_key, correlation_id
        receipt = type(
            "InvalidReceipt",
            (),
            {
                "provider_message_id": "provider-invalid-ack",
                "acknowledgement": "provider_unknown",
                "evidence": {"provider_status": "unknown"},
            },
        )()
        return OperationResult.success(receipt)


class VerifiedProviderEvent:
    provider_event_id = "provider-event-1"
    provider_message_id = "provider-send-1"
    event_type = "delivered"
    occurred_at = timezone.now()
    link_url_hash = ""
    bounce_class = ""
    metadata = {"provider": "unit"}
    correlation_id = "provider-correlation"

    def as_mapping(self) -> dict[str, object]:
        return {
            "provider_event_id": self.provider_event_id,
            "provider_message_id": self.provider_message_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "metadata": self.metadata,
        }


def prepare_sendable_campaign(
    tenant: uuid.UUID,
    actor: uuid.UUID,
    settings,
    monkeypatch: pytest.MonkeyPatch,
    *,
    gateway: ReadyGateway | None = None,
):
    settings.EMAIL_MARKETING_VERIFIED_SENDERS = {str(tenant): ["Marketing@example.com"]}
    settings.SARAISE_PUBLIC_URL = "https://email.example.test"
    monkeypatch.setattr(adapters, "get_delivery_gateway", lambda key="django": gateway or ReadyGateway())
    Entitlement.objects.create(tenant_id=tenant, capability="email_marketing")
    Quota.objects.create(tenant_id=tenant, resource="email_marketing.monthly_recipients", limit=25, remaining=25)
    template = TemplateService.create_template(tenant, actor, template_data())
    campaign = CampaignService.create_campaign(tenant, actor, campaign_data(template))
    ComplianceService.record_consent(
        tenant,
        actor,
        {
            "email": "Customer@example.com",
            "purpose": "marketing",
            "status": "granted",
            "lawful_basis": "consent",
            "source": "api",
            "notice_version": "v1",
            "captured_at": timezone.now(),
            "evidence": {},
        },
    )
    AudienceService.resolve(tenant, campaign.id, actor)
    campaign.refresh_from_db()
    return campaign


def test_campaign_create_normalizes_and_rejects_spoofed_state(
    identity: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant, actor = identity
    template = TemplateService.create_template(tenant, actor, template_data())
    data = campaign_data(template)
    data.update({"tenant_id": uuid.uuid4(), "status": "sent"})
    campaign = CampaignService.create_campaign(tenant, actor, data)
    assert campaign.tenant_id == tenant
    assert campaign.status == "draft"
    assert campaign.campaign_code == "LAUNCH"
    assert campaign.from_email == "Marketing@example.com"
    assert OutboxEvent.objects.filter(
        tenant_id=tenant,
        aggregate_id=campaign.id,
        event_type="email_marketing.campaign.created.v1",
    ).exists()


def test_campaign_template_lookup_is_tenant_bound(
    identity: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant, actor = identity
    foreign_tenant = uuid.uuid4()
    foreign = TemplateService.create_template(foreign_tenant, actor, template_data())
    with pytest.raises(ValidationError, match="Template does not exist"):
        CampaignService.create_campaign(tenant, actor, campaign_data(foreign))


def test_template_lifecycle_version_clone_and_immutability(
    identity: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant, actor = identity
    template = TemplateService.create_template(tenant, actor, template_data())
    updated = TemplateService.update_template(tenant, template.id, actor, {"template_name": "Updated"})
    assert updated.version == 2
    active = TemplateService.activate_template(tenant, template.id, actor, "activate-1")
    assert active.status == "active" and active.is_active
    archived = TemplateService.archive_template(tenant, template.id, actor, "archive-1")
    assert archived.status == "archived" and not archived.is_active
    with pytest.raises(DomainConflict):
        TemplateService.update_template(tenant, template.id, actor, {"template_name": "Forbidden"})
    clone = TemplateService.clone_template(tenant, template.id, actor, "welcome-v2")
    assert clone.status == "draft"
    assert clone.template_code == "WELCOME-V2"


def test_consent_history_and_suppression_precedence(
    identity: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant, actor = identity
    granted = ComplianceService.record_consent(
        tenant,
        actor,
        {
            "email": "Customer@EXAMPLE.COM",
            "purpose": "marketing",
            "status": "granted",
            "lawful_basis": "consent",
            "source": "form",
            "notice_version": "2026-01",
            "captured_at": timezone.now(),
            "evidence": {"version": 1},
        },
    )
    assert ComplianceService.is_eligible(tenant, granted.email, "marketing").eligible
    suppression = ComplianceService.suppress(
        tenant,
        actor,
        {
            "email": granted.email,
            "scope": "marketing",
            "reason": "manual",
            "source": "administrator",
            "notes": "Requested by compliance",
        },
    )
    decision = ComplianceService.is_eligible(tenant, granted.email, "marketing")
    assert not decision.eligible and decision.suppression_id == suppression.id
    ComplianceService.deactivate_suppression(tenant, suppression.id, actor, "Approved correction")
    revoked = ComplianceService.revoke_consent(tenant, actor, granted.email, "marketing", "api")
    assert revoked.supersedes_id == granted.id
    assert ComplianceService.latest_consent(tenant, granted.email, "marketing") == revoked
    assert not ComplianceService.is_eligible(tenant, granted.email, "marketing").eligible


def test_manual_audience_resolution_deduplicates_and_persists_eligibility(
    identity: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant, actor = identity
    template = TemplateService.create_template(tenant, actor, template_data())
    data = campaign_data(template)
    recipients = data["audience_definition"]["recipients"]  # type: ignore[index]
    recipients.append(  # type: ignore[union-attr]
        {
            "email": "Customer@example.com",
            "personalization": {"name": "Duplicate"},
        }
    )
    campaign = CampaignService.create_campaign(tenant, actor, data)
    ComplianceService.record_consent(
        tenant,
        actor,
        {
            "email": "Customer@example.com",
            "purpose": "marketing",
            "status": "granted",
            "lawful_basis": "consent",
            "source": "api",
            "notice_version": "v1",
            "captured_at": timezone.now(),
            "evidence": {},
        },
    )
    result = AudienceService.resolve(tenant, campaign.id, actor)
    assert len(result.candidates) == 2  # resolver evidence remains lossless
    assert CampaignRecipient.objects.filter(tenant_id=tenant, campaign=campaign).count() == 1
    recipient = CampaignRecipient.objects.get(tenant_id=tenant, campaign=campaign)
    assert recipient.status == "resolved"
    campaign.refresh_from_db()
    assert campaign.audience_snapshot_at is not None
    assert campaign.resolved_recipient_count == 1


def test_audience_request_is_durable_and_idempotent(
    identity: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant, actor = identity
    template = TemplateService.create_template(tenant, actor, template_data())
    campaign = CampaignService.create_campaign(tenant, actor, campaign_data(template))
    first = CampaignService.request_audience_resolution(tenant, campaign.id, actor, "resolve-once")
    second = CampaignService.request_audience_resolution(tenant, campaign.id, actor, "resolve-once")
    assert first.id == second.id
    assert AsyncJob.objects.filter(tenant_id=tenant, command="email_marketing.resolve_audience").count() == 1
    assert OutboxEvent.objects.filter(tenant_id=tenant, aggregate_id=first.id).exists()


def test_schedule_requires_future_aware_time_and_tenant_lookup(identity: tuple[uuid.UUID, uuid.UUID], settings) -> None:
    tenant, actor = identity
    template = TemplateService.create_template(tenant, actor, template_data())
    campaign = CampaignService.create_campaign(tenant, actor, campaign_data(template))
    settings.EMAIL_MARKETING_VERIFIED_SENDERS = {str(tenant): [campaign.from_email]}
    with pytest.raises(ValidationError):
        CampaignService.schedule_campaign(
            tenant,
            campaign.id,
            actor,
            timezone.now() - timedelta(minutes=1),
            "UTC",
            "schedule-past",
        )
    scheduled = CampaignService.schedule_campaign(
        tenant,
        campaign.id,
        actor,
        timezone.now() + timedelta(hours=1),
        "UTC",
        "schedule-future",
    )
    assert scheduled.status == "scheduled"
    with pytest.raises(NotFound):
        CampaignService.update_campaign(uuid.uuid4(), campaign.id, actor, {"campaign_name": "Cross tenant"})


def test_set_schedule_routes_draft_scheduled_and_unschedule_lifecycle_paths(
    identity: tuple[uuid.UUID, uuid.UUID], settings
) -> None:
    tenant, actor = identity
    template = TemplateService.create_template(tenant, actor, template_data())
    campaign = CampaignService.create_campaign(tenant, actor, campaign_data(template))
    settings.EMAIL_MARKETING_VERIFIED_SENDERS = {str(tenant): [campaign.from_email]}

    first_time = timezone.now() + timedelta(hours=2)
    scheduled = CampaignService.set_schedule(tenant, campaign.id, actor, first_time, "UTC", "set-schedule-once")
    second_time = timezone.now() + timedelta(hours=3)
    rescheduled = CampaignService.set_schedule(tenant, campaign.id, actor, second_time, "UTC", "reschedule-once")
    unscheduled = CampaignService.unschedule_campaign(tenant, campaign.id, actor, "unschedule-once")

    assert scheduled.status == "scheduled"
    assert rescheduled.status == "scheduled"
    assert rescheduled.scheduled_at == second_time
    assert unscheduled.status == "draft"
    assert unscheduled.scheduled_at is None


def test_cancel_campaign_cancels_unsent_recipients_and_pending_jobs(
    identity: tuple[uuid.UUID, uuid.UUID],
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, actor = identity
    campaign = prepare_sendable_campaign(tenant, actor, settings, monkeypatch)
    preflight = CampaignService.preflight(tenant, campaign.id)
    send_job = CampaignService.request_send(tenant, campaign.id, actor, "cancel-send-job", preflight.receipt)
    recipient = CampaignRecipient.objects.get(tenant_id=tenant, campaign=campaign)

    cancelled = CampaignService.cancel_campaign(tenant, campaign.id, actor, "cancel-campaign")

    send_job.refresh_from_db()
    recipient.refresh_from_db()
    assert cancelled.status == "cancelled"
    assert recipient.status == "cancelled"
    assert send_job.status == "cancelled"


def test_archive_is_soft_and_code_can_be_reused(
    identity: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant, actor = identity
    template = TemplateService.create_template(tenant, actor, template_data())
    campaign = CampaignService.create_campaign(tenant, actor, campaign_data(template))
    CampaignService.archive_campaign(tenant, campaign.id, actor)
    campaign.refresh_from_db()
    assert campaign.is_deleted and campaign.deleted_at and campaign.deleted_by == actor
    replacement = CampaignService.create_campaign(tenant, actor, campaign_data(template))
    assert replacement.id != campaign.id


def test_update_rejects_ownership_counters_and_non_draft(identity: tuple[uuid.UUID, uuid.UUID], settings) -> None:
    tenant, actor = identity
    template = TemplateService.create_template(tenant, actor, template_data())
    campaign = CampaignService.create_campaign(tenant, actor, campaign_data(template))
    with pytest.raises(ValidationError):
        CampaignService.update_campaign(tenant, campaign.id, actor, {"sent_count": 99})
    settings.EMAIL_MARKETING_VERIFIED_SENDERS = {str(tenant): [campaign.from_email]}
    CampaignService.schedule_campaign(
        tenant,
        campaign.id,
        actor,
        timezone.now() + timedelta(hours=1),
        "UTC",
        "schedule-non-draft",
    )
    with pytest.raises(DomainConflict):
        CampaignService.update_campaign(tenant, campaign.id, actor, {"campaign_name": "Late edit"})


def test_configuration_update_history_and_rollback(identity: tuple[uuid.UUID, uuid.UUID]) -> None:
    tenant, actor = identity
    current = ConfigurationService.current(tenant)
    document = get_platform_runtime_defaults()
    document["pagination"]["default_page_size"] = 50

    preview = ConfigurationService.preview(tenant, document)
    assert preview["valid"] is True
    assert any(change["path"] == "pagination.default_page_size" for change in preview["changes"])

    updated = ConfigurationService.update(tenant, actor, document, expected_version=current.version)
    assert updated.version == current.version + 1
    assert updated.document["pagination"]["default_page_size"] == 50

    rolled_back = ConfigurationService.rollback(
        tenant,
        actor,
        target_version=1,
        expected_version=updated.version,
    )
    assert rolled_back.version == updated.version + 1
    assert (
        rolled_back.document["pagination"]["default_page_size"] == current.document["pagination"]["default_page_size"]
    )
    assert ConfigurationService.history(tenant).count() == 3


def test_configuration_update_rejects_stale_or_noop_documents(identity: tuple[uuid.UUID, uuid.UUID]) -> None:
    tenant, actor = identity
    current = ConfigurationService.current(tenant)

    with pytest.raises(DomainConflict):
        ConfigurationService.update(
            tenant, actor, get_platform_runtime_defaults(), expected_version=current.version + 1
        )

    with pytest.raises(DomainConflict):
        ConfigurationService.update(tenant, actor, current.document, expected_version=current.version)


def test_platform_runtime_defaults_include_configured_gateway(settings) -> None:
    settings.EMAIL_MARKETING_DEFAULT_GATEWAY = "tenant-provider"

    document = get_platform_runtime_defaults()

    assert document["defaults"]["delivery_gateway"] == "tenant-provider"
    assert "tenant-provider" in document["integrations"]["gateway_keys"]


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        (lambda document: document.pop("limits"), "document"),
        (lambda document: document.update({"unexpected": {}}), "document"),
        (lambda document: document.update({"schema_version": 2}), "schema_version"),
        (
            lambda document: document["limits"].update({"json_max_depth": 0}),
            "limits.json_max_depth",
        ),
        (lambda document: document["pagination"].update({"default_page_size": 0}), "pagination"),
        (
            lambda document: document["pagination"].update({"page_size_options": [50, 25]}),
            "pagination.page_size_options",
        ),
        (
            lambda document: document["resilience"].update(
                {"retry_base_delay_seconds": 5, "retry_max_delay_seconds": 1}
            ),
            "resilience",
        ),
        (
            lambda document: document["tokens"].update({"tracking_token_days": 366}),
            "tokens.tracking_token_days",
        ),
        (
            lambda document: document["workflows"]["transitions"].update({"campaign": ["bad:edge"]}),
            "workflows.transitions.campaign",
        ),
        (
            lambda document: document["workflows"].update({"campaign_physical_delete_protected_states": ["sent"]}),
            "workflows.campaign_physical_delete_protected_states",
        ),
        (
            lambda document: document["workflows"].update(
                {"provider_acknowledgement_mapping": {"accepted": "accepted"}}
            ),
            "document.workflows.provider_acknowledgement_mapping",
        ),
        (
            lambda document: document["integrations"].update({"allowed_delivery_backends": ["unsafe.Backend"]}),
            "integrations",
        ),
        (
            lambda document: document["integrations"].update({"gateway_keys": [""]}),
            "integrations.gateway_keys",
        ),
        (
            lambda document: document["feature_flags"].update({"rollout_percentage": 101}),
            "feature_flags.rollout_percentage",
        ),
        (
            lambda document: document["feature_flags"].update({"roles": ["admin", "admin"]}),
            "feature_flags.roles",
        ),
        (
            lambda document: document["display"]["status_semantics"].update({"draft": "blue"}),
            "display.status_semantics",
        ),
        (
            lambda document: document["compliance"].update({"consent_required_status": "accepted"}),
            "compliance.consent_required_status",
        ),
    ],
)
def test_configuration_document_rejects_invalid_operator_policy(mutation, field) -> None:
    document = get_platform_runtime_defaults()
    mutation(document)

    with pytest.raises(ValidationError) as exc:
        validate_configuration_document(document)
    assert field in exc.value.detail


def test_campaign_create_rejects_disabled_gateway_and_audience_contract(
    identity: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant, actor = identity
    template = TemplateService.create_template(tenant, actor, template_data())
    disabled_gateway = campaign_data(template)
    disabled_gateway["gateway_key"] = "disabled"
    with pytest.raises(ValidationError) as gateway_error:
        CampaignService.create_campaign(tenant, actor, disabled_gateway)
    assert "gateway_key" in gateway_error.value.detail

    unsupported_audience = campaign_data(template)
    unsupported_audience["audience_definition"] = {
        "schema_version": 99,
        "resolver": "manual",
        "recipients": [],
    }
    with pytest.raises(ValidationError) as audience_error:
        CampaignService.create_campaign(tenant, actor, unsupported_audience)
    assert "audience_definition" in audience_error.value.detail


def test_campaign_update_clears_template_and_rejects_invalid_relationships(
    identity: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant, actor = identity
    template = TemplateService.create_template(tenant, actor, template_data())
    campaign = CampaignService.create_campaign(tenant, actor, campaign_data(template))
    cleared = CampaignService.update_campaign(tenant, campaign.id, actor, {"template_id": None, "reply_to_email": ""})
    assert cleared.template is None

    foreign_template = TemplateService.create_template(uuid.uuid4(), actor, template_data("foreign"))
    with pytest.raises(ValidationError) as foreign_error:
        CampaignService.update_campaign(tenant, campaign.id, actor, {"template_id": foreign_template.id})
    assert "template_id" in foreign_error.value.detail

    with pytest.raises(ValidationError) as timezone_error:
        CampaignService.update_campaign(tenant, campaign.id, actor, {"timezone": "Not/AZone"})
    assert "timezone" in timezone_error.value.detail


def test_template_archive_record_is_draft_only_and_tenant_safe(identity: tuple[uuid.UUID, uuid.UUID]) -> None:
    tenant, actor = identity
    draft = TemplateService.create_template(tenant, actor, template_data("archive-me"))
    TemplateService.archive_record(tenant, draft.id, actor)
    draft.refresh_from_db()
    assert draft.is_deleted and draft.deleted_by == actor
    with pytest.raises(NotFound):
        TemplateService.archive_record(tenant, draft.id, actor)

    active = TemplateService.create_template(tenant, actor, template_data("active-archive"))
    TemplateService.activate_template(tenant, active.id, actor, "activate-archive-target")
    with pytest.raises(DomainConflict):
        TemplateService.archive_record(tenant, active.id, actor)


def test_suppression_rejects_invalid_policy_and_protected_overwrite(
    identity: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant, actor = identity
    base = {
        "email": "Customer@example.com",
        "scope": "marketing",
        "reason": "manual",
        "source": "administrator",
    }
    for override, field in [
        ({"scope": "disabled"}, "scope"),
        ({"reason": "disabled"}, "reason"),
        ({"source": "disabled"}, "source"),
        ({"reason": "unsubscribe", "expires_at": timezone.now() + timedelta(days=1)}, "expires_at"),
    ]:
        with pytest.raises(ValidationError) as exc:
            ComplianceService.suppress(tenant, actor, {**base, **override})
        assert field in exc.value.detail

    protected = ComplianceService.suppress(tenant, actor, {**base, "reason": "complaint", "source": "provider_event"})
    assert protected.reason == "complaint"
    with pytest.raises(DomainConflict):
        ComplianceService.suppress(tenant, actor, base)

    with pytest.raises(ValidationError) as reason_error:
        ComplianceService.deactivate_suppression(tenant, protected.id, actor, " ")
    assert "reason" in reason_error.value.detail


def test_send_request_requires_current_preflight_and_queues_eligible_recipients(
    identity: tuple[uuid.UUID, uuid.UUID],
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, actor = identity
    campaign = prepare_sendable_campaign(tenant, actor, settings, monkeypatch)
    preflight = CampaignService.preflight(tenant, campaign.id)

    with pytest.raises(DomainConflict, match="preflight receipt"):
        CampaignService.request_send(tenant, campaign.id, actor, "send-without-receipt")

    job = CampaignService.request_send(tenant, campaign.id, actor, "send-once", preflight.receipt)
    replay = CampaignService.request_send(tenant, campaign.id, actor, "send-once", preflight.receipt)

    campaign.refresh_from_db()
    recipient = CampaignRecipient.objects.get(tenant_id=tenant, campaign=campaign)
    assert replay.id == job.id
    assert campaign.status == "queueing"
    assert campaign.content_snapshot_subject == campaign.subject
    assert recipient.status == "queued"
    assert Quota.objects.get(tenant_id=tenant, resource="email_marketing.monthly_recipients").remaining == 24


def test_delivery_job_starts_campaign_and_provider_acceptance_is_durable(
    identity: tuple[uuid.UUID, uuid.UUID],
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, actor = identity
    campaign = prepare_sendable_campaign(tenant, actor, settings, monkeypatch)
    preflight = CampaignService.preflight(tenant, campaign.id)
    send_job = CampaignService.request_send(tenant, campaign.id, actor, "send-provider-accepted", preflight.receipt)

    result = DeliveryService.process_campaign_job(send_job)
    campaign.refresh_from_db()
    recipient = CampaignRecipient.objects.get(tenant_id=tenant, campaign=campaign)
    attempt_result = DeliveryService.submit_recipient(tenant, recipient.id, uuid.uuid4())
    replay = DeliveryService.submit_recipient(tenant, recipient.id, attempt_result.value.job_id)

    campaign.refresh_from_db()
    recipient.refresh_from_db()
    attempt = DeliveryAttempt.objects.get(tenant_id=tenant, recipient=recipient)
    assert result["queued_count"] == 1
    assert campaign.status == "sent"
    assert campaign.completed_at is not None
    assert recipient.status == "accepted"
    assert attempt.status == "accepted"
    assert attempt.provider_message_id.startswith("provider-")
    assert DeliveryEvent.objects.filter(tenant_id=tenant, recipient=recipient, event_type="accepted").exists()
    assert replay.code == "idempotent_attempt"


def test_delivery_provider_timeout_records_retryable_failure(
    identity: tuple[uuid.UUID, uuid.UUID],
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, actor = identity
    campaign = prepare_sendable_campaign(tenant, actor, settings, monkeypatch, gateway=FailingGateway())
    preflight = CampaignService.preflight(tenant, campaign.id)
    send_job = CampaignService.request_send(tenant, campaign.id, actor, "send-provider-timeout", preflight.receipt)
    DeliveryService.process_campaign_job(send_job)
    recipient = CampaignRecipient.objects.get(tenant_id=tenant, campaign_id=campaign.id)

    result = DeliveryService.submit_recipient(tenant, recipient.id, uuid.uuid4())

    recipient.refresh_from_db()
    attempt = DeliveryAttempt.objects.get(tenant_id=tenant, recipient=recipient)
    campaign.refresh_from_db()
    assert not result.successful
    assert result.retryable and result.ambiguous
    assert attempt.status == "timed_out"
    assert recipient.status == "failed"
    assert recipient.last_error_code == "temporary_gateway_failure"
    assert campaign.failed_count == 1


def test_retry_recipient_requires_failed_or_deferred_evidence(
    identity: tuple[uuid.UUID, uuid.UUID],
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, actor = identity
    campaign = prepare_sendable_campaign(tenant, actor, settings, monkeypatch, gateway=FailingGateway())
    preflight = CampaignService.preflight(tenant, campaign.id)
    send_job = CampaignService.request_send(tenant, campaign.id, actor, "send-for-retry", preflight.receipt)
    DeliveryService.process_campaign_job(send_job)
    recipient = CampaignRecipient.objects.get(tenant_id=tenant, campaign=campaign)

    with pytest.raises(DomainConflict):
        DeliveryService.retry_recipient(tenant, recipient.id, actor, "retry-before-failure")

    DeliveryService.submit_recipient(tenant, recipient.id, uuid.uuid4())
    retry_job = DeliveryService.retry_recipient(tenant, recipient.id, actor, "retry-after-failure")

    assert retry_job.command == "email_marketing.send_recipient"
    assert retry_job.payload["recipient_id"] == str(recipient.id)
    assert retry_job.payload["retry"] is True


def test_reconcile_ambiguous_attempt_success_and_unavailable_paths(
    identity: tuple[uuid.UUID, uuid.UUID],
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, actor = identity
    campaign = prepare_sendable_campaign(tenant, actor, settings, monkeypatch, gateway=FailingGateway())
    preflight = CampaignService.preflight(tenant, campaign.id)
    send_job = CampaignService.request_send(tenant, campaign.id, actor, "send-for-reconcile", preflight.receipt)
    DeliveryService.process_campaign_job(send_job)
    recipient = CampaignRecipient.objects.get(tenant_id=tenant, campaign=campaign)
    DeliveryService.submit_recipient(tenant, recipient.id, uuid.uuid4())
    attempt = DeliveryAttempt.objects.get(tenant_id=tenant, recipient=recipient)
    attempt.provider_message_id = "provider-timeout"
    attempt.status = "failed"
    attempt.save(update_fields=["provider_message_id", "status", "updated_at"])

    failed = DeliveryService.reconcile_ambiguous_attempt(tenant, attempt.id)
    assert failed.code == "not_reconcilable"
    attempt.status = "timed_out"
    attempt.save(update_fields=["status", "updated_at"])
    receipt = DeliveryReceipt(
        provider_message_id="provider-timeout",
        gateway_key=attempt.gateway_key,
        acknowledgement="delivered",
        accepted_at=timezone.now(),
        evidence={"provider_status": "delivered"},
    )
    monkeypatch.setattr(
        adapters, "get_delivery_gateway", lambda key="django": LookupGateway(OperationResult.success(receipt))
    )

    reconciled = DeliveryService.reconcile_ambiguous_attempt(tenant, attempt.id)
    attempt.refresh_from_db()
    assert reconciled.code == "reconciled"
    assert attempt.status == "delivered"
    assert attempt.response_evidence == {"provider_status": "delivered"}

    attempt.status = "timed_out"
    attempt.save(update_fields=["status", "updated_at"])
    monkeypatch.setattr(
        adapters,
        "get_delivery_gateway",
        lambda key="django": LookupGateway(OperationResult.failure("lookup_down", retryable=True, ambiguous=True)),
    )
    unavailable = DeliveryService.reconcile_ambiguous_attempt(tenant, attempt.id)
    assert unavailable.code == "lookup_down"
    assert unavailable.retryable and unavailable.ambiguous


def test_submit_recipient_rejects_gateway_acknowledgement_outside_tenant_contract(
    identity: tuple[uuid.UUID, uuid.UUID],
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, actor = identity
    campaign = prepare_sendable_campaign(tenant, actor, settings, monkeypatch, gateway=InvalidAcknowledgementGateway())
    preflight = CampaignService.preflight(tenant, campaign.id)
    send_job = CampaignService.request_send(tenant, campaign.id, actor, "send-invalid-ack", preflight.receipt)
    DeliveryService.process_campaign_job(send_job)
    recipient = CampaignRecipient.objects.get(tenant_id=tenant, campaign=campaign)

    result = DeliveryService.submit_recipient(tenant, recipient.id, uuid.uuid4())

    recipient.refresh_from_db()
    attempt = DeliveryAttempt.objects.get(tenant_id=tenant, recipient=recipient)
    assert result.code == "invalid_gateway_acknowledgement"
    assert attempt.status == "failed"
    assert recipient.status == "failed"


def test_delivery_instrumentation_rewrites_only_safe_http_links(settings) -> None:
    settings.SARAISE_MODE = "development"
    rendered = adapters.RenderedEmail(
        subject="Subject",
        html='<a href="https://example.test/path?a=1">safe</a><a href="mailto:a@example.test">mail</a>',
        text="Plain",
        preview_text="Preview",
    )

    instrumented = DeliveryService._instrument_rendered(rendered, "https://public.example.test", "track token")

    assert "/api/v2/email-marketing/t/track%20token/click/" in instrumented.html
    assert "destination=" in instrumented.html
    assert 'href="mailto:a@example.test"' in instrumented.html
    assert "/api/v2/email-marketing/t/track%20token/open.gif" in instrumented.html
    assert instrumented.subject == rendered.subject
    assert instrumented.text == rendered.text


def test_provider_event_recording_is_idempotent_and_updates_recipient_truth(
    identity: tuple[uuid.UUID, uuid.UUID],
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, actor = identity
    campaign = prepare_sendable_campaign(tenant, actor, settings, monkeypatch)
    preflight = CampaignService.preflight(tenant, campaign.id)
    send_job = CampaignService.request_send(tenant, campaign.id, actor, "send-provider-event", preflight.receipt)
    DeliveryService.process_campaign_job(send_job)
    recipient = CampaignRecipient.objects.get(tenant_id=tenant, campaign=campaign)
    DeliveryService.submit_recipient(tenant, recipient.id, uuid.uuid4())
    attempt = DeliveryAttempt.objects.get(tenant_id=tenant, recipient=recipient)
    attempt.provider_message_id = VerifiedProviderEvent.provider_message_id
    attempt.save(update_fields=["provider_message_id", "updated_at"])

    event = DeliveryService.record_provider_event(tenant, "django", VerifiedProviderEvent())
    replay = DeliveryService.record_provider_event(tenant, "django", VerifiedProviderEvent())

    recipient.refresh_from_db()
    campaign.refresh_from_db()
    assert replay.id == event.id
    assert event.event_type == "delivered"
    assert recipient.status == "delivered"
    assert campaign.delivered_count == 1


def test_campaign_analytics_reports_truth_rates_and_counter_drift(identity: tuple[uuid.UUID, uuid.UUID]) -> None:
    tenant, actor = identity
    template = EmailTemplate.objects.create(
        tenant_id=tenant,
        template_code="ANALYTICS",
        template_name="Analytics",
        subject="Analytics",
        body_html="<p>Analytics</p>",
        design_json={},
    )
    campaign = CampaignService.create_campaign(
        tenant,
        actor,
        {
            "campaign_code": "analytics",
            "campaign_name": "Analytics",
            "template_id": template.id,
            "subject": "Analytics",
            "from_name": "SARAISE",
            "from_email": "analytics@example.com",
            "audience_definition": {"schema_version": 1, "resolver": "manual", "recipients": []},
            "timezone": "UTC",
        },
    )
    campaign.sent_count = 10
    campaign.delivered_count = 7
    campaign.unique_opened_count = 4
    campaign.unique_clicked_count = 2
    campaign.bounced_count = 1
    campaign.save()
    accepted, delivered, bounced = CampaignRecipient.objects.bulk_create(
        [
            CampaignRecipient(tenant_id=tenant, campaign=campaign, email="a@example.com", status="accepted"),
            CampaignRecipient(tenant_id=tenant, campaign=campaign, email="d@example.com", status="delivered"),
            CampaignRecipient(tenant_id=tenant, campaign=campaign, email="b@example.com", status="bounced"),
        ]
    )
    DeliveryEvent.objects.create(
        tenant_id=tenant,
        recipient=delivered,
        gateway_key="django",
        provider_event_id="open-1",
        event_type="opened",
        occurred_at=timezone.now(),
        correlation_id="analytics-open",
    )
    DeliveryEvent.objects.create(
        tenant_id=tenant,
        recipient=delivered,
        gateway_key="django",
        provider_event_id="click-1",
        event_type="clicked",
        occurred_at=timezone.now(),
        correlation_id="analytics-click",
    )

    analytics = CampaignService.get_campaign_analytics(tenant, campaign.id)

    assert accepted.id
    assert analytics.accepted == 3
    assert analytics.delivered == 1
    assert analytics.bounced == 1
    assert analytics.delivery_rate == pytest.approx(1 / 3)
    assert analytics.open_rate == 1
    assert analytics.click_rate == 1
    assert analytics.bounce_rate == pytest.approx(1 / 3)
    assert analytics.counter_drift["sent_count"] == 7
    assert analytics.counter_drift["delivered_count"] == 6


def test_audience_duplicate_and_recheck_paths_are_tenant_safe(identity: tuple[uuid.UUID, uuid.UUID]) -> None:
    tenant, actor = identity
    template = TemplateService.create_template(tenant, actor, template_data())
    campaign = CampaignService.create_campaign(tenant, actor, campaign_data(template))
    CampaignRecipient.objects.create(
        tenant_id=tenant,
        campaign=campaign,
        email="Customer@example.com",
        status="resolved",
        resolved_at=timezone.now(),
    )

    duplicate = AudienceService.evaluate_recipient(
        tenant,
        campaign.id,
        AudienceCandidate(email="Customer@EXAMPLE.COM", display_name="Duplicate"),
    )
    rechecked = AudienceService.recheck_before_send(
        tenant,
        CampaignRecipient.objects.get(tenant_id=tenant, campaign=campaign).id,
    )

    assert duplicate.eligible is False
    assert duplicate.code == "DUPLICATE"
    assert rechecked.eligible is False
    assert rechecked.code == "CONSENT_NOT_GRANTED"
    with pytest.raises(NotFound):
        AudienceService.recheck_before_send(tenant, uuid.uuid4())


def test_enqueue_verified_provider_event_rejects_disabled_or_malformed_events(
    identity: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant, _ = identity

    with pytest.raises(ValidationError) as disabled:
        DeliveryService.enqueue_verified_provider_event(tenant, "disabled", VerifiedProviderEvent())
    assert "gateway_key" in disabled.value.detail

    malformed = type("Malformed", (), {"provider_event_id": "event-without-mapping"})()
    with pytest.raises(ValidationError) as invalid:
        DeliveryService.enqueue_verified_provider_event(tenant, "django", malformed)
    assert "event" in invalid.value.detail

    empty = type("Empty", (), {"provider_event_id": "", "as_mapping": lambda self: {}})()
    with pytest.raises(ValidationError) as missing:
        DeliveryService.enqueue_verified_provider_event(tenant, "django", empty)
    assert "provider_event_id" in missing.value.detail

    job = DeliveryService.enqueue_verified_provider_event(tenant, "django", VerifiedProviderEvent())
    assert job.command == "email_marketing.process_provider_event"
    assert job.idempotency_key == "provider-event:django:provider-event-1"


def test_record_consent_idempotency_replays_and_rejects_key_reuse(
    identity: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant, actor = identity
    payload = {
        "email": "Customer@example.com",
        "purpose": "marketing",
        "status": "granted",
        "lawful_basis": "consent",
        "source": "api",
        "notice_version": "v1",
        "ignored_client_field": "must not enter the domain record",
    }

    created = ComplianceService.record_consent(
        tenant,
        actor,
        payload,
        capture_context={"remote_addr": "203.0.113.5", "user_agent": "pytest"},
        idempotency_key="consent-key-1",
    )
    replayed = ComplianceService.record_consent(
        tenant,
        actor,
        payload,
        capture_context={"remote_addr": "198.51.100.7"},
        idempotency_key="consent-key-1",
    )

    assert replayed.id == created.id
    assert created.ip_hash
    assert created.user_agent_hash
    assert created.evidence == {
        "capture_channel": "authenticated_api",
        "network_evidence_present": True,
        "user_agent_evidence_present": True,
    }
    assert not hasattr(created, "ignored_client_field")

    changed = {**payload, "status": "revoked"}
    with pytest.raises(DomainConflict, match="different request"):
        ComplianceService.record_consent(tenant, actor, changed, idempotency_key="consent-key-1")


def test_tenant_json_validation_uses_runtime_limits_not_static_padding(
    identity: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant, _ = identity
    configuration = ConfigurationService.current(tenant)
    document = configuration.document
    document["limits"]["serializer_json_max_depth"] = 1
    document["limits"]["serializer_json_max_keys"] = 1
    document["limits"]["json_key_max_length"] = 4
    document["limits"]["serializer_json_max_bytes"] = 32
    configuration.document = document
    configuration.save(update_fields=["document", "updated_at"])

    with pytest.raises(ValidationError) as nested:
        _validate_tenant_json(tenant, {"root": {"child": "value"}}, "serializer_json_max_bytes", "payload")
    assert "nesting" in str(nested.value.detail["payload"])

    with pytest.raises(ValidationError) as keys:
        _validate_tenant_json(tenant, {"a": 1, "b": 2}, "serializer_json_max_bytes", "payload")
    assert "key limit" in str(keys.value.detail["payload"])

    with pytest.raises(ValidationError) as key_length:
        _validate_tenant_json(tenant, {"oversized": 1}, "serializer_json_max_bytes", "payload")
    assert "oversized key" in str(key_length.value.detail["payload"])

    with pytest.raises(ValidationError) as bytes_error:
        _validate_tenant_json(tenant, {"a": "x" * 64}, "serializer_json_max_bytes", "payload")
    assert "byte limit" in str(bytes_error.value.detail["payload"])
