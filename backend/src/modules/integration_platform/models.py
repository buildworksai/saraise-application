"""Persistence contract for the open integration foundation.

Connector definitions are platform-global catalog entries.  Every other
aggregate carries the canonical UUID tenant boundary directly, including
credentials and operational delivery evidence.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from src.core.tenancy import TenantScopedModel, TimestampedModel

from .configuration import DEFAULT_CONFIGURATION

_WEBHOOK_POLICY = DEFAULT_CONFIGURATION["webhooks"]
_VALIDATION_POLICY = DEFAULT_CONFIGURATION["validation"]
_MAPPING_POLICY = DEFAULT_CONFIGURATION["mapping"]
assert isinstance(_WEBHOOK_POLICY, dict)
assert isinstance(_VALIDATION_POLICY, dict)
assert isinstance(_MAPPING_POLICY, dict)

def generate_uuid() -> str:
    """Compatibility callable retained for the immutable 0001/0002 migrations."""
    return str(uuid.uuid4())


class ConnectorType(models.TextChoices):
    API = "api", "API"
    WEBHOOK = "webhook", "Webhook"
    DATABASE = "database", "Database"
    FILE = "file", "File"
    MESSAGE_QUEUE = "message_queue", "Message queue"


class ConnectorCapability(models.TextChoices):
    TEST = "test", "Test"
    PULL = "pull", "Pull"
    PUSH = "push", "Push"
    RECEIVE = "receive", "Receive"
    DELIVER = "deliver", "Deliver"


class ConnectorAccessPolicy(models.TextChoices):
    PUBLIC = "public", "Public"
    ENTITLEMENT_REQUIRED = "entitlement_required", "Entitlement required"


class IntegrationStatus(models.TextChoices):
    INACTIVE = "inactive", "Inactive"
    TESTING = "testing", "Testing"
    ACTIVE = "active", "Active"
    ERROR = "error", "Error"


class CredentialType(models.TextChoices):
    API_KEY = "api_key", "API key"
    OAUTH_TOKEN = "oauth_token", "OAuth token"
    USERNAME_PASSWORD = "username_password", "Username/password"
    CERTIFICATE = "certificate", "Certificate"


class CredentialStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    REVOKED = "revoked", "Revoked"
    EXPIRED = "expired", "Expired"


class WebhookDirection(models.TextChoices):
    INBOUND = "inbound", "Inbound"
    OUTBOUND = "outbound", "Outbound"


class WebhookStatus(models.TextChoices):
    INACTIVE = "inactive", "Inactive"
    ACTIVE = "active", "Active"
    ERROR = "error", "Error"


class DeliveryStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    DELIVERING = "delivering", "Delivering"
    RETRYING = "retrying", "Retrying"
    DELIVERED = "delivered", "Delivered"
    DEAD_LETTER = "dead_letter", "Dead letter"
    CANCELLED = "cancelled", "Cancelled"


def _validate_schema(value: object, field: str) -> None:
    if not isinstance(value, dict):
        raise ValidationError({field: "A JSON Schema object is required."})
    try:
        Draft202012Validator.check_schema(value)
    except SchemaError as exc:
        raise ValidationError({field: f"Invalid JSON Schema: {exc.message}"}) from exc
    if value and value.get("type") not in (None, "object"):
        raise ValidationError({field: "Connector schemas must describe an object."})


def _validate_capabilities(value: object) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValidationError({"capabilities": "Capabilities must be a string array."})
    if len(value) != len(set(value)):
        raise ValidationError({"capabilities": "Capabilities must be unique."})
    unknown = set(value) - set(ConnectorCapability.values)
    if unknown:
        raise ValidationError({"capabilities": f"Unsupported capabilities: {', '.join(sorted(unknown))}."})


class MutableTenantModel(TenantScopedModel, TimestampedModel):
    """Audit and recoverable deletion fields shared by mutable resources."""

    created_by = models.UUIDField()
    updated_by = models.UUIDField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.UUIDField(null=True, blank=True)

    class Meta:
        abstract = True


class GuardedStateModel(models.Model):
    """Reject status mutation that did not append matching transition evidence."""

    class Meta:
        abstract = True

    def _validate_guarded_status(self) -> None:
        if self._state.adding or not self.pk:
            return
        previous = type(self)._default_manager.filter(pk=self.pk).values("status", "transition_history").first()
        if previous is None or previous["status"] == self.status:
            return
        old_history = previous["transition_history"] or []
        history = getattr(self, "transition_history", None)
        if not isinstance(history, list) or len(history) != len(old_history) + 1:
            raise ValidationError({"status": "Lifecycle changes must use the registered state machine."})
        record = history[-1]
        if not isinstance(record, dict) or record.get("from_state") != previous["status"] or record.get("to_state") != self.status:
            raise ValidationError({"status": "Transition evidence does not match the lifecycle change."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._validate_guarded_status()
        super().save(*args, **kwargs)


class Connector(TimestampedModel):
    """Platform-global connector descriptor; it never stores tenant configuration."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    connector_type = models.CharField(max_length=32, choices=ConnectorType.choices)
    adapter_key = models.CharField(max_length=200, unique=True)
    version = models.CharField(max_length=32)
    schema = models.JSONField(default=dict, blank=True)
    credential_schema = models.JSONField(default=dict, blank=True)
    capabilities = models.JSONField(default=list, blank=True)
    module_id = models.CharField(max_length=100, default="integration-platform")
    access_policy = models.CharField(
        max_length=32,
        choices=ConnectorAccessPolicy.choices,
        default=ConnectorAccessPolicy.PUBLIC,
    )
    required_entitlement = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_connectors"
        ordering = ("name", "version", "id")
        constraints = [models.UniqueConstraint(fields=("key", "version"), name="intplat_conn_key_ver_uniq")]
        indexes = [models.Index(fields=("connector_type", "is_active"), name="intplat_conn_type_active_idx")]

    def clean(self) -> None:
        super().clean()
        _validate_schema(self.schema, "schema")
        _validate_schema(self.credential_schema, "credential_schema")
        _validate_capabilities(self.capabilities)
        if self.access_policy == ConnectorAccessPolicy.ENTITLEMENT_REQUIRED and not self.required_entitlement:
            raise ValidationError({"required_entitlement": "An entitlement is required by this access policy."})
        if self.access_policy == ConnectorAccessPolicy.PUBLIC and self.required_entitlement:
            raise ValidationError({"required_entitlement": "Public connectors cannot declare an entitlement."})

    def __str__(self) -> str:
        return f"{self.name} ({self.key}@{self.version})"


