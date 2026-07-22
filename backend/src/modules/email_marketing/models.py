"""Tenant-safe persistence for the email-marketing runtime.

The models deliberately keep delivery/compliance evidence separate from the
mutable campaign and template aggregates.  Application validation provides an
early, useful error while migration ``0004`` installs equivalent cross-tenant
relationship protection in PostgreSQL.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.deconstruct import deconstructible

from src.core.tenancy import TenantScopedModel, TimestampedModel
from src.core.tenancy.models import TenantQuerySet


class CampaignStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SCHEDULED = "scheduled", "Scheduled"
    QUEUEING = "queueing", "Queueing"
    SENDING = "sending", "Sending"
    PAUSED = "paused", "Paused"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class TemplateStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class RecipientStatus(models.TextChoices):
    RESOLVED = "resolved", "Resolved"
    SUPPRESSED = "suppressed", "Suppressed"
    QUEUED = "queued", "Queued"
    SENDING = "sending", "Sending"
    ACCEPTED = "accepted", "Accepted"
    DELIVERED = "delivered", "Delivered"
    BOUNCED = "bounced", "Bounced"
    FAILED = "failed", "Failed"
    UNSUBSCRIBED = "unsubscribed", "Unsubscribed"
    COMPLAINED = "complained", "Complained"
    CANCELLED = "cancelled", "Cancelled"


class DeliveryAttemptStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    SENDING = "sending", "Sending"
    ACCEPTED = "accepted", "Accepted"
    DEFERRED = "deferred", "Deferred"
    DELIVERED = "delivered", "Delivered"
    BOUNCED = "bounced", "Bounced"
    FAILED = "failed", "Failed"
    TIMED_OUT = "timed_out", "Timed out"


class DeliveryEventType(models.TextChoices):
    ACCEPTED = "accepted", "Accepted"
    DELIVERED = "delivered", "Delivered"
    OPENED = "opened", "Opened"
    CLICKED = "clicked", "Clicked"
    DEFERRED = "deferred", "Deferred"
    BOUNCED = "bounced", "Bounced"
    COMPLAINED = "complained", "Complained"
    UNSUBSCRIBED = "unsubscribed", "Unsubscribed"


class SuppressionScope(models.TextChoices):
    MARKETING = "marketing", "Marketing"
    ALL = "all", "All email"


class SuppressionReason(models.TextChoices):
    UNSUBSCRIBE = "unsubscribe", "Unsubscribe"
    HARD_BOUNCE = "hard_bounce", "Hard bounce"
    COMPLAINT = "complaint", "Complaint"
    MANUAL = "manual", "Manual"
    LEGAL = "legal", "Legal"


class SuppressionSource(models.TextChoices):
    USER = "user", "User"
    PROVIDER_EVENT = "provider_event", "Provider event"
    ADMINISTRATOR = "administrator", "Administrator"
    MIGRATION = "migration", "Migration"


class ConsentStatus(models.TextChoices):
    GRANTED = "granted", "Granted"
    REVOKED = "revoked", "Revoked"


class LawfulBasis(models.TextChoices):
    CONSENT = "consent", "Consent"
    LEGITIMATE_INTEREST = "legitimate_interest", "Legitimate interest"
    CONTRACTUAL = "contractual", "Contractual"


class ConsentSource(models.TextChoices):
    FORM = "form", "Form"
    IMPORT = "import", "Import"
    API = "api", "API"
    CRM_EVENT = "crm_event", "CRM event"
    ADMINISTRATOR = "administrator", "Administrator"
    UNSUBSCRIBE = "unsubscribe", "Unsubscribe"


Source = ConsentSource


ConsentLawfulBasis = LawfulBasis


class BounceClass(models.TextChoices):
    HARD = "hard", "Hard"
    SOFT = "soft", "Soft"
    BLOCK = "block", "Block"


class ImmutableEvidenceError(ValidationError):
    """Raised when append-only delivery or consent evidence is mutated."""


def normalize_email_address(value: str) -> str:
    """Validate an address and lowercase only its domain component."""

    if not isinstance(value, str):
        raise ValidationError("Enter a valid email address.", code="invalid")
    normalized = value.strip()
    validate_email(normalized)
    local, separator, domain = normalized.rpartition("@")
    if not separator or not local or not domain:
        raise ValidationError("Enter a valid email address.", code="invalid")
    return f"{local}@{domain.lower()}"


def validate_timezone_name(value: str) -> None:
    """Require an IANA timezone identifier understood by the runtime."""

    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValidationError("Enter a valid IANA timezone.", code="invalid_timezone") from exc


@deconstructible
class BoundedJSONValidator:
    """Bound untrusted JSON by shape, nesting, key count, and encoded bytes."""

    def __init__(
        self,
        *,
        max_bytes: int,
        max_depth: int = 8,
        max_keys: int = 128,
        require_version: bool = False,
    ) -> None:
        self.max_bytes = max_bytes
        self.max_depth = max_depth
        self.max_keys = max_keys
        self.require_version = require_version

    def __call__(self, value: Any) -> None:
        if not isinstance(value, dict):
            raise ValidationError("Enter a JSON object.", code="invalid_json_shape")
        if self.require_version and value:
            # Audience resolver documents use ``schema_version`` while visual
            # template documents use ``version``. Both are explicit public
            # contracts and neither may silently fall back to an unversioned
            # interpretation.
            version = value.get("schema_version", value.get("version"))
            if not isinstance(version, int) or isinstance(version, bool) or version < 1:
                raise ValidationError("A positive integer schema version is required.", code="missing_schema_version")

        key_count = 0

        def walk(node: Any, depth: int) -> None:
            nonlocal key_count
            if depth > self.max_depth:
                raise ValidationError("JSON nesting is too deep.", code="json_too_deep")
            if isinstance(node, dict):
                key_count += len(node)
                if key_count > self.max_keys:
                    raise ValidationError("JSON contains too many keys.", code="json_too_many_keys")
                for key, child in node.items():
                    if not isinstance(key, str):
                        raise ValidationError("JSON object keys must be strings.", code="invalid_json_key")
                    walk(child, depth + 1)
            elif isinstance(node, list):
                for child in node:
                    walk(child, depth + 1)

        walk(value, 1)
        try:
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValidationError("Enter valid JSON data.", code="invalid_json") from exc
        if len(encoded) > self.max_bytes:
            raise ValidationError("JSON payload is too large.", code="json_too_large")


def validate_non_secret_json(value: Any) -> None:
    """Reject common secret and direct-PII keys from evidence metadata."""

    BoundedJSONValidator(max_bytes=16_384, max_depth=6, max_keys=96)(value)
    forbidden_fragments = {
        "address",
        "authorization",
        "body",
        "credential",
        "email",
        "html",
        "password",
        "personalization",
        "secret",
        "token",
    }

    def keys(node: Any) -> Iterable[str]:
        if isinstance(node, dict):
            for key, child in node.items():
                yield key.lower()
                yield from keys(child)
        elif isinstance(node, list):
            for child in node:
                yield from keys(child)

    for key in keys(value):
        if any(fragment in key for fragment in forbidden_fragments):
            raise ValidationError("Evidence metadata contains a forbidden key.", code="forbidden_evidence_key")


def _require_same_tenant(instance: models.Model, relation_name: str) -> None:
    relation_id = getattr(instance, f"{relation_name}_id", None)
    tenant_id = getattr(instance, "tenant_id", None)
    if relation_id is None or tenant_id is None:
        return
    related_model = instance._meta.get_field(relation_name).remote_field.model
    if not related_model._base_manager.filter(pk=relation_id, tenant_id=tenant_id).exists():
        raise ValidationError(
            {relation_name: "The referenced record does not belong to this tenant."},
            code="cross_tenant_reference",
        )


def _persisted_values(instance: models.Model, fields: Iterable[str]) -> dict[str, Any] | None:
    if instance._state.adding or instance.pk is None:
        return None
    return type(instance)._base_manager.filter(pk=instance.pk, tenant_id=instance.tenant_id).values(*fields).first()


class MutableTenantModel(TenantScopedModel, TimestampedModel):
    """UUID identity plus actor and soft-deletion projections."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.UUIDField(null=True, blank=True, db_index=True, editable=False)
    updated_by = models.UUIDField(null=True, blank=True, db_index=True, editable=False)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        abstract = True


