"""Canonical tenant-owned notification persistence model."""

from __future__ import annotations

import json
import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from src.core.tenancy import TenantQuerySet, TenantScopedModel, TimestampedModel


class Channel(models.TextChoices):
    IN_APP = "in_app", "In app"
    EMAIL = "email", "Email"
    SMS = "sms", "SMS"
    PUSH = "push", "Push"
    WEBHOOK = "webhook", "Webhook"


class TemplateStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class NotificationStatus(models.TextChoices):
    UNREAD = "unread", "Unread"
    READ = "read", "Read"
    ARCHIVED = "archived", "Archived"


class NotificationType(models.TextChoices):
    INFO = "info", "Information"
    SUCCESS = "success", "Success"
    WARNING = "warning", "Warning"
    ERROR = "error", "Error"
    WORKFLOW = "workflow", "Workflow"
    APPROVAL = "approval", "Approval"
    SYSTEM = "system", "System"
    SECURITY = "security", "Security"


class DeliveryStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    QUEUED = "queued", "Queued"
    SENDING = "sending", "Sending"
    SENT = "sent", "Sent"
    DELIVERED = "delivered", "Delivered"
    RETRY_WAIT = "retry_wait", "Retry wait"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    SKIPPED = "skipped", "Skipped"


class ImmutableRecordError(RuntimeError):
    """Raised when append-only evidence is changed or removed."""


class AppendOnlyQuerySet(TenantQuerySet):
    def update(self, **kwargs: Any) -> int:
        raise ImmutableRecordError("Append-only notification evidence cannot be updated")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableRecordError("Append-only notification evidence cannot be deleted")