class Integration(GuardedStateModel, MutableTenantModel):
    """A tenant's non-secret configuration for one connector."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connector = models.ForeignKey(Connector, on_delete=models.PROTECT, related_name="integrations")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    integration_type = models.CharField(max_length=32, choices=ConnectorType.choices)
    config = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=IntegrationStatus.choices, default=IntegrationStatus.INACTIVE)
    transition_history = models.JSONField(default=list, blank=True)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_test_job_id = models.UUIDField(null=True, blank=True)
    last_sync_job_id = models.UUIDField(null=True, blank=True)
    last_error_code = models.CharField(max_length=100, blank=True)
    last_error_message = models.TextField(blank=True)

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_integrations"
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "name"), condition=Q(is_deleted=False), name="intplat_integ_tenant_name_live_uniq"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "created_at"), name="intplat_integ_tenant_status_idx"),
            models.Index(fields=("tenant_id", "connector", "status"), name="intplat_integ_tenant_conn_idx"),
            models.Index(fields=("tenant_id", "integration_type", "is_deleted"), name="intplat_integ_tenant_type_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.connector_id and self.connector.connector_type != self.integration_type:
            raise ValidationError({"integration_type": "Must match the selected connector type."})

    def __str__(self) -> str:
        return f"{self.name} ({self.integration_type})"


class IntegrationCredential(GuardedStateModel, TenantScopedModel, TimestampedModel):
    """Versioned encrypted credential material with metadata-only read surfaces."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE, related_name="credentials")
    credential_type = models.CharField(max_length=32, choices=CredentialType.choices)
    encrypted_value = models.TextField()
    display_hint = models.CharField(max_length=100, blank=True)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=CredentialStatus.choices, default=CredentialStatus.ACTIVE)
    transition_history = models.JSONField(default=list, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    rotated_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.UUIDField()
    revoked_by = models.UUIDField(null=True, blank=True)

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_credentials"
        ordering = ("credential_type", "-version", "id")
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "integration", "credential_type", "version"), name="intplat_cred_version_uniq"),
            models.UniqueConstraint(fields=("tenant_id", "integration", "credential_type"), condition=Q(status=CredentialStatus.ACTIVE), name="intplat_cred_one_active_uniq"),
        ]
        indexes = [models.Index(fields=("tenant_id", "integration", "status"), name="intplat_cred_tenant_int_idx")]

    def clean(self) -> None:
        super().clean()
        if self.integration_id and self.tenant_id != self.integration.tenant_id:
            raise ValidationError({"integration": "Credential and integration must belong to the same tenant."})

    def __str__(self) -> str:
        return f"{self.credential_type} v{self.version} ({self.status})"