class AuditedTenantModel(TenantScopedModel, TimestampedModel):
    """Mutable tenant record without soft deletion."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.UUIDField(null=True, blank=True, db_index=True, editable=False)
    updated_by = models.UUIDField(null=True, blank=True, db_index=True, editable=False)

    class Meta:
        abstract = True


class AppendOnlyQuerySet(TenantQuerySet):
    """Prevent QuerySet operations from bypassing append-only evidence."""

    def update(self, **kwargs: Any) -> int:
        raise ImmutableEvidenceError("Append-only evidence cannot be updated.", code="append_only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableEvidenceError("Append-only evidence cannot be deleted.", code="append_only")


class AppendOnlyTenantModel(TenantScopedModel):
    """UUID/created-at base whose rows can only be inserted."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableEvidenceError("Append-only evidence cannot be updated.", code="append_only")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableEvidenceError("Append-only evidence cannot be deleted.", code="append_only")


class StateControlledQuerySet(TenantQuerySet):
    """Reject bulk lifecycle forgery that bypasses row locks and audit."""

    def update(self, **kwargs: Any) -> int:
        if "status" in kwargs:
            raise ValidationError("Status changes must use the registered state machine.", code="state_machine")
        return super().update(**kwargs)


class CampaignQuerySet(StateControlledQuerySet):
    """Prevent bulk deletion from bypassing terminal campaign retention."""

    def delete(self) -> tuple[int, dict[str, int]]:
        if self.filter(status__in=[CampaignStatus.SENT, CampaignStatus.CANCELLED]).exists():
            raise ValidationError("Terminal campaigns cannot be physically deleted.", code="terminal")
        return super().delete()