class AppendOnlyModel(TenantScopedModel):
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableRecordError(f"{type(self).__name__} records are append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableRecordError(f"{type(self).__name__} records are append-only")


def _same_tenant(instance: TenantScopedModel, related: object, field: str) -> None:
    if related is not None and getattr(related, "tenant_id", None) != instance.tenant_id:
        raise ValidationError({field: "Related object must belong to the same tenant."})


class NotificationTemplate(TenantScopedModel, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    locale = models.CharField(max_length=16, default="en")
    status = models.CharField(max_length=16, choices=TemplateStatus.choices, default=TemplateStatus.DRAFT)
    active_version = models.ForeignKey("NotificationTemplateVersion", null=True, blank=True, on_delete=models.PROTECT, related_name="active_for_templates")
    transition_history = models.JSONField(default=list, blank=True)
    created_by = models.UUIDField()
    updated_by = models.UUIDField()

    class Meta:
        db_table = "notifications_templates"
        constraints = [
            models.UniqueConstraint(Lower("code"), "channel", "locale", "tenant_id", condition=~models.Q(status="archived"), name="notif_tpl_identity_uniq"),
            models.CheckConstraint(condition=~models.Q(code=""), name="notif_tpl_code_nonempty"),
            models.CheckConstraint(condition=~models.Q(category=""), name="notif_tpl_category_nonempty"),
            models.CheckConstraint(condition=~models.Q(name=""), name="notif_tpl_name_nonempty"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "channel", "code"), name="notif_tpl_state_idx"),
            models.Index(fields=("tenant_id", "category", "status"), name="notif_tpl_category_idx"),
        ]

    def clean(self) -> None:
        self.code = self.code.strip().lower(); self.category = self.category.strip().lower(); self.name = self.name.strip()
        _same_tenant(self, self.active_version, "active_version")
        if self.active_version and self.active_version.template_id != self.id:
            raise ValidationError({"active_version": "Active version must belong to this template."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.active_version_id:
            _same_tenant(self, self.active_version, "active_version")
            if self.active_version.template_id != self.id: raise ValidationError({"active_version": "Active version must belong to this template."})
        super().save(*args, **kwargs)


class NotificationTemplateVersion(AppendOnlyModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(NotificationTemplate, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    subject_template = models.CharField(max_length=500, blank=True)
    body_template = models.TextField()
    variables_schema = models.JSONField(default=dict)
    content_type = models.CharField(max_length=32, choices=(("text/plain", "Plain text"), ("text/html", "HTML"), ("application/json", "JSON")), default="text/plain")
    created_by = models.UUIDField()
    correlation_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_template_versions"
        constraints = [models.UniqueConstraint(fields=("tenant_id", "template", "version"), name="notif_tpl_version_uniq")]
        indexes = [models.Index(fields=("tenant_id", "template", "-version"), name="notif_tpl_version_idx")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        _same_tenant(self, self.template, "template")
        super().save(*args, **kwargs)


class NotificationDelivery(TenantScopedModel, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template_version = models.ForeignKey(NotificationTemplateVersion, on_delete=models.PROTECT, related_name="deliveries")
    job_id = models.UUIDField(null=True, blank=True, db_index=True)
    idempotency_key = models.CharField(max_length=255)
    recipient_type = models.CharField(max_length=20, choices=(("user", "User"), ("email", "Email"), ("phone", "Phone"), ("push_endpoint", "Push endpoint"), ("webhook_endpoint", "Webhook endpoint")))
    recipient_user_id = models.UUIDField(null=True, blank=True, db_index=True)
    recipient_ciphertext = models.TextField(blank=True)
    recipient_fingerprint = models.CharField(max_length=64)
    recipient_display = models.CharField(max_length=255)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    category = models.CharField(max_length=100)
    priority = models.PositiveSmallIntegerField(default=5)
    status = models.CharField(max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING)
    context_data = models.JSONField(default=dict, blank=True)
    rendered_subject = models.CharField(max_length=500, blank=True)
    rendered_body = models.TextField(blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    provider_message_id = models.CharField(max_length=255, blank=True)
    failure_code = models.CharField(max_length=100, blank=True)
    failure_message = models.TextField(blank=True)
    transition_history = models.JSONField(default=list, blank=True)
    created_by = models.UUIDField()
    correlation_id = models.UUIDField(db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications_deliveries"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="notif_delivery_idem_uniq"),
            models.CheckConstraint(condition=models.Q(priority__gte=1, priority__lte=10), name="notif_delivery_priority_ck"),
            models.CheckConstraint(condition=models.Q(max_attempts__gte=1, max_attempts__lte=10), name="notif_delivery_max_attempts_ck"),
            models.CheckConstraint(condition=models.Q(attempt_count__lte=models.F("max_attempts")), name="notif_delivery_attempt_bound_ck"),
            models.CheckConstraint(condition=~models.Q(status="sent") | (models.Q(sent_at__isnull=False) & ~models.Q(provider_message_id="")), name="notif_delivery_sent_evidence_ck"),
            models.CheckConstraint(condition=~models.Q(status="delivered") | models.Q(delivered_at__isnull=False), name="notif_delivery_delivered_ck"),
            models.CheckConstraint(condition=~models.Q(status="failed") | ~models.Q(failure_code=""), name="notif_delivery_failed_ck"),
            models.CheckConstraint(condition=~models.Q(status="retry_wait") | models.Q(next_attempt_at__isnull=False), name="notif_delivery_retry_ck"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "scheduled_at", "priority", "created_at"), name="notif_delivery_queue_idx"),
            models.Index(fields=("tenant_id", "recipient_user_id", "-created_at"), name="notif_delivery_user_idx"),
            models.Index(fields=("tenant_id", "channel", "status", "-created_at"), name="notif_delivery_channel_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        _same_tenant(self, self.template_version, "template_version")
        super().save(*args, **kwargs)


class Notification(TenantScopedModel, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(db_index=True)
    delivery = models.OneToOneField(NotificationDelivery, null=True, blank=True, on_delete=models.SET_NULL, related_name="inbox_notification")
    notification_type = models.CharField(max_length=20, choices=NotificationType.choices, default=NotificationType.INFO)
    category = models.CharField(max_length=100, default="general")
    title = models.CharField(max_length=255)
    message = models.TextField()
    status = models.CharField(max_length=16, choices=NotificationStatus.choices, default=NotificationStatus.UNREAD)
    read_at = models.DateTimeField(null=True, blank=True)
    action_url = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    transition_history = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "notifications_notifications"
        constraints = [
            models.CheckConstraint(condition=(models.Q(status="read", read_at__isnull=False) | (~models.Q(status="read") & models.Q(read_at__isnull=True))), name="notif_inbox_read_at_ck"),
            models.CheckConstraint(condition=~models.Q(category=""), name="notif_inbox_category_ck"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "user_id", "status", "-created_at"), name="notif_inbox_status_idx"),
            models.Index(fields=("tenant_id", "user_id", "expires_at"), name="notif_inbox_expiry_idx"),
        ]

    def clean(self) -> None:
        _same_tenant(self, self.delivery, "delivery")
        if len(json.dumps(self.metadata, separators=(",", ":")).encode()) > 65536:
            raise ValidationError({"metadata": "Metadata exceeds the safe maximum."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.delivery_id: _same_tenant(self, self.delivery, "delivery")
        super().save(*args, **kwargs)


class NotificationDeliveryAttempt(AppendOnlyModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery = models.ForeignKey(NotificationDelivery, on_delete=models.PROTECT, related_name="attempts")
    attempt_number = models.PositiveIntegerField()
    adapter_key = models.CharField(max_length=100)
    outcome = models.CharField(max_length=20, choices=(("accepted", "Accepted"), ("retryable_failure", "Retryable failure"), ("permanent_failure", "Permanent failure"), ("circuit_open", "Circuit open"), ("timeout", "Timeout")))
    provider_message_id = models.CharField(max_length=255, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    latency_ms = models.PositiveIntegerField()
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField()
    correlation_id = models.UUIDField(db_index=True)

    class Meta:
        db_table = "notifications_delivery_attempts"
        constraints = [models.UniqueConstraint(fields=("tenant_id", "delivery", "attempt_number"), name="notif_attempt_number_uniq")]
        indexes = [models.Index(fields=("tenant_id", "delivery", "attempt_number"), name="notif_attempt_delivery_idx")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        _same_tenant(self, self.delivery, "delivery"); super().save(*args, **kwargs)


class NotificationPreference(TenantScopedModel, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(db_index=True)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    category = models.CharField(max_length=100)
    enabled = models.BooleanField(default=True)
    digest_mode = models.CharField(max_length=16, choices=(("immediate", "Immediate"), ("hourly", "Hourly"), ("daily", "Daily"), ("weekly", "Weekly")), default="immediate")
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    timezone = models.CharField(max_length=64, default="UTC")
    migration_provenance = models.JSONField(default=dict, blank=True, editable=False)

    class Meta:
        db_table = "notifications_preferences"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "user_id", "channel", "category"), name="notif_preference_uniq"),
            models.CheckConstraint(condition=(models.Q(quiet_hours_start__isnull=True, quiet_hours_end__isnull=True) | models.Q(quiet_hours_start__isnull=False, quiet_hours_end__isnull=False)), name="notif_preference_quiet_ck"),
            models.CheckConstraint(condition=~models.Q(category__in=("security_alerts", "password_reset"), enabled=False), name="notif_preference_mandatory_ck"),
        ]
        indexes = [models.Index(fields=("tenant_id", "user_id", "channel"), name="notif_preference_user_idx")]


class NotificationEndpoint(TenantScopedModel, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(null=True, blank=True, db_index=True)
    kind = models.CharField(max_length=20, choices=(("push", "Push"), ("webhook", "Webhook")))
    device_type = models.CharField(max_length=20, choices=(("", "None"), ("web", "Web"), ("android", "Android"), ("ios", "iOS")), blank=True)
    address_ciphertext = models.TextField()
    fingerprint = models.CharField(max_length=64)
    display_name = models.CharField(max_length=255)
    secret_ref = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.UUIDField()
    migration_provenance = models.JSONField(default=dict, blank=True, editable=False)

    class Meta:
        db_table = "notifications_endpoints"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "kind", "fingerprint"), name="notif_endpoint_fingerprint_uniq"),
            models.CheckConstraint(condition=(models.Q(kind="push", user_id__isnull=False, device_type__in=("web", "android", "ios")) | models.Q(kind="webhook", device_type="")), name="notif_endpoint_kind_ck"),
        ]
        indexes = [models.Index(fields=("tenant_id", "user_id", "kind", "is_active"), name="notif_endpoint_user_idx")]


class NotificationConfiguration(TenantScopedModel, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.CharField(max_length=20, choices=(("development", "Development"), ("staging", "Staging"), ("production", "Production")))
    active_version = models.PositiveIntegerField(default=1)
    document = models.JSONField(default=dict)
    created_by = models.UUIDField()
    updated_by = models.UUIDField()

    class Meta:
        db_table = "notifications_configurations"
        constraints = [models.UniqueConstraint(fields=("tenant_id", "environment"), name="notif_configuration_env_uniq")]


class NotificationConfigurationVersion(AppendOnlyModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(NotificationConfiguration, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    document = models.JSONField()
    checksum = models.CharField(max_length=64)
    previous_version_id = models.UUIDField(null=True, blank=True)
    created_by = models.UUIDField()
    correlation_id = models.UUIDField(db_index=True)
    change_reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_configuration_versions"
        constraints = [models.UniqueConstraint(fields=("tenant_id", "configuration", "version"), name="notif_config_version_uniq")]
        indexes = [models.Index(fields=("tenant_id", "configuration", "-version"), name="notif_config_version_idx")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        _same_tenant(self, self.configuration, "configuration"); super().save(*args, **kwargs)


class NotificationConfigurationAudit(AppendOnlyModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(NotificationConfiguration, on_delete=models.PROTECT, related_name="audits")
    version = models.ForeignKey(NotificationConfigurationVersion, on_delete=models.PROTECT, related_name="audits")
    action = models.CharField(max_length=20, choices=(("created", "Created"), ("updated", "Updated"), ("imported", "Imported"), ("rolled_back", "Rolled back"), ("activated", "Activated")))
    diff = models.JSONField(default=list)
    actor_id = models.UUIDField()
    correlation_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_configuration_audits"
        indexes = [models.Index(fields=("tenant_id", "configuration", "-created_at"), name="notif_config_audit_idx")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        _same_tenant(self, self.configuration, "configuration"); _same_tenant(self, self.version, "version")
        if self.version.configuration_id != self.configuration_id: raise ValidationError({"version": "Version must belong to the configuration."})
        super().save(*args, **kwargs)


__all__ = [
    "Channel", "DeliveryStatus", "ImmutableRecordError", "Notification",
    "NotificationConfiguration", "NotificationConfigurationAudit",
    "NotificationConfigurationVersion", "NotificationDelivery",
    "NotificationDeliveryAttempt", "NotificationEndpoint", "NotificationPreference",
    "NotificationStatus", "NotificationTemplate", "NotificationTemplateVersion",
    "NotificationType", "TemplateStatus",
]