_EVENT_RE = re.compile(str(_VALIDATION_POLICY["event_name_pattern"]))


class Webhook(GuardedStateModel, MutableTenantModel):
    """Signed inbound or outbound webhook configuration."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    direction = models.CharField(max_length=20, choices=WebhookDirection.choices)
    url = models.URLField(max_length=2000, blank=True)
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    events = models.JSONField(default=list)
    encrypted_signing_secret = models.TextField()
    config = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=WebhookStatus.choices, default=WebhookStatus.INACTIVE)
    transition_history = models.JSONField(default=list, blank=True)
    timeout_seconds = models.PositiveSmallIntegerField(default=int(_WEBHOOK_POLICY["timeout_seconds_default"]))
    max_attempts = models.PositiveSmallIntegerField(default=int(_WEBHOOK_POLICY["max_attempts_default"]))
    last_received_at = models.DateTimeField(null=True, blank=True)
    last_delivered_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=100, blank=True)

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_webhooks"
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "name"), condition=Q(is_deleted=False), name="intplat_hook_tenant_name_live_uniq"),
            models.CheckConstraint(condition=Q(timeout_seconds__gte=1, timeout_seconds__lte=30), name="intplat_hook_timeout_range"),
            models.CheckConstraint(condition=Q(max_attempts__gte=1, max_attempts__lte=10), name="intplat_hook_attempt_range"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "direction", "status"), name="intplat_hook_tenant_dir_idx"),
            models.Index(fields=("tenant_id", "public_id"), name="intplat_hook_tenant_pub_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.direction == WebhookDirection.OUTBOUND and not self.url:
            raise ValidationError({"url": "Outbound webhooks require a URL."})
        if self.direction == WebhookDirection.INBOUND and self.url:
            raise ValidationError({"url": "Inbound webhooks cannot define an outbound URL."})
        if not isinstance(self.events, list) or not self.events or any(not isinstance(item, str) or not _EVENT_RE.fullmatch(item) for item in self.events):
            raise ValidationError({"events": "A non-empty list of registered event names is required."})
        if len(self.events) != len(set(self.events)):
            raise ValidationError({"events": "Event names must be unique."})
        timeout_min, timeout_max = int(_WEBHOOK_POLICY["timeout_seconds_min"]), int(_WEBHOOK_POLICY["timeout_seconds_max"])
        attempts_min, attempts_max = int(_WEBHOOK_POLICY["max_attempts_min"]), int(_WEBHOOK_POLICY["max_attempts_max"])
        if not timeout_min <= self.timeout_seconds <= timeout_max:
            raise ValidationError({"timeout_seconds": f"Must be between {timeout_min} and {timeout_max}."})
        if not attempts_min <= self.max_attempts <= attempts_max:
            raise ValidationError({"max_attempts": f"Must be between {attempts_min} and {attempts_max}."})

    def __str__(self) -> str:
        return f"{self.name} ({self.direction})"


class ImmutableDeliveryError(RuntimeError):
    """Raised when operational evidence is mutated or deleted."""


class ImmutableRecordError(RuntimeError):
    """Raised when an append-only evidence row is tampered with."""


class ImmutableEvidenceQuerySet(models.QuerySet[Any]):
    """Block bulk tampering that would bypass model save/delete guards."""

    def for_tenant(self, tenant_id: uuid.UUID) -> "ImmutableEvidenceQuerySet":
        return self.filter(tenant_id=tenant_id)

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ImmutableRecordError("Evidence cannot be updated")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableRecordError("Evidence cannot be deleted")


class IntegrationPlatformConfiguration(TenantScopedModel, TimestampedModel):
    """Current tenant/environment configuration pointer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.CharField(max_length=64, default="default")
    version = models.PositiveIntegerField(default=1)
    document = models.JSONField()
    updated_by = models.UUIDField()

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_configuration"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "environment"),
                name="intplat_config_tenant_env_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "environment", "version"),
                name="intplat_config_tenant_ver_idx",
            )
        ]