class TemplateQuerySet(StateControlledQuerySet):
    """Protect archived template content from bulk mutation."""

    IMMUTABLE_FIELDS = frozenset(
        {
            "template_code",
            "template_name",
            "description",
            "category",
            "subject",
            "preview_text",
            "body_html",
            "body_text",
            "design_json",
            "version",
        }
    )

    def update(self, **kwargs: Any) -> int:
        if self.IMMUTABLE_FIELDS.intersection(kwargs) and self.filter(status=TemplateStatus.ARCHIVED).exists():
            raise ValidationError("Archived templates are immutable; clone to a new draft.", code="archived")
        return super().update(**kwargs)


class EmailTemplate(MutableTenantModel):
    """Reusable, versioned email content owned by one tenant."""

    objects = TemplateQuerySet.as_manager()

    template_code = models.CharField(max_length=50)
    template_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=64, default="general")
    subject = models.CharField(max_length=500)
    preview_text = models.CharField(max_length=255, blank=True)
    body_html = models.TextField()
    body_text = models.TextField(blank=True)
    design_json = models.JSONField(
        blank=True,
        default=dict,
        validators=[BoundedJSONValidator(max_bytes=131_072, require_version=True)],
    )
    status = models.CharField(
        max_length=16,
        choices=TemplateStatus.choices,
        default=TemplateStatus.DRAFT,
        db_index=True,
    )
    transition_history = models.JSONField(default=list, blank=True)
    version = models.PositiveIntegerField(default=1)
    usage_count = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "email_templates"
        indexes = [
            models.Index(fields=["tenant_id", "status", "category"], name="em_tmpl_tenant_status_cat"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "template_code"],
                condition=Q(is_deleted=False),
                name="em_tmpl_tenant_code_live_uniq",
            ),
            models.CheckConstraint(condition=Q(version__gte=1), name="em_tmpl_version_positive_ck"),
            models.CheckConstraint(condition=Q(usage_count__gte=0), name="em_tmpl_usage_nonnegative_ck"),
            models.CheckConstraint(condition=Q(status__in=TemplateStatus.values), name="em_tmpl_status_valid_ck"),
            models.CheckConstraint(
                condition=(
                    ~Q(status=TemplateStatus.ACTIVE)
                    | (Q(subject__gt="") & (Q(body_html__gt="") | Q(body_text__gt="")))
                ),
                name="em_tmpl_active_content_ck",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        self.template_code = self.template_code.strip().upper()
        if self._state.adding and self.status != TemplateStatus.DRAFT:
            raise ValidationError("Templates must be created as drafts.", code="state_machine")
        if self.status == TemplateStatus.ACTIVE and (
            not self.subject.strip() or not (self.body_html.strip() or self.body_text.strip())
        ):
            raise ValidationError("Active templates require a subject and at least one body.", code="active_content")

        immutable_fields = (
            "template_code",
            "template_name",
            "description",
            "category",
            "subject",
            "preview_text",
            "body_html",
            "body_text",
            "design_json",
            "status",
            "version",
        )
        previous = _persisted_values(self, ("status", "transition_history", *immutable_fields))
        if (
            previous
            and previous["status"] != self.status
            and previous.get("transition_history") == self.transition_history
        ):
            raise ValidationError(
                "Template status changes must use the registered state machine.",
                code="state_machine",
            )
        if previous and previous["status"] == TemplateStatus.ARCHIVED:
            changed = [field for field in immutable_fields if previous[field] != getattr(self, field)]
            if changed:
                raise ValidationError("Archived templates are immutable; clone to a new draft.", code="archived")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.template_code = self.template_code.strip().upper()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.template_code} - {self.template_name}"


