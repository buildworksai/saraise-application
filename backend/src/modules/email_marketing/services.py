"""Transactional business authority for the email-marketing runtime.

Controllers and workers deliberately share these services.  This keeps tenant
ownership, lifecycle, consent, quota, provider evidence, and idempotency rules
identical regardless of how an operation enters the system.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence
from urllib.parse import quote, urlparse
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from rest_framework.exceptions import APIException, NotFound, ValidationError

from src.core.access.entitlements import EntitlementService, Quota, QuotaService
from src.core.async_jobs.models import AsyncJob, JobStatus, OutboxEvent
from src.core.async_jobs.services import enqueue, transition
from src.core.middleware.correlation import get_correlation_id

from .models import (
    CampaignRecipient,
    ConsentRecord,
    DeliveryAttempt,
    DeliveryEvent,
    EmailCampaign,
    EmailTemplate,
    SuppressionEntry,
)
from .adapters import OperationResult
from .state_machines import CAMPAIGN_STATE_MACHINE, RECIPIENT_STATE_MACHINE, TEMPLATE_STATE_MACHINE

logger = logging.getLogger("saraise.email_marketing")
SYSTEM_ACTOR_ID = uuid5(NAMESPACE_URL, "saraise:email-marketing:system")


class DomainConflict(APIException):
    status_code = 409
    default_detail = "The operation conflicts with the current resource state."
    default_code = "conflict"


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    eligible: bool
    code: str
    reason: str
    consent_record_id: UUID | None = None
    suppression_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AudienceCandidate:
    email: str
    display_name: str = ""
    recipient_key: str | None = None
    personalization_data: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class AudienceResolutionResult:
    candidates: tuple[AudienceCandidate, ...]
    evidence: Mapping[str, object]
    resolver_key: str = "manual"


@dataclass(frozen=True, slots=True)
class CampaignPreflight:
    campaign_id: UUID
    generated_at: datetime
    receipt: str
    content_valid: bool
    sender_valid: bool
    audience_resolved: bool
    resolved_count: int
    eligible_count: int
    suppressed_count: int
    consent_failure_count: int
    suppression_failure_count: int
    quota_required: int
    quota_remaining: int
    quota_available: bool
    entitlement_available: bool
    schedule_valid: bool
    gateway_status: str
    blockers: tuple[Mapping[str, str], ...]
    consequences: Mapping[str, str]

    @property
    def ready(self) -> bool:
        return not self.blockers

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["ready"] = self.ready
        return value


@dataclass(frozen=True, slots=True)
class CampaignAnalytics:
    campaign_id: UUID
    resolved: int
    eligible: int
    suppressed: int
    accepted: int
    delivered: int
    unique_opened: int
    unique_clicked: int
    bounced: int
    failed: int
    unsubscribed: int
    complained: int
    delivery_rate: float
    open_rate: float
    click_rate: float
    bounce_rate: float
    counter_drift: Mapping[str, int]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_email(value: str) -> str:
    """Validate an address and lowercase only its DNS domain."""

    if not isinstance(value, str) or "@" not in value:
        raise ValidationError({"email": "A valid email address is required."})
    address = value.strip()
    try:
        validate_email(address)
    except DjangoValidationError as exc:
        raise ValidationError({"email": "A valid email address is required."}) from exc
    local, domain = address.rsplit("@", 1)
    return f"{local}@{domain.lower()}"


def _uuid(value: UUID | str, name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({name: "Must be a valid UUID."}) from exc


def _actor_metadata(actor_id: UUID | str | None, **extra: object) -> dict[str, object]:
    return {
        "actor_id": str(actor_id) if actor_id is not None else None,
        "correlation_id": get_correlation_id() or f"op_{uuid.uuid4().hex}",
        **extra,
    }


def _publish(
    event_type: str,
    tenant_id: UUID,
    aggregate_type: str,
    aggregate_id: UUID,
    *,
    actor_id: UUID | str | None,
    payload: Mapping[str, object],
    job_id: UUID | None = None,
    causation_id: str | None = None,
) -> OutboxEvent:
    """Persist a versioned domain event without depending on a broker."""

    from .events import publish_domain_event

    return publish_domain_event(
        event_type=event_type,
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor_id=actor_id,
        correlation_id=get_correlation_id() or f"evt_{uuid.uuid4().hex}",
        causation_id=causation_id,
        job_id=job_id,
        payload=dict(payload),
    )


def _apply_transition(
    machine: object,
    aggregate: object,
    command: str,
    tenant_id: UUID,
    key: str,
    actor_id: UUID | str | None,
    *,
    context: Mapping[str, object] | None = None,
) -> Any:
    if not key or not key.strip():
        raise ValidationError({"idempotency_key": "This field is required."})
    transitioned = machine.apply(  # type: ignore[attr-defined]
        aggregate,
        command,
        tenant_id=tenant_id,
        transition_key=key.strip(),
        context=dict(context or {}),
        metadata=_actor_metadata(actor_id),
    )
    transitioned.updated_at = timezone.now()
    transitioned.save(update_fields=["updated_at"])
    return transitioned


class CampaignService:
    editable_fields = frozenset(
        {
            "campaign_name",
            "description",
            "campaign_type",
            "template_id",
            "subject",
            "preview_text",
            "from_name",
            "from_email",
            "reply_to_email",
            "audience_definition",
            "timezone",
            "audience_resolver_key",
            "gateway_key",
            "verifier_key",
        }
    )

    @classmethod
    @transaction.atomic
    def create_campaign(cls, tenant_id: UUID, actor_id: UUID, data: Mapping[str, Any]) -> EmailCampaign:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        values = dict(data)
        values.pop("tenant_id", None)
        values.pop("status", None)
        template_id = values.pop("template_id", None)
        template = None
        if template_id is not None:
            template = EmailTemplate.objects.for_tenant(tenant).filter(pk=template_id, is_deleted=False).first()
            if template is None:
                raise ValidationError({"template_id": "Template does not exist for this tenant."})
        values["campaign_code"] = str(values.get("campaign_code", "")).strip().upper()
        if not values["campaign_code"]:
            raise ValidationError({"campaign_code": "This field is required."})
        values["from_email"] = normalize_email(str(values.get("from_email", "")))
        if values.get("reply_to_email"):
            values["reply_to_email"] = normalize_email(str(values["reply_to_email"]))
        cls._validate_timezone(str(values.get("timezone", "UTC")))
        cls._validate_audience_definition(values.get("audience_definition", {}))
        campaign = EmailCampaign(tenant_id=tenant, created_by=actor, updated_by=actor, template=template, **values)
        try:
            campaign.full_clean()
            campaign.save()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        _publish(
            "email_marketing.campaign.created.v1",
            tenant,
            "email_campaign",
            campaign.id,
            actor_id=actor,
            payload={"campaign_code": campaign.campaign_code, "status": campaign.status},
        )
        return campaign

    @classmethod
    @transaction.atomic
    def update_campaign(
        cls, tenant_id: UUID, campaign_id: UUID, actor_id: UUID, data: Mapping[str, Any]
    ) -> EmailCampaign:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        if campaign.status != "draft":
            raise DomainConflict("Only draft campaigns can be edited.")
        unknown = set(data) - cls.editable_fields
        if unknown:
            raise ValidationError({field: "This field is not editable." for field in sorted(unknown)})
        values = dict(data)
        if "template_id" in values:
            template_id = values.pop("template_id")
            if template_id is None:
                campaign.template = None
            else:
                template = EmailTemplate.objects.for_tenant(tenant).filter(pk=template_id, is_deleted=False).first()
                if template is None:
                    raise ValidationError({"template_id": "Template does not exist for this tenant."})
                campaign.template = template
        if "from_email" in values:
            values["from_email"] = normalize_email(str(values["from_email"]))
        if values.get("reply_to_email"):
            values["reply_to_email"] = normalize_email(str(values["reply_to_email"]))
        if "timezone" in values:
            cls._validate_timezone(str(values["timezone"]))
        if "audience_definition" in values:
            cls._validate_audience_definition(values["audience_definition"])
            campaign.audience_snapshot_at = None
        for field, value in values.items():
            setattr(campaign, field, value)
        campaign.updated_by = _uuid(actor_id, "actor_id")
        try:
            campaign.full_clean()
            campaign.save()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        return campaign

    @classmethod
    @transaction.atomic
    def archive_campaign(cls, tenant_id: UUID, campaign_id: UUID, actor_id: UUID) -> None:
        campaign = cls._locked_campaign(_uuid(tenant_id, "tenant_id"), campaign_id)
        if campaign.status not in {"draft", "failed"}:
            raise DomainConflict("Only draft or failed campaigns can be archived.")
        if campaign.recipients.filter(status__in={"queued", "sending", "accepted"}).exists():
            raise DomainConflict("A campaign with active delivery work cannot be archived.")
        campaign.is_deleted = True
        campaign.deleted_at = timezone.now()
        campaign.deleted_by = _uuid(actor_id, "actor_id")
        campaign.updated_by = campaign.deleted_by
        campaign.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_by", "updated_at"])

    @classmethod
    @transaction.atomic
    def schedule_campaign(
        cls,
        tenant_id: UUID,
        campaign_id: UUID,
        actor_id: UUID,
        scheduled_at: datetime,
        timezone_name: str,
        idempotency_key: str,
    ) -> EmailCampaign:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        cls._validate_schedule(scheduled_at, timezone_name)
        preflight = cls.preflight(tenant, campaign.id)
        critical = [item for item in preflight.blockers if item["code"] in {"CONTENT_INVALID", "SENDER_INVALID"}]
        if critical:
            raise DomainConflict({"preflight": critical})
        campaign.scheduled_at = scheduled_at
        campaign.timezone = timezone_name
        campaign.updated_by = _uuid(actor_id, "actor_id")
        campaign.save(update_fields=["scheduled_at", "timezone", "updated_by", "updated_at"])
        transitioned = _apply_transition(
            CAMPAIGN_STATE_MACHINE,
            campaign,
            "schedule",
            tenant,
            idempotency_key,
            actor_id,
        )
        _publish(
            "email_marketing.campaign.scheduled.v1",
            tenant,
            "email_campaign",
            campaign.id,
            actor_id=actor_id,
            payload={"scheduled_at": scheduled_at.isoformat(), "timezone": timezone_name},
        )
        return transitioned

    @classmethod
    @transaction.atomic
    def reschedule_campaign(
        cls,
        tenant_id: UUID,
        campaign_id: UUID,
        actor_id: UUID,
        scheduled_at: datetime,
        timezone_name: str,
        idempotency_key: str,
    ) -> EmailCampaign:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        cls._validate_schedule(scheduled_at, timezone_name)
        campaign.scheduled_at = scheduled_at
        campaign.timezone = timezone_name
        campaign.updated_by = _uuid(actor_id, "actor_id")
        campaign.save(update_fields=["scheduled_at", "timezone", "updated_by", "updated_at"])
        return _apply_transition(CAMPAIGN_STATE_MACHINE, campaign, "reschedule", tenant, idempotency_key, actor_id)

    @classmethod
    @transaction.atomic
    def unschedule_campaign(
        cls, tenant_id: UUID, campaign_id: UUID, actor_id: UUID, idempotency_key: str
    ) -> EmailCampaign:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        transitioned = _apply_transition(
            CAMPAIGN_STATE_MACHINE, campaign, "unschedule", tenant, idempotency_key, actor_id
        )
        transitioned.scheduled_at = None
        transitioned.updated_by = _uuid(actor_id, "actor_id")
        transitioned.save(update_fields=["scheduled_at", "updated_by", "updated_at"])
        return transitioned

    @classmethod
    @transaction.atomic
    def request_audience_resolution(
        cls, tenant_id: UUID, campaign_id: UUID, actor_id: UUID, idempotency_key: str
    ) -> AsyncJob:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        if campaign.status != "draft":
            raise DomainConflict("Audience can only be resolved for a draft campaign.")
        return enqueue(
            tenant,
            actor_id,
            "email_marketing.resolve_audience",
            {"campaign_id": str(campaign.id)},
            idempotency_key,
        )

    @classmethod
    @transaction.atomic
    def request_send(
        cls,
        tenant_id: UUID,
        campaign_id: UUID,
        actor_id: UUID,
        idempotency_key: str,
        preflight_receipt: str | None = None,
    ) -> AsyncJob:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        existing = AsyncJob.objects.for_tenant(tenant).filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing
        preflight = cls.preflight(tenant, campaign.id)
        if not preflight_receipt:
            raise DomainConflict("A current preflight receipt is required before sending.")
        try:
            submitted_preflight = signing.loads(
                preflight_receipt,
                salt="email_marketing.preflight",
                max_age=15 * 60,
            )
            current_preflight = signing.loads(preflight.receipt, salt="email_marketing.preflight")
        except signing.BadSignature as exc:
            raise DomainConflict("The preflight receipt is invalid or expired; run preflight again.") from exc
        if not constant_time_compare(str(submitted_preflight), str(current_preflight)):
            raise DomainConflict("The campaign changed after preflight; review the refreshed preflight before sending.")
        if not preflight.ready:
            raise DomainConflict({"preflight": list(preflight.blockers)})
        quota = QuotaService().consume(
            tenant, "email_marketing.monthly_recipients", cost=preflight.eligible_count
        )
        if not quota.allowed:
            raise DomainConflict("Recipient quota is insufficient.")
        cls._snapshot_content(campaign)
        campaign.queue_started_at = timezone.now()
        campaign.updated_by = _uuid(actor_id, "actor_id")
        campaign.save()
        transitioned = _apply_transition(
            CAMPAIGN_STATE_MACHINE,
            campaign,
            "queue_send",
            tenant,
            idempotency_key,
            actor_id,
            context={
                "preflight_ready": True,
                "entitlement_available": preflight.entitlement_available,
                "quota_available": True,
                "consent_evaluated": True,
            },
        )
        for recipient in CampaignRecipient.objects.select_for_update().filter(
            tenant_id=tenant, campaign=transitioned, status="resolved"
        ):
            queued_recipient = _apply_transition(
                RECIPIENT_STATE_MACHINE,
                recipient,
                "queue",
                tenant,
                f"queue:{idempotency_key}:{recipient.id}",
                actor_id,
            )
            queued_recipient.queued_at = timezone.now()
            queued_recipient.save(update_fields=["queued_at", "updated_at"])
        job = enqueue(
            tenant,
            actor_id,
            "email_marketing.send_campaign",
            {"campaign_id": str(campaign.id), "preflight_receipt": preflight.receipt},
            idempotency_key,
        )
        _publish(
            "email_marketing.campaign.send_queued.v1",
            tenant,
            "email_campaign",
            campaign.id,
            actor_id=actor_id,
            payload={"eligible_recipient_count": preflight.eligible_count},
            job_id=job.id,
        )
        return job

    @classmethod
    @transaction.atomic
    def pause_campaign(
        cls, tenant_id: UUID, campaign_id: UUID, actor_id: UUID, idempotency_key: str
    ) -> EmailCampaign:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        return _apply_transition(CAMPAIGN_STATE_MACHINE, campaign, "pause", tenant, idempotency_key, actor_id)

    @classmethod
    @transaction.atomic
    def resume_campaign(
        cls, tenant_id: UUID, campaign_id: UUID, actor_id: UUID, idempotency_key: str
    ) -> AsyncJob:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        _apply_transition(CAMPAIGN_STATE_MACHINE, campaign, "resume", tenant, idempotency_key, actor_id)
        return enqueue(
            tenant,
            actor_id,
            "email_marketing.send_campaign",
            {"campaign_id": str(campaign.id), "resume": True},
            idempotency_key,
        )

    @classmethod
    @transaction.atomic
    def cancel_campaign(
        cls, tenant_id: UUID, campaign_id: UUID, actor_id: UUID, idempotency_key: str
    ) -> EmailCampaign:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        transitioned = _apply_transition(
            CAMPAIGN_STATE_MACHINE, campaign, "cancel", tenant, idempotency_key, actor_id
        )
        recipients = CampaignRecipient.objects.select_for_update().filter(
            tenant_id=tenant,
            campaign=campaign, status__in={"resolved", "queued", "sending"}
        )
        for recipient in recipients:
            _apply_transition(
                RECIPIENT_STATE_MACHINE,
                recipient,
                "cancel",
                tenant,
                f"cancel:{idempotency_key}:{recipient.id}",
                actor_id,
            )
        jobs = AsyncJob.objects.for_tenant(tenant).filter(
            payload__campaign_id=str(campaign.id), status__in={JobStatus.QUEUED, JobStatus.RETRYING}
        )
        for job in jobs:
            transition(job.id, tenant, JobStatus.CANCELLED, reason="Campaign cancelled", actor_id=actor_id)
        return transitioned

    @classmethod
    def preflight(cls, tenant_id: UUID, campaign_id: UUID) -> CampaignPreflight:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._campaign(tenant, campaign_id)
        counts = dict(
            CampaignRecipient.objects.for_tenant(tenant)
            .filter(campaign=campaign)
            .values_list("status")
            .annotate(total=Count("id"))
        )
        eligible = int(counts.get("resolved", 0))
        resolved = CampaignRecipient.objects.for_tenant(tenant).filter(campaign=campaign).count()
        suppressed = int(counts.get("suppressed", 0))
        content_valid = bool(campaign.template_id and campaign.subject.strip())
        sender_valid = cls._sender_is_verified(tenant, campaign.from_email)
        public_url = str(getattr(settings, "SARAISE_PUBLIC_URL", "")).rstrip("/")
        public_url_valid = urlparse(public_url).scheme == "https" and bool(urlparse(public_url).netloc)
        entitlement = EntitlementService().check(tenant, "email_marketing").entitled
        quota_state = Quota.objects.filter(tenant_id=tenant, resource="email_marketing.monthly_recipients").first()
        quota_remaining = int(quota_state.remaining) if quota_state else 0
        quota_available = eligible > 0 and quota_remaining >= eligible
        gateway_status = "unavailable"
        try:
            from .adapters import get_delivery_gateway

            health = get_delivery_gateway(getattr(campaign, "gateway_key", "django")).health()
            gateway_status = str(getattr(health, "code", "unavailable")) if health.available else "unavailable"
        except Exception:
            gateway_status = "unavailable"
        blockers: list[Mapping[str, str]] = []
        if not content_valid:
            blockers.append({"code": "CONTENT_INVALID", "message": "Select a valid template and subject."})
        if not sender_valid:
            blockers.append({"code": "SENDER_INVALID", "message": "Verify this sender for the tenant."})
        if not public_url_valid:
            blockers.append(
                {
                    "code": "PUBLIC_URL_INVALID",
                    "message": "Configure a public HTTPS URL for unsubscribe and tracking links.",
                }
            )
        if campaign.audience_snapshot_at is None:
            blockers.append({"code": "AUDIENCE_NOT_RESOLVED", "message": "Resolve the audience before sending."})
        if eligible <= 0:
            blockers.append({"code": "NO_ELIGIBLE_RECIPIENTS", "message": "No consent-eligible recipients are available."})
        if not entitlement:
            blockers.append({"code": "ENTITLEMENT_REQUIRED", "message": "Email marketing entitlement is unavailable."})
        if not quota_available:
            blockers.append({"code": "QUOTA_INSUFFICIENT", "message": "Recipient quota is insufficient."})
        if gateway_status != "ready":
            blockers.append({"code": "GATEWAY_UNAVAILABLE", "message": "The configured delivery gateway is not ready."})
        generated = timezone.now()
        receipt_payload = ":".join(
            [
                str(campaign.id),
                campaign.updated_at.isoformat(),
                str(campaign.audience_snapshot_at),
                str(eligible),
                str(quota_remaining),
            ]
        )
        receipt = signing.dumps(receipt_payload, salt="email_marketing.preflight", compress=True)
        return CampaignPreflight(
            campaign_id=campaign.id,
            generated_at=generated,
            receipt=receipt,
            content_valid=content_valid,
            sender_valid=sender_valid,
            audience_resolved=campaign.audience_snapshot_at is not None,
            resolved_count=resolved,
            eligible_count=eligible,
            suppressed_count=suppressed,
            consent_failure_count=suppressed,
            suppression_failure_count=CampaignRecipient.objects.for_tenant(tenant)
            .filter(campaign=campaign, status="suppressed")
            .exclude(suppression_reason="consent_not_granted")
            .count(),
            quota_required=eligible,
            quota_remaining=quota_remaining,
            quota_available=quota_available,
            entitlement_available=entitlement,
            schedule_valid=campaign.scheduled_at is None or campaign.scheduled_at > generated,
            gateway_status=gateway_status,
            blockers=tuple(blockers),
            consequences={
                "send": f"Queues {eligible} eligible recipients and reserves the same number of quota units.",
                "pause": "Stops new provider submissions; already accepted messages cannot be recalled.",
                "resume": "Queues only recipients that remain eligible and have not been accepted.",
                "cancel": "Cancels unsent recipients and pending jobs; accepted provider messages remain immutable.",
            },
        )

    @classmethod
    def get_campaign_analytics(cls, tenant_id: UUID, campaign_id: UUID) -> CampaignAnalytics:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._campaign(tenant, campaign_id)
        recipients = CampaignRecipient.objects.for_tenant(tenant).filter(campaign=campaign)
        counts = {row["status"]: row["total"] for row in recipients.values("status").annotate(total=Count("id"))}
        events = DeliveryEvent.objects.for_tenant(tenant).filter(recipient__campaign=campaign)
        unique_opened = events.filter(event_type="opened").values("recipient_id").distinct().count()
        unique_clicked = events.filter(event_type="clicked").values("recipient_id").distinct().count()
        accepted = sum(int(counts.get(value, 0)) for value in ("accepted", "delivered", "bounced", "complained"))
        delivered = int(counts.get("delivered", 0))
        bounced = int(counts.get("bounced", 0))
        failed = int(counts.get("failed", 0))
        unsubscribed = int(counts.get("unsubscribed", 0))
        complained = int(counts.get("complained", 0))
        truth = {
            "sent_count": accepted,
            "delivered_count": delivered,
            "unique_opened_count": unique_opened,
            "unique_clicked_count": unique_clicked,
            "bounced_count": bounced,
            "failed_count": failed,
            "unsubscribed_count": unsubscribed,
            "complaint_count": complained,
        }
        drift = {name: int(getattr(campaign, name)) - value for name, value in truth.items()}
        return CampaignAnalytics(
            campaign_id=campaign.id,
            resolved=recipients.count(),
            eligible=int(counts.get("resolved", 0)),
            suppressed=int(counts.get("suppressed", 0)),
            accepted=accepted,
            delivered=delivered,
            unique_opened=unique_opened,
            unique_clicked=unique_clicked,
            bounced=bounced,
            failed=failed,
            unsubscribed=unsubscribed,
            complained=complained,
            delivery_rate=delivered / accepted if accepted else 0.0,
            open_rate=unique_opened / delivered if delivered else 0.0,
            click_rate=unique_clicked / delivered if delivered else 0.0,
            bounce_rate=bounced / accepted if accepted else 0.0,
            counter_drift=drift,
        )

    @staticmethod
    def _validate_timezone(value: str) -> None:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationError({"timezone": "Must be a valid IANA timezone."}) from exc

    @classmethod
    def _validate_schedule(cls, scheduled_at: datetime, timezone_name: str) -> None:
        cls._validate_timezone(timezone_name)
        if timezone.is_naive(scheduled_at) or scheduled_at <= timezone.now():
            raise ValidationError({"scheduled_at": "Must be an aware future datetime."})

    @staticmethod
    def _validate_audience_definition(value: object) -> None:
        if not isinstance(value, Mapping):
            raise ValidationError({"audience_definition": "Must be an object."})
        if value and value.get("version", value.get("schema_version")) not in {1, "1"}:
            raise ValidationError({"audience_definition": "Only schema version 1 is supported."})
        allowed = {"version", "schema_version", "resolver", "candidates", "recipients", "industry"}
        if set(value) - allowed:
            raise ValidationError({"audience_definition": "Contains unsupported keys."})

    @staticmethod
    def _sender_is_verified(tenant_id: UUID, email: str) -> bool:
        configured = getattr(settings, "EMAIL_MARKETING_VERIFIED_SENDERS", {})
        if not isinstance(configured, Mapping):
            return False
        senders = configured.get(str(tenant_id), configured.get(tenant_id, ()))
        if not isinstance(senders, Sequence) or isinstance(senders, (str, bytes)):
            return False
        normalized = normalize_email(email)
        return normalized in {normalize_email(str(sender)) for sender in senders}

    @staticmethod
    def _snapshot_content(campaign: EmailCampaign) -> None:
        if campaign.template is None:
            raise DomainConflict("A template is required before sending.")
        from .adapters import sanitize_email_html

        campaign.content_snapshot_subject = campaign.subject or campaign.template.subject
        campaign.content_snapshot_html = sanitize_email_html(campaign.template.body_html)
        campaign.content_snapshot_text = campaign.template.body_text
        campaign.template_version_snapshot = campaign.template.version

    @staticmethod
    def _campaign(tenant_id: UUID, campaign_id: UUID) -> EmailCampaign:
        try:
            return EmailCampaign.objects.for_tenant(tenant_id).select_related("template").get(
                pk=campaign_id, is_deleted=False
            )
        except EmailCampaign.DoesNotExist as exc:
            raise NotFound("Campaign not found.") from exc

    @staticmethod
    def _locked_campaign(tenant_id: UUID, campaign_id: UUID) -> EmailCampaign:
        try:
            return EmailCampaign.objects.select_for_update().select_related("template").get(
                tenant_id=tenant_id, pk=campaign_id, is_deleted=False
            )
        except EmailCampaign.DoesNotExist as exc:
            raise NotFound("Campaign not found.") from exc


class TemplateService:
    editable_fields = frozenset(
        {"template_name", "description", "category", "subject", "preview_text", "body_html", "body_text", "design_json"}
    )

    @classmethod
    @transaction.atomic
    def create_template(cls, tenant_id: UUID, actor_id: UUID, data: Mapping[str, Any]) -> EmailTemplate:
        values = dict(data)
        values.pop("tenant_id", None)
        values.pop("status", None)
        values["template_code"] = str(values.get("template_code", "")).strip().upper()
        template = EmailTemplate(
            tenant_id=_uuid(tenant_id, "tenant_id"),
            created_by=_uuid(actor_id, "actor_id"),
            updated_by=_uuid(actor_id, "actor_id"),
            status="draft",
            is_active=False,
            **values,
        )
        try:
            template.full_clean()
            template.save()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        return template

    @classmethod
    @transaction.atomic
    def update_template(
        cls, tenant_id: UUID, template_id: UUID, actor_id: UUID, data: Mapping[str, Any]
    ) -> EmailTemplate:
        template = cls._locked_template(_uuid(tenant_id, "tenant_id"), template_id)
        if template.status != "draft":
            raise DomainConflict("Only draft templates can be edited; clone an archived template.")
        unknown = set(data) - cls.editable_fields
        if unknown:
            raise ValidationError({field: "This field is not editable." for field in sorted(unknown)})
        for field, value in data.items():
            setattr(template, field, value)
        template.version += 1
        template.updated_by = _uuid(actor_id, "actor_id")
        try:
            template.full_clean()
            template.save()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        return template

    @classmethod
    @transaction.atomic
    def activate_template(
        cls, tenant_id: UUID, template_id: UUID, actor_id: UUID, transition_key: str
    ) -> EmailTemplate:
        tenant = _uuid(tenant_id, "tenant_id")
        template = cls._locked_template(tenant, template_id)
        if not template.subject.strip() or not (template.body_html.strip() or template.body_text.strip()):
            raise ValidationError("An active template requires a subject and at least one body.")
        transitioned = _apply_transition(
            TEMPLATE_STATE_MACHINE, template, "activate", tenant, transition_key, actor_id
        )
        transitioned.is_active = True
        transitioned.updated_by = _uuid(actor_id, "actor_id")
        transitioned.save(update_fields=["is_active", "updated_by", "updated_at"])
        return transitioned

    @classmethod
    @transaction.atomic
    def archive_template(
        cls, tenant_id: UUID, template_id: UUID, actor_id: UUID, transition_key: str
    ) -> EmailTemplate:
        tenant = _uuid(tenant_id, "tenant_id")
        template = cls._locked_template(tenant, template_id)
        transitioned = _apply_transition(
            TEMPLATE_STATE_MACHINE, template, "archive", tenant, transition_key, actor_id
        )
        transitioned.is_active = False
        transitioned.updated_by = _uuid(actor_id, "actor_id")
        transitioned.save(update_fields=["is_active", "updated_by", "updated_at"])
        return transitioned

    @classmethod
    @transaction.atomic
    def clone_template(cls, tenant_id: UUID, template_id: UUID, actor_id: UUID, new_code: str) -> EmailTemplate:
        tenant = _uuid(tenant_id, "tenant_id")
        source = cls._template(tenant, template_id)
        return cls.create_template(
            tenant,
            actor_id,
            {
                "template_code": new_code,
                "template_name": f"{source.template_name} (copy)",
                "description": source.description,
                "category": source.category,
                "subject": source.subject,
                "preview_text": source.preview_text,
                "body_html": source.body_html,
                "body_text": source.body_text,
                "design_json": source.design_json,
            },
        )

    @classmethod
    def render_preview(cls, tenant_id: UUID, template_id: UUID, sample_data: Mapping[str, object]) -> Any:
        template = cls._template(_uuid(tenant_id, "tenant_id"), template_id)
        from .adapters import get_renderer

        return get_renderer("default").render(
            {"subject": template.subject, "body_html": template.body_html, "body_text": template.body_text},
            sample_data,
        )

    @classmethod
    @transaction.atomic
    def archive_record(cls, tenant_id: UUID, template_id: UUID, actor_id: UUID) -> None:
        template = cls._locked_template(_uuid(tenant_id, "tenant_id"), template_id)
        if template.status != "draft":
            raise DomainConflict("Only a draft template can be deleted.")
        template.is_deleted = True
        template.deleted_at = timezone.now()
        template.deleted_by = _uuid(actor_id, "actor_id")
        template.updated_by = template.deleted_by
        template.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_by", "updated_at"])

    @staticmethod
    def _template(tenant_id: UUID, template_id: UUID) -> EmailTemplate:
        try:
            return EmailTemplate.objects.for_tenant(tenant_id).get(pk=template_id, is_deleted=False)
        except EmailTemplate.DoesNotExist as exc:
            raise NotFound("Template not found.") from exc

    @staticmethod
    def _locked_template(tenant_id: UUID, template_id: UUID) -> EmailTemplate:
        try:
            return EmailTemplate.objects.select_for_update().get(
                tenant_id=tenant_id, pk=template_id, is_deleted=False
            )
        except EmailTemplate.DoesNotExist as exc:
            raise NotFound("Template not found.") from exc


class ComplianceService:
    @classmethod
    @transaction.atomic
    def record_consent(cls, tenant_id: UUID, actor_id: UUID | None, data: Mapping[str, Any]) -> ConsentRecord:
        tenant = _uuid(tenant_id, "tenant_id")
        values = dict(data)
        values.pop("tenant_id", None)
        values["email"] = normalize_email(str(values.get("email", "")))
        values.setdefault("captured_at", timezone.now())
        values["actor_id"] = _uuid(actor_id, "actor_id") if actor_id else None
        previous = cls.latest_consent(tenant, values["email"], str(values.get("purpose", "marketing")))
        record = ConsentRecord(tenant_id=tenant, supersedes=previous, **values)
        try:
            record.full_clean()
            record.save()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        _publish(
            "email_marketing.consent.changed.v1",
            tenant,
            "consent_record",
            record.id,
            actor_id=actor_id,
            payload={"purpose": record.purpose, "status": record.status, "source": record.source},
        )
        return record

    @classmethod
    def revoke_consent(
        cls, tenant_id: UUID, actor_id: UUID | None, email: str, purpose: str, source: str
    ) -> ConsentRecord:
        previous = cls.latest_consent(_uuid(tenant_id, "tenant_id"), normalize_email(email), purpose)
        lawful_basis = previous.lawful_basis if previous else "consent"
        notice_version = previous.notice_version if previous else "revocation-v1"
        return cls.record_consent(
            tenant_id,
            actor_id,
            {
                "email": email,
                "purpose": purpose,
                "status": "revoked",
                "lawful_basis": lawful_basis,
                "source": source,
                "notice_version": notice_version,
                "captured_at": timezone.now(),
                "evidence": {"kind": "revocation"},
            },
        )

    @classmethod
    @transaction.atomic
    def suppress(cls, tenant_id: UUID, actor_id: UUID | None, data: Mapping[str, Any]) -> SuppressionEntry:
        tenant = _uuid(tenant_id, "tenant_id")
        values = dict(data)
        values.pop("tenant_id", None)
        values["email"] = normalize_email(str(values.get("email", "")))
        values.setdefault("suppressed_at", timezone.now())
        if values.get("reason") in {"unsubscribe", "complaint", "legal"} and values.get("expires_at") is not None:
            raise ValidationError({"expires_at": "This suppression reason cannot expire."})
        existing = SuppressionEntry.objects.select_for_update().filter(
            tenant_id=tenant, email=values["email"], scope=values.get("scope", "marketing"), active=True
        ).first()
        if existing is not None:
            if existing.reason in {"hard_bounce", "complaint"} and existing.reason != values.get("reason"):
                raise DomainConflict("A provider-enforced suppression cannot be overwritten.")
            return existing
        entry = SuppressionEntry(
            tenant_id=tenant,
            created_by=_uuid(actor_id, "actor_id") if actor_id else None,
            updated_by=_uuid(actor_id, "actor_id") if actor_id else None,
            **values,
        )
        try:
            entry.full_clean()
            entry.save()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        _publish(
            "email_marketing.suppression.changed.v1",
            tenant,
            "suppression_entry",
            entry.id,
            actor_id=actor_id,
            payload={"scope": entry.scope, "reason": entry.reason, "active": True},
        )
        return entry

    @classmethod
    @transaction.atomic
    def deactivate_suppression(
        cls, tenant_id: UUID, suppression_id: UUID, actor_id: UUID, reason: str
    ) -> SuppressionEntry:
        if not reason.strip():
            raise ValidationError({"reason": "An audit reason is required."})
        tenant = _uuid(tenant_id, "tenant_id")
        try:
            entry = SuppressionEntry.objects.select_for_update().get(
                tenant_id=tenant, pk=suppression_id, active=True
            )
        except SuppressionEntry.DoesNotExist as exc:
            raise NotFound("Suppression not found.") from exc
        entry.active = False
        entry.deactivated_at = timezone.now()
        entry.deactivated_by = _uuid(actor_id, "actor_id")
        entry.updated_by = entry.deactivated_by
        entry.notes = f"{entry.notes}\nDeactivation: {reason}".strip()
        entry.save()
        _publish(
            "email_marketing.suppression.changed.v1",
            tenant,
            "suppression_entry",
            entry.id,
            actor_id=actor_id,
            payload={"scope": entry.scope, "reason": entry.reason, "active": False},
        )
        return entry

    @staticmethod
    def latest_consent(tenant_id: UUID, email: str, purpose: str) -> ConsentRecord | None:
        return (
            ConsentRecord.objects.for_tenant(_uuid(tenant_id, "tenant_id"))
            .filter(email=normalize_email(email), purpose=purpose)
            .order_by("-captured_at", "-created_at", "-id")
            .first()
        )

    @staticmethod
    def active_suppression(tenant_id: UUID, email: str, scope: str) -> SuppressionEntry | None:
        now = timezone.now()
        scopes = ("all", "marketing") if scope == "marketing" else ("all",)
        return (
            SuppressionEntry.objects.for_tenant(_uuid(tenant_id, "tenant_id"))
            .filter(email=normalize_email(email), scope__in=scopes, active=True)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .order_by("-suppressed_at")
            .first()
        )

    @classmethod
    def is_eligible(cls, tenant_id: UUID, email: str, purpose: str) -> EligibilityDecision:
        tenant = _uuid(tenant_id, "tenant_id")
        normalized = normalize_email(email)
        suppression = cls.active_suppression(tenant, normalized, "marketing")
        if suppression is not None:
            return EligibilityDecision(False, "SUPPRESSED", "An active suppression applies.", suppression_id=suppression.id)
        consent = cls.latest_consent(tenant, normalized, purpose)
        if consent is None or consent.status != "granted":
            return EligibilityDecision(
                False,
                "CONSENT_NOT_GRANTED",
                "The latest consent state does not permit marketing.",
                consent_record_id=consent.id if consent else None,
            )
        return EligibilityDecision(True, "ELIGIBLE", "Consent is current and no suppression applies.", consent.id)


class AudienceService:
    @classmethod
    @transaction.atomic
    def resolve(cls, tenant_id: UUID, campaign_id: UUID, actor_id: UUID) -> AudienceResolutionResult:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = CampaignService._locked_campaign(tenant, campaign_id)
        if campaign.status != "draft":
            raise DomainConflict("Audience can only be resolved for a draft campaign.")
        from .adapters import get_audience_resolver

        resolver_key = getattr(campaign, "audience_resolver_key", "manual") or str(
            campaign.audience_definition.get("resolver", "manual")
        )
        definition = dict(campaign.audience_definition)
        if "version" in definition and "schema_version" not in definition:
            definition["schema_version"] = definition.pop("version")
        if "candidates" in definition and "recipients" not in definition:
            definition["recipients"] = definition.pop("candidates")
        result = get_audience_resolver(resolver_key).resolve(tenant, definition)
        candidates = tuple(
            AudienceCandidate(
                email=str(candidate.email),
                display_name=str(getattr(candidate, "display_name", "")),
                recipient_key=getattr(candidate, "recipient_key", None),
                personalization_data=(
                    getattr(candidate, "personalization_data", None)
                    or getattr(candidate, "personalization", {})
                    or {}
                ),
            )
            for candidate in result.candidates
        )
        count = cls.replace_snapshot(tenant, campaign.id, actor_id, candidates)
        campaign.refresh_from_db()
        return AudienceResolutionResult(candidates, dict(result.evidence), resolver_key) if count else AudienceResolutionResult((), dict(result.evidence), resolver_key)

    @classmethod
    def evaluate_recipient(
        cls, tenant_id: UUID, campaign_id: UUID, candidate: AudienceCandidate
    ) -> EligibilityDecision:
        tenant = _uuid(tenant_id, "tenant_id")
        CampaignService._campaign(tenant, campaign_id)
        normalized = normalize_email(candidate.email)
        if CampaignRecipient.objects.for_tenant(tenant).filter(campaign_id=campaign_id, email=normalized).exists():
            return EligibilityDecision(False, "DUPLICATE", "The normalized address is already in the snapshot.")
        return ComplianceService.is_eligible(tenant, normalized, "marketing")

    @classmethod
    def recheck_before_send(cls, tenant_id: UUID, recipient_id: UUID) -> EligibilityDecision:
        tenant = _uuid(tenant_id, "tenant_id")
        try:
            recipient = CampaignRecipient.objects.for_tenant(tenant).get(pk=recipient_id)
        except CampaignRecipient.DoesNotExist as exc:
            raise NotFound("Recipient not found.") from exc
        return ComplianceService.is_eligible(tenant, recipient.email, "marketing")

    @classmethod
    @transaction.atomic
    def replace_snapshot(
        cls, tenant_id: UUID, campaign_id: UUID, actor_id: UUID, candidates: Sequence[AudienceCandidate]
    ) -> int:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = CampaignService._locked_campaign(tenant, campaign_id)
        if campaign.status != "draft":
            raise DomainConflict("Audience snapshots are immutable after draft.")
        CampaignRecipient.objects.for_tenant(tenant).filter(campaign=campaign).delete()
        deduplicated: dict[str, AudienceCandidate] = {}
        for candidate in candidates:
            normalized = normalize_email(candidate.email)
            deduplicated.setdefault(normalized, candidate)
        records: list[CampaignRecipient] = []
        now = timezone.now()
        for email, candidate in deduplicated.items():
            decision = ComplianceService.is_eligible(tenant, email, "marketing")
            records.append(
                CampaignRecipient(
                    tenant_id=tenant,
                    campaign=campaign,
                    recipient_key=candidate.recipient_key,
                    email=email,
                    display_name=candidate.display_name,
                    personalization_data=dict(candidate.personalization_data or {}),
                    consent_record_id=decision.consent_record_id,
                    status="resolved" if decision.eligible else "suppressed",
                    suppression_reason="" if decision.eligible else decision.code.lower(),
                    resolved_at=now,
                )
            )
        CampaignRecipient.objects.bulk_create(records)
        campaign.audience_snapshot_at = now
        campaign.resolved_recipient_count = len(records)
        campaign.updated_by = _uuid(actor_id, "actor_id")
        if hasattr(campaign, "audience_snapshot_evidence"):
            campaign.audience_snapshot_evidence = {
                "schema_version": 1,
                "deduplicated_count": len(records),
                "eligible_count": sum(record.status == "resolved" for record in records),
            }
        campaign.save()
        return len(records)


class DeliveryService:
    @classmethod
    @transaction.atomic
    def process_campaign_job(cls, job: AsyncJob) -> dict[str, object]:
        campaign_id = _uuid(job.payload.get("campaign_id"), "campaign_id")
        campaign = CampaignService._locked_campaign(job.tenant_id, campaign_id)
        if campaign.status == "paused":
            return {"campaign_id": str(campaign.id), "queued_count": 0, "status": "paused"}
        if campaign.status == "queueing":
            campaign = _apply_transition(
                CAMPAIGN_STATE_MACHINE,
                campaign,
                "start_send",
                job.tenant_id,
                f"start:{job.id}",
                job.actor_id,
            )
            campaign.send_started_at = timezone.now()
            campaign.save(update_fields=["send_started_at", "updated_at"])
        recipients = list(
            CampaignRecipient.objects.select_for_update().filter(
                tenant_id=job.tenant_id, campaign=campaign, status__in={"queued", "failed"}
            )
        )
        queued = 0
        for recipient in recipients:
            if recipient.status == "failed":
                recipient = _apply_transition(
                    RECIPIENT_STATE_MACHINE,
                    recipient,
                    "retry",
                    job.tenant_id,
                    f"retry:{job.id}:{recipient.id}",
                    job.actor_id,
                )
            child = enqueue(
                job.tenant_id,
                job.actor_id,
                "email_marketing.send_recipient",
                {"campaign_id": str(campaign.id), "recipient_id": str(recipient.id)},
                f"send-recipient:{campaign.id}:{recipient.id}",
            )
            queued += int(child.status in {JobStatus.QUEUED, JobStatus.RETRYING})
        return {"campaign_id": str(campaign.id), "queued_count": queued, "status": campaign.status}

    @classmethod
    def submit_recipient(
        cls, tenant_id: UUID, recipient_id: UUID, job_id: UUID
    ) -> OperationResult[DeliveryAttempt]:
        tenant = _uuid(tenant_id, "tenant_id")
        with transaction.atomic():
            try:
                recipient = (
                    CampaignRecipient.objects.select_for_update()
                    .select_related("campaign")
                    .get(tenant_id=tenant, pk=recipient_id)
                )
            except CampaignRecipient.DoesNotExist as exc:
                raise NotFound("Recipient not found.") from exc
            existing = DeliveryAttempt.objects.for_tenant(tenant).filter(
                idempotency_key=f"recipient:{recipient.id}:job:{job_id}"
            ).first()
            if existing is not None:
                return OperationResult.success(existing, code="idempotent_attempt")
            if recipient.campaign.status == "paused":
                return OperationResult.failure("campaign_paused", detail="Campaign is paused.")
            decision = AudienceService.recheck_before_send(tenant, recipient.id)
            if not decision.eligible:
                recipient = _apply_transition(
                    RECIPIENT_STATE_MACHINE,
                    recipient,
                    "suppress",
                    tenant,
                    f"suppress:{job_id}:{recipient.id}",
                    SYSTEM_ACTOR_ID,
                )
                recipient.suppression_reason = decision.code.lower()
                recipient.save(update_fields=["suppression_reason", "updated_at"])
                return OperationResult.failure(decision.code.lower(), detail="Recipient is no longer eligible.")
            number = (
                DeliveryAttempt.objects.for_tenant(tenant).filter(recipient=recipient).aggregate(total=Count("id"))["total"]
                + 1
            )
            attempt = DeliveryAttempt.objects.create(
                tenant_id=tenant,
                recipient=recipient,
                attempt_number=number,
                job_id=job_id,
                idempotency_key=f"recipient:{recipient.id}:job:{job_id}",
                gateway_key=getattr(recipient.campaign, "gateway_key", "django"),
                status="sending",
                started_at=timezone.now(),
            )
            recipient = _apply_transition(
                RECIPIENT_STATE_MACHINE,
                recipient,
                "start_send",
                tenant,
                f"start:{attempt.id}",
                SYSTEM_ACTOR_ID,
            )

        from .adapters import DeliveryMessage, get_delivery_gateway, get_renderer

        campaign = recipient.campaign
        rendered = get_renderer("default").render(
            {
                "subject": campaign.content_snapshot_subject,
                "body_html": campaign.content_snapshot_html,
                "body_text": campaign.content_snapshot_text,
            },
            recipient.personalization_data,
        )
        unsubscribe_token = signing.dumps(
            {"tenant_id": str(tenant), "recipient_id": str(recipient.id)}, salt="email_marketing.unsubscribe"
        )
        tracking_token = signing.dumps(
            {"tenant_id": str(tenant), "recipient_id": str(recipient.id)}, salt="email_marketing.tracking"
        )
        public_url = str(getattr(settings, "SARAISE_PUBLIC_URL", "")).rstrip("/")
        rendered = cls._instrument_rendered(rendered, public_url, tracking_token)
        message = DeliveryMessage(
            recipient=recipient.email,
            from_email=campaign.from_email,
            from_name=campaign.from_name,
            reply_to=campaign.reply_to_email,
            rendered=rendered,
            headers={
                "List-Unsubscribe": f"<{public_url}/api/v2/email-marketing/public/unsubscribe/?token={unsubscribe_token}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        )
        try:
            result = get_delivery_gateway(attempt.gateway_key).submit(
                message,
                attempt.idempotency_key,
                get_correlation_id() or str(job_id),
            )
        except Exception:
            result = OperationResult.failure("gateway_unavailable", retryable=True, detail="Delivery gateway is unavailable.")
        with transaction.atomic():
            attempt = DeliveryAttempt.objects.select_for_update().get(tenant_id=tenant, pk=attempt.id)
            recipient = CampaignRecipient.objects.select_for_update().get(tenant_id=tenant, pk=recipient.id)
            if result.successful and result.value is not None:
                receipt = result.value
                provider_acknowledgement = str(getattr(receipt, "acknowledgement", ""))
                acknowledgement = "delivered" if provider_acknowledgement == "provider_delivered" else "accepted"
                if provider_acknowledgement in {"transport_accepted", "provider_accepted", "provider_delivered"}:
                    attempt.status = acknowledgement
                    attempt.provider_message_id = str(getattr(receipt, "provider_message_id", ""))
                    attempt.provider_status_code = provider_acknowledgement
                    attempt.response_evidence = dict(getattr(receipt, "evidence", {}))
                    attempt.accepted_at = timezone.now()
                    if acknowledgement == "delivered":
                        attempt.completed_at = timezone.now()
                    recipient = _apply_transition(
                        RECIPIENT_STATE_MACHINE,
                        recipient,
                        acknowledgement,
                        tenant,
                        f"gateway:{attempt.id}:{acknowledgement}",
                        SYSTEM_ACTOR_ID,
                    )
                    recipient.accepted_at = attempt.accepted_at
                    if acknowledgement == "delivered":
                        recipient.delivered_at = attempt.completed_at
                    recipient.save()
                attempt.save()
                accepted_event = DeliveryEvent.objects.create(
                    tenant_id=tenant,
                    recipient=recipient,
                    attempt=attempt,
                    gateway_key=attempt.gateway_key,
                    provider_event_id=f"gateway:{attempt.id}:{acknowledgement}",
                    event_type=acknowledgement,
                    occurred_at=attempt.accepted_at or timezone.now(),
                    metadata={"source": "gateway_acknowledgement"},
                    correlation_id=get_correlation_id() or str(job_id),
                )
                cls._apply_event_truth(accepted_event, attempt)
                _publish(
                    "email_marketing.email.sent.v1",
                    tenant,
                    "campaign_recipient",
                    recipient.id,
                    actor_id=None,
                    payload={"attempt_id": str(attempt.id), "gateway_key": attempt.gateway_key},
                    job_id=job_id,
                )
                cls._complete_campaign_if_finished(tenant, campaign.id, job_id)
                return OperationResult.success(attempt, code="provider_acknowledged")
            error_code = str(result.code or "delivery_unavailable")
            attempt.status = "timed_out" if result.ambiguous else "failed"
            attempt.error_code = error_code[:64]
            attempt.error_detail = str(result.detail or "Delivery failed.")[:1000]
            attempt.completed_at = timezone.now()
            attempt.save()
            recipient = _apply_transition(
                RECIPIENT_STATE_MACHINE,
                recipient,
                "fail",
                tenant,
                f"fail:{attempt.id}",
                SYSTEM_ACTOR_ID,
            )
            recipient.last_error_code = attempt.error_code
            recipient.failed_at = attempt.completed_at
            recipient.save(update_fields=["last_error_code", "failed_at", "updated_at"])
            campaign.failed_count += 1
            campaign.save(update_fields=["failed_count", "updated_at"])
            cls._complete_campaign_if_finished(tenant, campaign.id, job_id)
            return OperationResult.failure(
                attempt.error_code.lower(),
                retryable=result.retryable,
                ambiguous=result.ambiguous,
                detail="Delivery gateway did not acknowledge the message.",
            )

    @classmethod
    @transaction.atomic
    def retry_recipient(
        cls, tenant_id: UUID, recipient_id: UUID, actor_id: UUID, idempotency_key: str
    ) -> AsyncJob:
        tenant = _uuid(tenant_id, "tenant_id")
        try:
            recipient = CampaignRecipient.objects.select_for_update().get(tenant_id=tenant, pk=recipient_id)
        except CampaignRecipient.DoesNotExist as exc:
            raise NotFound("Recipient not found.") from exc
        if recipient.status != "failed" and not recipient.delivery_attempts.filter(status="deferred").exists():
            raise DomainConflict("Only failed or deferred recipients can be retried.")
        return enqueue(
            tenant,
            actor_id,
            "email_marketing.send_recipient",
            {"campaign_id": str(recipient.campaign_id), "recipient_id": str(recipient.id), "retry": True},
            idempotency_key,
        )

    @classmethod
    @transaction.atomic
    def record_provider_event(
        cls, tenant_id: UUID, gateway_key: str, verified_event: object
    ) -> DeliveryEvent:
        tenant = _uuid(tenant_id, "tenant_id")
        provider_event_id = str(getattr(verified_event, "provider_event_id"))
        existing = DeliveryEvent.objects.for_tenant(tenant).filter(
            gateway_key=gateway_key, provider_event_id=provider_event_id
        ).first()
        if existing is not None:
            return existing
        provider_message_id = str(getattr(verified_event, "provider_message_id", ""))
        attempt = (
            DeliveryAttempt.objects.select_for_update()
            .filter(tenant_id=tenant, gateway_key=gateway_key, provider_message_id=provider_message_id)
            .select_related("recipient__campaign")
            .first()
        )
        if attempt is None:
            raise NotFound("No tenant-bound delivery attempt matches this event.")
        event_type = str(getattr(verified_event, "event_type"))
        event = DeliveryEvent.objects.create(
            tenant_id=tenant,
            recipient=attempt.recipient,
            attempt=attempt,
            gateway_key=gateway_key,
            provider_event_id=provider_event_id,
            event_type=event_type,
            occurred_at=getattr(verified_event, "occurred_at"),
            link_url_hash=str(getattr(verified_event, "link_url_hash", "")),
            bounce_class=str(getattr(verified_event, "bounce_class", "")),
            metadata=dict(getattr(verified_event, "metadata", {}) or {}),
            correlation_id=str(getattr(verified_event, "correlation_id", get_correlation_id() or "")),
        )
        cls._apply_event_truth(event, attempt)
        return event

    @classmethod
    def record_open(cls, tenant_id: UUID, tracking_token: str) -> DeliveryEvent:
        payload = signing.loads(tracking_token, salt="email_marketing.tracking", max_age=60 * 60 * 24 * 90)
        if str(payload.get("tenant_id")) != str(tenant_id):
            raise NotFound("Tracking token is not valid for this tenant.")
        recipient_id = _uuid(payload.get("recipient_id"), "recipient_id")
        event_id = hashlib.sha256(f"open:{tracking_token}".encode()).hexdigest()
        event = type("Verified", (), {
            "provider_event_id": event_id,
            "provider_message_id": payload.get("provider_message_id", ""),
            "event_type": "opened",
            "occurred_at": timezone.now(),
            "link_url_hash": "",
            "bounce_class": "",
            "metadata": {"source": "tracking"},
            "correlation_id": get_correlation_id() or "",
        })()
        attempt = DeliveryAttempt.objects.for_tenant(tenant_id).filter(recipient_id=recipient_id).order_by("-created_at").first()
        if attempt is None:
            raise NotFound("Tracking recipient has no accepted attempt.")
        event.provider_message_id = attempt.provider_message_id
        return cls.record_provider_event(tenant_id, attempt.gateway_key, event)

    @classmethod
    def record_click(cls, tenant_id: UUID, tracking_token: str, signed_destination: str) -> tuple[DeliveryEvent, str]:
        destination = signing.loads(signed_destination, salt="email_marketing.destination", max_age=60 * 60 * 24 * 90)
        parsed = urlparse(str(destination))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValidationError("Signed destination is not a safe HTTP URL.")
        event = cls.record_open(tenant_id, tracking_token)
        # A distinct provider id keeps click truth independent of the open pixel.
        click = type("Verified", (), {
            "provider_event_id": hashlib.sha256(f"click:{tracking_token}:{signed_destination}".encode()).hexdigest(),
            "provider_message_id": event.attempt.provider_message_id if event.attempt else "",
            "event_type": "clicked",
            "occurred_at": timezone.now(),
            "link_url_hash": hashlib.sha256(str(destination).encode()).hexdigest(),
            "bounce_class": "",
            "metadata": {"source": "tracking"},
            "correlation_id": get_correlation_id() or "",
        })()
        return cls.record_provider_event(tenant_id, event.gateway_key, click), str(destination)

    @classmethod
    @transaction.atomic
    def unsubscribe(cls, tenant_id: UUID, signed_token: str, occurred_at: datetime) -> SuppressionEntry:
        payload = signing.loads(signed_token, salt="email_marketing.unsubscribe", max_age=60 * 60 * 24 * 365)
        tenant = _uuid(tenant_id, "tenant_id")
        if str(payload.get("tenant_id")) != str(tenant):
            raise NotFound("Unsubscribe token is not valid for this tenant.")
        recipient_id = _uuid(payload.get("recipient_id"), "recipient_id")
        try:
            recipient = CampaignRecipient.objects.select_for_update().get(tenant_id=tenant, pk=recipient_id)
        except CampaignRecipient.DoesNotExist as exc:
            raise NotFound("Recipient not found.") from exc
        ComplianceService.revoke_consent(tenant, None, recipient.email, "marketing", "unsubscribe")
        suppression = ComplianceService.suppress(
            tenant,
            SYSTEM_ACTOR_ID,
            {
                "email": recipient.email,
                "scope": "marketing",
                "reason": "unsubscribe",
                "source": "user",
                "suppressed_at": occurred_at,
            },
        )
        if recipient.status not in {"complained", "bounced", "unsubscribed", "cancelled"}:
            if recipient.status == "sending":
                recipient = _apply_transition(
                    RECIPIENT_STATE_MACHINE,
                    recipient,
                    "accepted",
                    tenant,
                    f"unsubscribe-accept:{recipient.id}:{occurred_at.isoformat()}",
                    SYSTEM_ACTOR_ID,
                )
            _apply_transition(
                RECIPIENT_STATE_MACHINE,
                recipient,
                "unsubscribe",
                tenant,
                f"unsubscribe:{recipient.id}:{occurred_at.isoformat()}",
                SYSTEM_ACTOR_ID,
            )
        return suppression

    @classmethod
    def reconcile_ambiguous_attempt(
        cls, tenant_id: UUID, attempt_id: UUID
    ) -> OperationResult[DeliveryAttempt]:
        tenant = _uuid(tenant_id, "tenant_id")
        try:
            attempt = DeliveryAttempt.objects.for_tenant(tenant).get(pk=attempt_id)
        except DeliveryAttempt.DoesNotExist as exc:
            raise NotFound("Delivery attempt not found.") from exc
        if attempt.status != "timed_out" or not attempt.provider_message_id:
            return OperationResult.failure(
                "not_reconcilable",
                detail="Only ambiguous attempts with a provider identifier can be reconciled.",
            )
        from .adapters import get_delivery_gateway

        result = get_delivery_gateway(attempt.gateway_key).lookup(attempt.provider_message_id)
        if not result.successful or result.value is None:
            return OperationResult.failure(
                result.code or "reconciliation_unavailable",
                retryable=result.retryable,
                ambiguous=result.ambiguous,
                detail=result.detail or "Provider reconciliation is unavailable.",
            )
        receipt = result.value
        acknowledgement = str(getattr(receipt, "acknowledgement", ""))
        if acknowledgement not in {"accepted", "delivered", "failed", "bounced"}:
            return OperationResult.failure("ambiguous_delivery", ambiguous=True, detail="Provider status remains ambiguous.")
        attempt.status = acknowledgement
        attempt.response_evidence = dict(getattr(receipt, "evidence", {}))
        attempt.completed_at = timezone.now() if acknowledgement != "accepted" else None
        attempt.save()
        return OperationResult.success(attempt, code="reconciled")

    @classmethod
    def _apply_event_truth(cls, event: DeliveryEvent, attempt: DeliveryAttempt) -> None:
        recipient = attempt.recipient
        campaign = recipient.campaign
        event_type = event.event_type
        terminal = {"delivered", "bounced", "complained", "unsubscribed"}
        status_map = {
            "accepted": "accepted",
            "delivered": "delivered",
            "bounced": "bounced",
            "complained": "complained",
            "unsubscribed": "unsubscribed",
        }
        target = status_map.get(event_type)
        if target and recipient.status not in terminal and recipient.status != target:
            command = {
                "accepted": "accepted",
                "delivered": "delivered",
                "bounced": "bounce",
                "complained": "complain",
                "unsubscribed": "unsubscribe",
            }[target]
            if recipient.status == "sending" and command in {"delivered", "complain", "unsubscribe"}:
                recipient = _apply_transition(
                    RECIPIENT_STATE_MACHINE,
                    recipient,
                    "accepted",
                    event.tenant_id,
                    f"event-accepted:{event.id}",
                    SYSTEM_ACTOR_ID,
                )
            recipient = _apply_transition(
                RECIPIENT_STATE_MACHINE,
                recipient,
                command,
                event.tenant_id,
                f"event:{event.id}:{command}",
                SYSTEM_ACTOR_ID,
            )
            if target == "delivered":
                recipient.delivered_at = event.occurred_at
                recipient.save(update_fields=["delivered_at", "updated_at"])
        counter_map = {
            "accepted": "sent_count",
            "delivered": "delivered_count",
            "opened": "opened_count",
            "clicked": "clicked_count",
            "bounced": "bounced_count",
            "complained": "complaint_count",
            "unsubscribed": "unsubscribed_count",
        }
        field = counter_map.get(event_type)
        if field:
            setattr(campaign, field, int(getattr(campaign, field)) + 1)
        if event_type == "opened" and not DeliveryEvent.objects.for_tenant(event.tenant_id).filter(
            recipient=recipient, event_type="opened"
        ).exclude(pk=event.pk).exists():
            campaign.unique_opened_count += 1
        if event_type == "clicked" and not DeliveryEvent.objects.for_tenant(event.tenant_id).filter(
            recipient=recipient, event_type="clicked"
        ).exclude(pk=event.pk).exists():
            campaign.unique_clicked_count += 1
        campaign.save()
        if event_type in {"bounced", "complained", "unsubscribed"}:
            reason = {"bounced": "hard_bounce", "complained": "complaint", "unsubscribed": "unsubscribe"}[event_type]
            ComplianceService.suppress(
                event.tenant_id,
                None,
                {
                    "email": recipient.email,
                    "scope": "marketing",
                    "reason": reason,
                    "source": "provider_event",
                    "evidence_event": event,
                },
            )
        event_name = {
            "delivered": "email_marketing.email.delivered.v1",
            "opened": "email_marketing.email.opened.v1",
            "clicked": "email_marketing.email.clicked.v1",
            "bounced": "email_marketing.email.bounced.v1",
            "unsubscribed": "email_marketing.email.unsubscribed.v1",
        }.get(event_type)
        if event_name:
            _publish(
                event_name,
                event.tenant_id,
                "campaign_recipient",
                recipient.id,
                actor_id=None,
                payload={"recipient_id": str(recipient.id), "attempt_id": str(attempt.id)},
            )

    @staticmethod
    def _instrument_rendered(rendered: object, public_url: str, tracking_token: str) -> object:
        """Rewrite safe links and append an open pixel without storing raw URLs."""

        from .adapters import RenderedEmail

        html = str(getattr(rendered, "html", ""))

        def rewrite(match: re.Match[str]) -> str:
            destination = match.group(2)
            parsed = urlparse(destination)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return match.group(0)
            signed = signing.dumps(destination, salt="email_marketing.destination", compress=True)
            click_url = (
                f"{public_url}/api/v2/email-marketing/t/{quote(tracking_token, safe='')}/click/"
                f"?destination={quote(signed, safe='')}"
            )
            return f'{match.group(1)}{click_url}{match.group(3)}'

        rewritten = re.sub(r'(<a\b[^>]*\bhref=["\'])(https?://[^"\']+)(["\'])', rewrite, html, flags=re.IGNORECASE)
        pixel = (
            f'<img src="{public_url}/api/v2/email-marketing/t/{quote(tracking_token, safe="")}/open.gif" '
            'width="1" height="1" alt="" style="display:none" />'
        )
        return RenderedEmail(
            subject=str(getattr(rendered, "subject")),
            html=f"{rewritten}{pixel}" if rewritten else "",
            text=str(getattr(rendered, "text", "")),
            preview_text=str(getattr(rendered, "preview_text", "")),
        )

    @classmethod
    def _complete_campaign_if_finished(cls, tenant_id: UUID, campaign_id: UUID, job_id: UUID) -> None:
        """Mark a sending campaign sent only after every recipient is terminal."""

        campaign = EmailCampaign.objects.select_for_update().get(tenant_id=tenant_id, pk=campaign_id)
        remaining = CampaignRecipient.objects.for_tenant(tenant_id).filter(
            campaign=campaign, status__in={"resolved", "queued", "sending"}
        )
        if campaign.status != "sending" or remaining.exists():
            return
        campaign.completed_at = timezone.now()
        campaign.save(update_fields=["completed_at", "updated_at"])
        campaign = _apply_transition(
            CAMPAIGN_STATE_MACHINE,
            campaign,
            "complete",
            tenant_id,
            f"complete:{campaign.id}",
            SYSTEM_ACTOR_ID,
        )
        _publish(
            "email_marketing.campaign.sent.v1",
            tenant_id,
            "email_campaign",
            campaign.id,
            actor_id=None,
            job_id=job_id,
            payload={
                "sent_count": campaign.sent_count,
                "delivered_count": campaign.delivered_count,
                "failed_count": campaign.failed_count,
                "bounced_count": campaign.bounced_count,
                "status": campaign.status,
            },
        )


# Compatibility aliases preserve imports while routing legacy callers into the
# strict service implementation. They intentionally do not accept arbitrary
# ORM keyword arguments.
EmailCampaignService = CampaignService
EmailTemplateService = TemplateService


__all__ = [
    "AudienceCandidate",
    "AudienceResolutionResult",
    "AudienceService",
    "CampaignAnalytics",
    "CampaignPreflight",
    "CampaignService",
    "ComplianceService",
    "DeliveryService",
    "DomainConflict",
    "EligibilityDecision",
    "EmailCampaignService",
    "EmailTemplateService",
    "TemplateService",
    "normalize_email",
]