class _ImmutableEvidence(TenantScopedModel):
    """Shared append-only model protection for operational evidence."""

    objects = ImmutableEvidenceQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableRecordError("Evidence is immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableRecordError("Evidence cannot be deleted")


class IntegrationPlatformConfigurationVersion(_ImmutableEvidence):
    """Immutable complete snapshot enabling deterministic rollback."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(
        IntegrationPlatformConfiguration,
        on_delete=models.PROTECT,
        related_name="versions",
    )
    environment = models.CharField(max_length=64)
    version = models.PositiveIntegerField()
    document = models.JSONField()
    created_by = models.UUIDField()
    correlation_id = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_configuration_versions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "environment", "version"),
                name="intplat_config_version_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "configuration", "-version"),
                name="intplat_config_version_idx",
            )
        ]


class IntegrationPlatformConfigurationAudit(_ImmutableEvidence):
    """Immutable who/what/when evidence for each configuration mutation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(
        IntegrationPlatformConfiguration,
        on_delete=models.PROTECT,
        related_name="audits",
    )
    environment = models.CharField(max_length=64)
    action = models.CharField(max_length=32)
    from_version = models.PositiveIntegerField(null=True)
    to_version = models.PositiveIntegerField()
    before = models.JSONField(null=True)
    after = models.JSONField()
    changed_by = models.UUIDField()
    correlation_id = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_configuration_audits"
        ordering = ("-created_at", "-to_version", "id")
        indexes = [
            models.Index(
                fields=("tenant_id", "configuration", "-created_at"),
                name="intplat_config_audit_idx",
            )
        ]


class WebhookDelivery(GuardedStateModel, TenantScopedModel, TimestampedModel):
    """Current delivery projection backed by immutable attempt evidence."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    webhook = models.ForeignKey(Webhook, on_delete=models.PROTECT, related_name="deliveries")
    event = models.CharField(max_length=255)
    payload = models.JSONField(default=dict, blank=True)
    payload_hash = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.QUEUED)
    transition_history = models.JSONField(default=list, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField()
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    job_id = models.UUIDField(db_index=True)
    correlation_id = models.CharField(max_length=64, db_index=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    IMMUTABLE_FIELDS = ("tenant_id", "webhook_id", "event", "payload", "payload_hash", "idempotency_key", "max_attempts", "correlation_id")

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_webhook_deliveries"
        ordering = ("-created_at", "id")
        constraints = [models.UniqueConstraint(fields=("tenant_id", "webhook", "idempotency_key"), name="intplat_delivery_idem_uniq")]
        indexes = [
            models.Index(fields=("tenant_id", "webhook", "status", "created_at"), name="intplat_deliv_tenant_hook_idx"),
            models.Index(fields=("tenant_id", "status", "next_attempt_at"), name="intplat_deliv_tenant_retry_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.webhook_id and self.tenant_id != self.webhook.tenant_id:
            raise ValidationError({"webhook": "Delivery and webhook must belong to the same tenant."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            previous = type(self)._default_manager.get(pk=self.pk)
            if any(getattr(previous, field) != getattr(self, field) for field in self.IMMUTABLE_FIELDS):
                raise ImmutableDeliveryError("Webhook delivery identity and payload evidence are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableDeliveryError("Webhook delivery evidence cannot be deleted")

    def __str__(self) -> str:
        return f"{self.event} [{self.status}] ({self.id})"


class WebhookDeliveryAttempt(_ImmutableEvidence):
    """Append-only outcome evidence for exactly one provider call attempt."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery = models.ForeignKey(WebhookDelivery, on_delete=models.PROTECT, related_name="attempts")
    attempt_number = models.PositiveSmallIntegerField()
    outcome = models.CharField(max_length=32)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    job_id = models.UUIDField(db_index=True)
    correlation_id = models.CharField(max_length=64, db_index=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_webhook_delivery_attempts"
        ordering = ("attempt_number", "occurred_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "delivery", "attempt_number"),
                name="intplat_delivery_attempt_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "delivery", "attempt_number"),
                name="intplat_delivery_attempt_idx",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.delivery_id and self.tenant_id != self.delivery.tenant_id:
            raise ValidationError({"delivery": "Attempt and delivery must belong to the same tenant."})


class DataMapping(MutableTenantModel):
    """Deterministic source-to-target field transformation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE, related_name="mappings")
    name = models.CharField(max_length=255)
    source_field = models.CharField(max_length=255)
    target_field = models.CharField(max_length=255)
    transform = models.JSONField(default=dict)
    position = models.PositiveIntegerField(default=int(_MAPPING_POLICY["default_position"]))
    is_required = models.BooleanField(default=bool(_MAPPING_POLICY["default_required"]))
    default_value = models.JSONField(null=True, blank=True)

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_data_mappings"
        ordering = ("position", "name", "id")
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "integration", "source_field", "target_field"), condition=Q(is_deleted=False), name="intplat_map_fields_live_uniq"),
            models.UniqueConstraint(fields=("tenant_id", "integration", "name"), condition=Q(is_deleted=False), name="intplat_map_name_live_uniq"),
        ]
        indexes = [models.Index(fields=("tenant_id", "integration", "position"), name="intplat_map_tenant_pos_idx")]

    def clean(self) -> None:
        super().clean()
        if self.integration_id and self.tenant_id != self.integration.tenant_id:
            raise ValidationError({"integration": "Mapping and integration must belong to the same tenant."})
        from .adapter_registry import transformation_registry

        transformation_registry.validate(self.transform)

    def __str__(self) -> str:
        return f"{self.name}: {self.source_field} -> {self.target_field}"


__all__ = [
    "Connector", "ConnectorAccessPolicy", "ConnectorCapability", "ConnectorType", "CredentialStatus", "CredentialType",
    "DataMapping", "DeliveryStatus", "Integration", "IntegrationCredential", "IntegrationStatus",
    "ImmutableDeliveryError", "ImmutableRecordError", "IntegrationPlatformConfiguration",
    "IntegrationPlatformConfigurationAudit", "IntegrationPlatformConfigurationVersion",
    "Webhook", "WebhookDelivery", "WebhookDeliveryAttempt", "WebhookDirection", "WebhookStatus", "generate_uuid",
]