class EmailCampaign(MutableTenantModel):
    """Authoring aggregate and durable campaign-level delivery summary."""

    objects = CampaignQuerySet.as_manager()

    campaign_code = models.CharField(max_length=50)
    campaign_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    campaign_type = models.CharField(max_length=32, default="broadcast")
    audience_resolver_key = models.CharField(max_length=100, default="manual")
    gateway_key = models.CharField(max_length=100, default="django")
    verifier_key = models.CharField(max_length=100, blank=True)
    # ``template_id`` existed as an unsafe UUID column in v1.  It is preserved
    # as a read-only compatibility projection while the real FK uses a new
    # physical column so migration is additive and lossless.
    legacy_template_id = models.UUIDField(null=True, blank=True, db_column="template_id", editable=False)
    legacy_sent_at = models.DateTimeField(null=True, blank=True, db_column="sent_at", editable=False)
    legacy_recipient_count = models.PositiveIntegerField(default=0, db_column="recipient_count", editable=False)
    template = models.ForeignKey(
        EmailTemplate,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="campaigns",
        db_column="template_ref_id",
    )
    subject = models.CharField(max_length=500)
    preview_text = models.CharField(max_length=255, blank=True)
    from_name = models.CharField(max_length=255)
    from_email = models.EmailField(max_length=254)
    reply_to_email = models.EmailField(max_length=254, null=True, blank=True)
    audience_definition = models.JSONField(
        blank=True,
        default=dict,
        validators=[BoundedJSONValidator(max_bytes=32_768, require_version=True)],
    )
    audience_snapshot_at = models.DateTimeField(null=True, blank=True)
    audience_snapshot_evidence = models.JSONField(
        default=dict,
        blank=True,
        validators=[BoundedJSONValidator(max_bytes=32_768)],
    )
    resolved_recipient_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=24, choices=CampaignStatus.choices, default=CampaignStatus.DRAFT)
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    timezone = models.CharField(max_length=63, default="UTC", validators=[validate_timezone_name])
    queue_started_at = models.DateTimeField(null=True, blank=True)
    send_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    content_snapshot_subject = models.CharField(max_length=500, blank=True)
    content_snapshot_html = models.TextField(blank=True)
    content_snapshot_text = models.TextField(blank=True)
    template_version_snapshot = models.PositiveIntegerField(null=True, blank=True)
    sent_count = models.PositiveIntegerField(default=0)
    delivered_count = models.PositiveIntegerField(default=0)
    opened_count = models.PositiveIntegerField(default=0)
    unique_opened_count = models.PositiveIntegerField(default=0)
    clicked_count = models.PositiveIntegerField(default=0)
    unique_clicked_count = models.PositiveIntegerField(default=0)
    bounced_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    unsubscribed_count = models.PositiveIntegerField(default=0)
    complaint_count = models.PositiveIntegerField(default=0)
    transition_history = models.JSONField(default=list, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    last_error_detail = models.TextField(blank=True)

    COUNTER_FIELDS = (
        "resolved_recipient_count",
        "sent_count",
        "delivered_count",
        "opened_count",
        "unique_opened_count",
        "clicked_count",
        "unique_clicked_count",
        "bounced_count",
        "failed_count",
        "unsubscribed_count",
        "complaint_count",
    )

    class Meta:
        db_table = "email_campaigns"
        indexes = [
            models.Index(fields=["tenant_id", "status", "-created_at"], name="em_cmp_tenant_status_created"),
            models.Index(
                fields=["tenant_id", "scheduled_at"],
                condition=Q(status=CampaignStatus.SCHEDULED),
                name="em_cmp_tenant_scheduled",
            ),
            models.Index(fields=["tenant_id", "template", "-created_at"], name="em_cmp_tenant_tmpl_created"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "campaign_code"],
                condition=Q(is_deleted=False),
                name="em_cmp_tenant_code_live_uniq",
            ),
            models.CheckConstraint(
                condition=~Q(status=CampaignStatus.SCHEDULED) | Q(scheduled_at__isnull=False),
                name="em_cmp_scheduled_at_required_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status=CampaignStatus.SENT) | Q(completed_at__isnull=False),
                name="em_cmp_completed_at_required_ck",
            ),
            models.CheckConstraint(
                condition=Q(resolved_recipient_count__gte=0)
                & Q(legacy_recipient_count__gte=0)
                & Q(sent_count__gte=0)
                & Q(delivered_count__gte=0)
                & Q(opened_count__gte=0)
                & Q(unique_opened_count__gte=0)
                & Q(clicked_count__gte=0)
                & Q(unique_clicked_count__gte=0)
                & Q(bounced_count__gte=0)
                & Q(failed_count__gte=0)
                & Q(unsubscribed_count__gte=0)
                & Q(complaint_count__gte=0),
                name="em_cmp_counters_nonnegative_ck",
            ),
            models.CheckConstraint(condition=Q(status__in=CampaignStatus.values), name="em_cmp_status_valid_ck"),
        ]

    def clean(self) -> None:
        super().clean()
        self.campaign_code = self.campaign_code.strip().upper()
        self.from_email = normalize_email_address(self.from_email)
        if self.reply_to_email:
            self.reply_to_email = normalize_email_address(self.reply_to_email)
        validate_timezone_name(self.timezone)
        _require_same_tenant(self, "template")
        if self._state.adding and self.status != CampaignStatus.DRAFT:
            raise ValidationError("Campaigns must be created as drafts.", code="state_machine")
        if self.status == CampaignStatus.SCHEDULED and self.scheduled_at is None:
            raise ValidationError({"scheduled_at": "Scheduled campaigns require a date."}, code="required")
        if self.status == CampaignStatus.SENT and self.completed_at is None:
            raise ValidationError({"completed_at": "Sent campaigns require a completion date."}, code="required")

        previous = _persisted_values(self, ("status", "transition_history"))
        if previous and previous["status"] != self.status and previous["transition_history"] == self.transition_history:
            raise ValidationError(
                "Campaign status changes must use the registered state machine.",
                code="state_machine",
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.campaign_code = self.campaign_code.strip().upper()
        self.from_email = normalize_email_address(self.from_email)
        if self.reply_to_email:
            self.reply_to_email = normalize_email_address(self.reply_to_email)
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.status in {CampaignStatus.SENT, CampaignStatus.CANCELLED}:
            raise ValidationError("Terminal campaigns cannot be physically deleted.", code="terminal")
        return super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.campaign_code} - {self.campaign_name}"


