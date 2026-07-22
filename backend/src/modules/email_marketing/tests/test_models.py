"""Persistence and lifecycle contract tests for email marketing."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from src.core.state_machine import GuardFailedError, TerminalStateError
from src.modules.email_marketing.models import (
    BoundedJSONValidator,
    CampaignRecipient,
    CampaignStatus,
    ConsentRecord,
    DeliveryAttempt,
    DeliveryEvent,
    EmailCampaign,
    EmailTemplate,
    ImmutableEvidenceError,
    RecipientStatus,
    SuppressionEntry,
    TemplateStatus,
    normalize_email_address,
)
from src.modules.email_marketing.state_machines import (
    CAMPAIGN_STATE_MACHINE,
    RECIPIENT_STATE_MACHINE,
    TEMPLATE_STATE_MACHINE,
)

pytestmark = pytest.mark.django_db


def _template(tenant_id: uuid.UUID, code: str = "welcome") -> EmailTemplate:
    return EmailTemplate.objects.create(
        tenant_id=tenant_id,
        template_code=code,
        template_name="Welcome",
        subject="Hello {{ name }}",
        body_html="<p>Hello {{ name }}</p>",
        design_json={},
    )


def _campaign(
    tenant_id: uuid.UUID,
    *,
    code: str = "launch",
    template: EmailTemplate | None = None,
) -> EmailCampaign:
    return EmailCampaign.objects.create(
        tenant_id=tenant_id,
        campaign_code=code,
        campaign_name="Launch",
        subject="Launch announcement",
        from_name="SARAISE",
        from_email="Team@EXAMPLE.COM",
        audience_definition={},
        template=template,
    )


def _consent(tenant_id: uuid.UUID, email: str = "User@EXAMPLE.COM") -> ConsentRecord:
    return ConsentRecord.objects.create(
        tenant_id=tenant_id,
        email=email,
        purpose="marketing",
        status="granted",
        lawful_basis="consent",
        source="form",
        notice_version="2026-01",
        captured_at=timezone.now(),
        evidence={},
    )


def _recipient(
    tenant_id: uuid.UUID,
    campaign: EmailCampaign,
    *,
    email: str = "User@EXAMPLE.COM",
    consent: ConsentRecord | None = None,
) -> CampaignRecipient:
    return CampaignRecipient.objects.create(
        tenant_id=tenant_id,
        campaign=campaign,
        email=email,
        consent_record=consent,
        personalization_data={},
        resolved_at=timezone.now(),
    )


def _metadata(actor: uuid.UUID | None = None) -> dict[str, str | None]:
    return {"actor_id": str(actor or uuid.uuid4()), "correlation_id": str(uuid.uuid4())}


def test_mutable_model_defaults_normalization_and_string_representations() -> None:
    tenant_id = uuid.uuid4()
    template = _template(tenant_id)
    campaign = _campaign(tenant_id, template=template)

    assert template.template_code == "WELCOME"
    assert template.status == TemplateStatus.DRAFT
    assert template.version == 1
    assert template.usage_count == 0
    assert template.is_active is False
    assert template.is_deleted is False
    assert str(template) == "WELCOME - Welcome"

    assert campaign.campaign_code == "LAUNCH"
    assert campaign.status == CampaignStatus.DRAFT
    assert campaign.campaign_type == "broadcast"
    assert campaign.audience_resolver_key == "manual"
    assert campaign.gateway_key == "django"
    assert campaign.timezone == "UTC"
    assert campaign.from_email == "Team@example.com"
    assert all(getattr(campaign, field) == 0 for field in campaign.COUNTER_FIELDS)
    assert campaign.transition_history == []
    assert str(campaign) == "LAUNCH - Launch"


def test_every_tenant_field_is_an_indexed_non_null_uuid() -> None:
    for model in (
        EmailCampaign,
        EmailTemplate,
        CampaignRecipient,
        DeliveryAttempt,
        DeliveryEvent,
        SuppressionEntry,
        ConsentRecord,
    ):
        field = model._meta.get_field("tenant_id")
        assert field.get_internal_type() == "UUIDField"
        assert field.null is False
        assert field.db_index is True


def test_email_normalization_preserves_local_part_and_validates() -> None:
    assert normalize_email_address(" Customer.Tag@EXAMPLE.COM ") == "Customer.Tag@example.com"
    with pytest.raises(ValidationError):
        normalize_email_address("not-an-email")


def test_invalid_timezone_and_active_template_content_are_rejected() -> None:
    tenant_id = uuid.uuid4()
    campaign = _campaign(tenant_id)
    campaign.timezone = "Mars/Olympus"
    with pytest.raises(ValidationError):
        campaign.full_clean()

    template = _template(tenant_id, "empty")
    template.status = TemplateStatus.ACTIVE
    template.subject = ""
    template.body_html = ""
    template.body_text = ""
    with pytest.raises(ValidationError):
        template.full_clean()


def test_versioned_json_accepts_unset_draft_default_but_rejects_unversioned_content() -> None:
    validator = BoundedJSONValidator(max_bytes=1024, require_version=True)
    validator({})
    validator({"version": 1, "resolver": "manual"})
    with pytest.raises(ValidationError, match="schema version"):
        validator({"resolver": "manual"})


def test_conditional_campaign_and_template_uniqueness_allows_reuse_after_soft_delete() -> None:
    tenant_id = uuid.uuid4()
    campaign = _campaign(tenant_id, code="monthly")
    with pytest.raises((ValidationError, IntegrityError)), transaction.atomic():
        _campaign(tenant_id, code="MONTHLY")
    campaign.is_deleted = True
    campaign.deleted_at = timezone.now()
    campaign.save()
    assert _campaign(tenant_id, code="MONTHLY").pk

    template = _template(tenant_id, "receipt")
    with pytest.raises((ValidationError, IntegrityError)), transaction.atomic():
        _template(tenant_id, "RECEIPT")
    template.is_deleted = True
    template.deleted_at = timezone.now()
    template.save()
    assert _template(tenant_id, "RECEIPT").pk


def test_campaign_schedule_and_completion_checks_are_enforced() -> None:
    tenant_id = uuid.uuid4()
    with pytest.raises((ValidationError, IntegrityError)), transaction.atomic():
        EmailCampaign.objects.create(
            tenant_id=tenant_id,
            campaign_code="scheduled",
            campaign_name="Scheduled",
            subject="Subject",
            from_name="Sender",
            from_email="sender@example.com",
            audience_definition={},
            status=CampaignStatus.SCHEDULED,
        )

    campaign = _campaign(tenant_id, code="sent")
    campaign.status = CampaignStatus.SENT
    with pytest.raises(ValidationError):
        campaign.save()


def test_cross_tenant_relationships_are_rejected_at_model_boundary() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    template_b = _template(tenant_b)
    campaign = _campaign(tenant_a)
    campaign.template = template_b
    with pytest.raises(ValidationError, match="referenced record"):
        campaign.full_clean()

    consent_b = _consent(tenant_b)
    recipient = CampaignRecipient(
        tenant_id=tenant_a,
        campaign=campaign,
        email=consent_b.email,
        consent_record=consent_b,
    )
    with pytest.raises(ValidationError, match="referenced record"):
        recipient.full_clean()


def test_consent_supersession_requires_same_identity() -> None:
    tenant_id = uuid.uuid4()
    previous = _consent(tenant_id, "first@example.com")
    replacement = ConsentRecord(
        tenant_id=tenant_id,
        email="second@example.com",
        purpose="marketing",
        status="revoked",
        lawful_basis="consent",
        source="unsubscribe",
        notice_version="2026-01",
        captured_at=timezone.now(),
        supersedes=previous,
        evidence={},
    )
    with pytest.raises(ValidationError, match="same email and purpose"):
        replacement.full_clean()


def test_delivery_attempt_and_event_relationships_are_tenant_safe() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    campaign = _campaign(tenant_a)
    recipient = _recipient(tenant_a, campaign)
    attempt = DeliveryAttempt(
        tenant_id=tenant_b,
        recipient=recipient,
        attempt_number=1,
        job_id=uuid.uuid4(),
        idempotency_key="job:one",
        gateway_key="django",
    )
    with pytest.raises(ValidationError, match="referenced record"):
        attempt.full_clean()

    saved_attempt = DeliveryAttempt.objects.create(
        tenant_id=tenant_a,
        recipient=recipient,
        attempt_number=1,
        job_id=uuid.uuid4(),
        idempotency_key="job:one",
        gateway_key="django",
    )
    other = _recipient(tenant_a, campaign, email="other@example.com")
    event = DeliveryEvent(
        tenant_id=tenant_a,
        recipient=other,
        attempt=saved_attempt,
        gateway_key="django",
        provider_event_id="evt-1",
        event_type="delivered",
        occurred_at=timezone.now(),
        correlation_id=str(uuid.uuid4()),
    )
    with pytest.raises(ValidationError, match="Attempt must belong"):
        event.full_clean()


def test_append_only_consent_and_delivery_events_reject_instance_and_queryset_mutation() -> None:
    tenant_id = uuid.uuid4()
    consent = _consent(tenant_id)
    consent.status = "revoked"
    with pytest.raises(ImmutableEvidenceError):
        consent.save()
    with pytest.raises(ImmutableEvidenceError):
        ConsentRecord.objects.filter(pk=consent.pk).update(status="revoked")
    with pytest.raises(ImmutableEvidenceError):
        consent.delete()

    campaign = _campaign(tenant_id)
    recipient = _recipient(tenant_id, campaign, email="event@example.com")
    event = DeliveryEvent.objects.create(
        tenant_id=tenant_id,
        recipient=recipient,
        gateway_key="tracking",
        provider_event_id="open-1",
        event_type="opened",
        occurred_at=timezone.now(),
        correlation_id=str(uuid.uuid4()),
        metadata={"source": "tracking"},
    )
    event.metadata = {"source": "changed"}
    with pytest.raises(ImmutableEvidenceError):
        event.save()
    with pytest.raises(ImmutableEvidenceError):
        DeliveryEvent.objects.filter(pk=event.pk).delete()


def test_suppression_validation_and_active_uniqueness() -> None:
    tenant_id = uuid.uuid4()
    entry = SuppressionEntry.objects.create(
        tenant_id=tenant_id,
        email="User@EXAMPLE.COM",
        scope="marketing",
        reason="unsubscribe",
        source="user",
    )
    assert entry.email == "User@example.com"
    with pytest.raises((ValidationError, IntegrityError)), transaction.atomic():
        SuppressionEntry.objects.create(
            tenant_id=tenant_id,
            email="User@example.com",
            scope="marketing",
            reason="manual",
            source="administrator",
        )
    entry.active = False
    entry.deactivated_at = timezone.now()
    entry.save()
    assert SuppressionEntry.objects.create(
        tenant_id=tenant_id,
        email="User@example.com",
        scope="marketing",
        reason="manual",
        source="administrator",
    ).pk

    permanent = SuppressionEntry(
        tenant_id=tenant_id,
        email="other@example.com",
        scope="all",
        reason="legal",
        source="administrator",
        expires_at=timezone.now() + timedelta(days=1),
    )
    with pytest.raises(ValidationError, match="cannot expire"):
        permanent.full_clean()


def test_campaign_queue_guard_requires_every_preflight_fact() -> None:
    tenant_id = uuid.uuid4()
    campaign = _campaign(tenant_id)
    with pytest.raises(GuardFailedError):
        CAMPAIGN_STATE_MACHINE.apply(
            campaign,
            "queue_send",
            tenant_id=tenant_id,
            transition_key="send-1",
            context={},
            metadata=_metadata(),
        )

    consent = _consent(tenant_id, "eligible@example.com")
    _recipient(tenant_id, campaign, email="eligible@example.com", consent=consent)
    campaign.audience_snapshot_at = timezone.now()
    campaign.resolved_recipient_count = 1
    campaign.content_snapshot_subject = "Subject"
    campaign.content_snapshot_html = "<p>Body</p>"
    campaign.save()
    transitioned = CAMPAIGN_STATE_MACHINE.apply(
        campaign,
        "queue_send",
        tenant_id=tenant_id,
        transition_key="send-2",
        context={
            "entitlement_available": True,
            "quota_available": True,
            "consent_evaluated": True,
        },
        metadata=_metadata(),
    )
    assert transitioned.status == CampaignStatus.QUEUEING
    assert transitioned.transition_history[-1]["command"] == "queue_send"


def test_terminal_campaign_and_template_states_are_immutable() -> None:
    tenant_id = uuid.uuid4()
    campaign = _campaign(tenant_id)
    cancelled = CAMPAIGN_STATE_MACHINE.apply(
        campaign,
        "cancel",
        tenant_id=tenant_id,
        transition_key="cancel-1",
        metadata=_metadata(),
    )
    with pytest.raises(TerminalStateError):
        CAMPAIGN_STATE_MACHINE.apply(
            cancelled,
            "cancel",
            tenant_id=tenant_id,
            transition_key="cancel-2",
            metadata=_metadata(),
        )
    with pytest.raises(ValidationError, match="physically deleted"):
        EmailCampaign.objects.filter(pk=campaign.pk).delete()
    with pytest.raises(ValidationError, match="state machine"):
        EmailCampaign.objects.filter(pk=campaign.pk).update(status=CampaignStatus.DRAFT)

    template = _template(tenant_id, "archive")
    archived = TEMPLATE_STATE_MACHINE.apply(
        template,
        "archive",
        tenant_id=tenant_id,
        transition_key="archive-1",
        metadata=_metadata(),
    )
    archived.body_html = "<p>Changed</p>"
    with pytest.raises(ValidationError, match="immutable"):
        archived.save()
    with pytest.raises(ValidationError, match="immutable"):
        EmailTemplate.objects.filter(pk=archived.pk).update(body_html="<p>Bulk change</p>")


def test_recipient_transitions_require_attempt_evidence_and_do_not_regress_terminal_state() -> None:
    tenant_id = uuid.uuid4()
    campaign = _campaign(tenant_id)
    recipient = _recipient(tenant_id, campaign)
    DeliveryAttempt.objects.create(
        tenant_id=tenant_id,
        recipient=recipient,
        attempt_number=1,
        job_id=uuid.uuid4(),
        idempotency_key="recipient-attempt",
        gateway_key="django",
    )
    recipient = RECIPIENT_STATE_MACHINE.apply(
        recipient,
        "queue",
        tenant_id=tenant_id,
        transition_key="recipient-queue",
        metadata=_metadata(),
    )
    recipient = RECIPIENT_STATE_MACHINE.apply(
        recipient,
        "start_send",
        tenant_id=tenant_id,
        transition_key="recipient-start",
        metadata=_metadata(),
    )
    recipient = RECIPIENT_STATE_MACHINE.apply(
        recipient,
        "accepted",
        tenant_id=tenant_id,
        transition_key="recipient-accepted",
        metadata=_metadata(),
    )
    recipient = RECIPIENT_STATE_MACHINE.apply(
        recipient,
        "delivered",
        tenant_id=tenant_id,
        transition_key="recipient-delivered",
        metadata=_metadata(),
    )
    recipient = RECIPIENT_STATE_MACHINE.apply(
        recipient,
        "complain",
        tenant_id=tenant_id,
        transition_key="recipient-complained",
        metadata=_metadata(),
    )
    assert recipient.status == RecipientStatus.COMPLAINED
    with pytest.raises(TerminalStateError):
        RECIPIENT_STATE_MACHINE.apply(
            recipient,
            "queue",
            tenant_id=tenant_id,
            transition_key="recipient-regression",
            metadata=_metadata(),
        )
