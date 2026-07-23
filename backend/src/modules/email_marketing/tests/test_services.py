"""Service-level evidence for tenant, consent, lifecycle, and idempotency rules."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.modules.email_marketing.models import CampaignRecipient, EmailTemplate
from src.modules.email_marketing.services import (
    AudienceService,
    CampaignService,
    ComplianceService,
    DomainConflict,
    TemplateService,
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