class ConsentRecord(AppendOnlyTenantModel):
    """Immutable evidence for one consent decision."""

    email = models.EmailField(max_length=254)
    purpose = models.CharField(max_length=64, default="marketing")
    status = models.CharField(max_length=16, choices=ConsentStatus.choices)
    lawful_basis = models.CharField(max_length=32, choices=ConsentLawfulBasis.choices)
    source = models.CharField(max_length=32, choices=ConsentSource.choices)
    notice_version = models.CharField(max_length=64)
    captured_at = models.DateTimeField(db_index=True)
    actor_id = models.UUIDField(null=True, blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    user_agent_hash = models.CharField(max_length=64, blank=True)
    supersedes = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseded_by",
    )
    evidence = models.JSONField(default=dict, blank=True, validators=[BoundedJSONValidator(max_bytes=32_768)])

    class Meta:
        db_table = "email_consent_records"
        indexes = [
            models.Index(
                fields=["tenant_id", "email", "purpose", "-captured_at"],
                name="em_consent_tenant_email_time",
            ),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(status__in=ConsentStatus.values), name="em_consent_status_valid_ck"),
            models.CheckConstraint(
                condition=Q(lawful_basis__in=ConsentLawfulBasis.values),
                name="em_consent_basis_valid_ck",
            ),
            models.CheckConstraint(condition=Q(source__in=ConsentSource.values), name="em_consent_source_valid_ck"),
        ]

    def clean(self) -> None:
        super().clean()
        self.email = normalize_email_address(self.email)
        if self.supersedes_id:
            _require_same_tenant(self, "supersedes")
            predecessor = self.supersedes
            if predecessor.email != self.email or predecessor.purpose != self.purpose:
                raise ValidationError(
                    {"supersedes": "A superseded consent must have the same email and purpose."},
                    code="invalid_supersession",
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = normalize_email_address(self.email)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.purpose}: {self.status} ({self.captured_at.isoformat()})"


class CampaignRecipient(TenantScopedModel, TimestampedModel):
    """One deduplicated, consent-evaluated campaign recipient snapshot."""

    objects = StateControlledQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(EmailCampaign, on_delete=models.PROTECT, related_name="recipients")
    recipient_key = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(max_length=254)
    display_name = models.CharField(max_length=255, blank=True)
    personalization_data = models.JSONField(
        default=dict,
        blank=True,
        validators=[BoundedJSONValidator(max_bytes=65_536)],
    )
    consent_record = models.ForeignKey(ConsentRecord, null=True, blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, choices=RecipientStatus.choices, default=RecipientStatus.RESOLVED)
    suppression_reason = models.CharField(max_length=64, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    queued_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    transition_history = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "email_campaign_recipients"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "campaign", "email"],
                name="em_recipient_campaign_email_uniq",
            ),
            models.CheckConstraint(condition=Q(status__in=RecipientStatus.values), name="em_recipient_status_valid_ck"),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "campaign", "status"], name="em_recipient_cmp_status"),
            models.Index(fields=["tenant_id", "email", "-created_at"], name="em_recipient_email_created"),
        ]

    def clean(self) -> None:
        super().clean()
        self.email = normalize_email_address(self.email)
        _require_same_tenant(self, "campaign")
        _require_same_tenant(self, "consent_record")
        if self._state.adding and self.status not in {RecipientStatus.RESOLVED, RecipientStatus.SUPPRESSED}:
            raise ValidationError("Recipients must enter through audience resolution.", code="state_machine")
        if self.consent_record_id and (
            self.consent_record.email != self.email or self.consent_record.purpose != "marketing"
        ):
            raise ValidationError(
                {"consent_record": "Consent evidence must match this recipient and marketing purpose."},
                code="invalid_consent_reference",
            )
        if self.status in {RecipientStatus.ACCEPTED, RecipientStatus.DELIVERED} and (
            self._state.adding or not self.delivery_attempts.exists()
        ):
            raise ValidationError(
                "Accepted or delivered recipients require delivery evidence.",
                code="missing_attempt",
            )

        previous = _persisted_values(self, ("status", "transition_history"))
        if previous and previous["status"] != self.status and previous["transition_history"] == self.transition_history:
            raise ValidationError(
                "Recipient status changes must use the registered state machine.",
                code="state_machine",
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = normalize_email_address(self.email)
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.campaign_id}: {self.status}"


class DeliveryAttempt(TenantScopedModel, TimestampedModel):
    """Durable record of a real gateway submission attempt."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(CampaignRecipient, on_delete=models.PROTECT, related_name="delivery_attempts")
    attempt_number = models.PositiveSmallIntegerField()
    job_id = models.UUIDField()
    idempotency_key = models.CharField(max_length=255)
    gateway_key = models.CharField(max_length=100)
    status = models.CharField(
        max_length=16,
        choices=DeliveryAttemptStatus.choices,
        default=DeliveryAttemptStatus.QUEUED,
    )
    provider_message_id = models.CharField(max_length=255, blank=True)
    provider_status_code = models.CharField(max_length=64, blank=True)
    response_evidence = models.JSONField(default=dict, blank=True, validators=[validate_non_secret_json])
    error_code = models.CharField(max_length=64, blank=True)
    error_detail = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "email_delivery_attempts"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "idempotency_key"], name="em_attempt_idempotency_uniq"),
            models.UniqueConstraint(
                fields=["tenant_id", "recipient", "attempt_number"],
                name="em_attempt_recipient_number_uniq",
            ),
            models.CheckConstraint(condition=Q(attempt_number__gte=1), name="em_attempt_number_positive_ck"),
            models.CheckConstraint(
                condition=Q(status__in=DeliveryAttemptStatus.values),
                name="em_attempt_status_valid_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "status", "created_at"], name="em_attempt_status_created"),
            models.Index(
                fields=["tenant_id", "provider_message_id"],
                condition=~Q(provider_message_id=""),
                name="em_attempt_provider_message",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "recipient")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.recipient_id} attempt {self.attempt_number}: {self.status}"


class DeliveryEvent(AppendOnlyTenantModel):
    """Idempotent, immutable provider or first-party delivery event."""

    recipient = models.ForeignKey(CampaignRecipient, on_delete=models.PROTECT, related_name="events")
    attempt = models.ForeignKey(
        DeliveryAttempt,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="events",
    )
    provider_event_id = models.CharField(max_length=255)
    gateway_key = models.CharField(max_length=100)
    event_type = models.CharField(max_length=16, choices=DeliveryEventType.choices)
    occurred_at = models.DateTimeField(db_index=True)
    link_url_hash = models.CharField(max_length=64, blank=True)
    bounce_class = models.CharField(max_length=32, choices=BounceClass.choices, blank=True)
    metadata = models.JSONField(default=dict, blank=True, validators=[validate_non_secret_json])
    correlation_id = models.CharField(max_length=64, db_index=True)

    class Meta:
        db_table = "email_delivery_events"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "gateway_key", "provider_event_id"],
                name="em_event_provider_id_uniq",
            ),
            models.CheckConstraint(condition=Q(event_type__in=DeliveryEventType.values), name="em_event_type_valid_ck"),
            models.CheckConstraint(
                condition=(
                    (Q(event_type=DeliveryEventType.BOUNCED) & Q(bounce_class__in=BounceClass.values))
                    | (~Q(event_type=DeliveryEventType.BOUNCED) & Q(bounce_class=""))
                ),
                name="em_event_bounce_class_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "recipient", "occurred_at"], name="em_event_recipient_time"),
            models.Index(fields=["tenant_id", "event_type", "occurred_at"], name="em_event_type_time"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "recipient")
        _require_same_tenant(self, "attempt")
        if self.attempt_id and self.attempt.recipient_id != self.recipient_id:
            raise ValidationError({"attempt": "Attempt must belong to this recipient."}, code="invalid_attempt")
        if self.event_type == DeliveryEventType.BOUNCED and not self.bounce_class:
            raise ValidationError({"bounce_class": "Bounce events require a bounce class."}, code="required")
        if self.event_type != DeliveryEventType.BOUNCED and self.bounce_class:
            raise ValidationError({"bounce_class": "Bounce class is valid only for bounce events."}, code="invalid")

    def __str__(self) -> str:
        return f"{self.event_type} ({self.gateway_key}:{self.provider_event_id})"


class SuppressionEntry(AuditedTenantModel):
    """Lifecycle-controlled block on marketing or all email delivery."""

    email = models.EmailField(max_length=254)
    scope = models.CharField(max_length=16, choices=SuppressionScope.choices)
    reason = models.CharField(max_length=16, choices=SuppressionReason.choices)
    source = models.CharField(max_length=16, choices=SuppressionSource.choices)
    active = models.BooleanField(default=True)
    suppressed_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivated_by = models.UUIDField(null=True, blank=True)
    evidence_event = models.ForeignKey(DeliveryEvent, null=True, blank=True, on_delete=models.PROTECT)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "email_suppression_entries"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "email", "scope"],
                condition=Q(active=True),
                name="em_suppress_email_scope_live_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(reason__in=[SuppressionReason.UNSUBSCRIBE, SuppressionReason.COMPLAINT, SuppressionReason.LEGAL])
                    | Q(expires_at__isnull=True)
                ),
                name="em_suppress_permanent_no_expiry_ck",
            ),
            models.CheckConstraint(
                condition=Q(active=True) | Q(deactivated_at__isnull=False),
                name="em_suppress_deactivated_at_ck",
            ),
            models.CheckConstraint(
                condition=Q(scope__in=SuppressionScope.values),
                name="em_suppress_scope_valid_ck",
            ),
            models.CheckConstraint(
                condition=Q(reason__in=SuppressionReason.values),
                name="em_suppress_reason_valid_ck",
            ),
            models.CheckConstraint(
                condition=Q(source__in=SuppressionSource.values),
                name="em_suppress_source_valid_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "active", "reason", "-suppressed_at"],
                name="em_suppress_active_reason_time",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        self.email = normalize_email_address(self.email)
        _require_same_tenant(self, "evidence_event")
        if self.reason in {
            SuppressionReason.UNSUBSCRIBE,
            SuppressionReason.COMPLAINT,
            SuppressionReason.LEGAL,
        } and self.expires_at is not None:
            raise ValidationError({"expires_at": "This suppression reason cannot expire."}, code="permanent")
        if not self.active and self.deactivated_at is None:
            raise ValidationError({"deactivated_at": "Deactivation time is required."}, code="required")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = normalize_email_address(self.email)
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.scope}: {self.reason} ({'active' if self.active else 'inactive'})"


__all__ = [
    "BounceClass",
    "BoundedJSONValidator",
    "CampaignRecipient",
    "CampaignStatus",
    "ConsentLawfulBasis",
    "ConsentRecord",
    "ConsentSource",
    "ConsentStatus",
    "DeliveryAttempt",
    "DeliveryAttemptStatus",
    "DeliveryEvent",
    "DeliveryEventType",
    "EmailCampaign",
    "EmailTemplate",
    "ImmutableEvidenceError",
    "LawfulBasis",
    "RecipientStatus",
    "SuppressionEntry",
    "SuppressionReason",
    "SuppressionScope",
    "SuppressionSource",
    "Source",
    "TemplateStatus",
    "normalize_email_address",
    "validate_timezone_name",
]
