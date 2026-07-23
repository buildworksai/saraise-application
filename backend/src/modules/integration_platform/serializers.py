"""Strict, secret-safe serializers for Integration Platform API v2."""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from jsonschema import Draft202012Validator
from rest_framework import serializers

from src.core.async_jobs.models import AsyncJob

from .models import (
    Connector,
    DataMapping,
    Integration,
    IntegrationCredential,
    IntegrationPlatformConfigurationAudit,
    IntegrationPlatformConfigurationVersion,
    Webhook,
    WebhookDelivery,
    WebhookDeliveryAttempt,
)

PROTECTED_INPUT_FIELDS = frozenset(
    {
        "id",
        "tenant_id",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "is_deleted",
        "deleted_at",
        "deleted_by",
        "encrypted_value",
        "encrypted_signing_secret",
        "transition_history",
        "last_tested_at",
        "last_test_job_id",
        "last_sync_job_id",
        "last_error_code",
        "last_error_message",
        "rotated_at",
        "revoked_at",
        "revoked_by",
        "last_received_at",
        "last_delivered_at",
        "public_id",
        "status",
    }
)
SECRET_KEY_FRAGMENTS = frozenset(
    {
        "authorization",
        "credential",
        "password",
        "private_key",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "client_secret",
        "signing_secret",
        "encrypted_value",
    }
)
FORBIDDEN_EXECUTION_KEYS = frozenset(
    {
        "sql",
        "query",
        "script",
        "python",
        "javascript",
        "template",
        "model",
        "model_name",
        "import",
        "module",
        "callable",
        "handler_class",
    }
)


def _normalise_key(value: object) -> str:
    return str(value).strip().lower().replace("-", "_")


def _walk_json(value: object, *, path: str = "config") -> None:
    """Reject secret material and executable configuration recursively."""

    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = _normalise_key(raw_key)
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_EXECUTION_KEYS:
                raise serializers.ValidationError(f"{child_path} is not an allowed declarative setting.")
            if any(fragment in key for fragment in SECRET_KEY_FRAGMENTS):
                raise serializers.ValidationError(f"{child_path} must be supplied through credential storage.")
            _walk_json(child, path=child_path)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _walk_json(child, path=f"{path}[{index}]")


def _validate_transform(value: object) -> object:
    """Validate the bounded deterministic transformation DSL."""

    _walk_json(value, path="transform")
    from .adapter_registry import transformation_registry

    try:
        transformation_registry.validate(value)
    except DjangoValidationError as exc:
        detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or str(exc)
        raise serializers.ValidationError(detail) from exc
    return value


def _validate_safe_destination(value: str) -> str:
    """Reject URL forms that are unsafe before resilience-layer DNS checks."""

    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise serializers.ValidationError("Destination must be an absolute HTTP(S) URL.")
    if parsed.username is not None or parsed.password is not None:
        raise serializers.ValidationError("URL user information is forbidden.")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        raise serializers.ValidationError("Local or internal destinations are forbidden.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return value
    if not address.is_global:
        raise serializers.ValidationError("Private, loopback, link-local, and reserved destinations are forbidden.")
    return value


def _request_tenant_id(serializer: serializers.BaseSerializer[Any]) -> object | None:
    request = serializer.context.get("request")
    if request is None:
        return serializer.context.get("tenant_id")
    return getattr(request, "tenant_id", None)


class StrictInputMixin:
    """Reject unknown and server-owned fields instead of silently ignoring them."""

    def to_internal_value(self, data: object) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            return super().to_internal_value(data)  # type: ignore[misc,no-any-return]
        supplied = {_normalise_key(key) for key in data}
        protected = sorted(supplied.intersection(PROTECTED_INPUT_FIELDS))
        if protected:
            raise serializers.ValidationError(
                {field: "This server-owned field cannot be supplied." for field in protected}
            )
        accepted = set(self.fields)
        unknown = sorted(supplied.difference(accepted))
        if unknown:
            raise serializers.ValidationError({field: "Unknown field." for field in unknown})
        return super().to_internal_value(data)  # type: ignore[misc,no-any-return]


class ConnectorListSerializer(serializers.Serializer):
    """Serialize a tenant-evaluated connector service descriptor."""

    id = serializers.UUIDField(read_only=True, source="connector.id")
    key = serializers.SlugField(read_only=True, source="connector.key")
    name = serializers.CharField(read_only=True, source="connector.name")
    connector_type = serializers.CharField(read_only=True, source="connector.connector_type")
    adapter_key = serializers.CharField(read_only=True, source="connector.adapter_key")
    version = serializers.CharField(read_only=True, source="connector.version")
    capabilities = serializers.ListField(child=serializers.CharField(), read_only=True, source="connector.capabilities")
    module_id = serializers.CharField(read_only=True, source="connector.module_id")
    access_policy = serializers.CharField(read_only=True, source="connector.access_policy")
    required_entitlement = serializers.CharField(
        read_only=True, allow_blank=True, source="connector.required_entitlement"
    )
    is_active = serializers.BooleanField(read_only=True, source="connector.is_active")
    is_entitled = serializers.BooleanField(read_only=True, source="entitled")
    entitlement_reason = serializers.CharField(
        read_only=True, required=False, allow_blank=True, source="availability_reason"
    )
    adapter_available = serializers.BooleanField(read_only=True, source="adapter_registered")
    created_at = serializers.DateTimeField(read_only=True, source="connector.created_at")
    updated_at = serializers.DateTimeField(read_only=True, source="connector.updated_at")


class ConnectorDetailSerializer(ConnectorListSerializer):
    schema = serializers.JSONField(read_only=True, source="connector.schema")
    credential_schema = serializers.JSONField(read_only=True, source="connector.credential_schema")


class ConnectorSchemaSerializer(serializers.Serializer):
    connector_id = serializers.UUIDField(read_only=True)
    config_schema = serializers.JSONField(read_only=True)
    credential_schema = serializers.JSONField(read_only=True)


class IntegrationListSerializer(serializers.ModelSerializer):
    connector_id = serializers.UUIDField(read_only=True)
    connector_name = serializers.CharField(source="connector.name", read_only=True)
    credentials_count = serializers.SerializerMethodField()
    mappings_count = serializers.SerializerMethodField()

    class Meta:
        model = Integration
        fields = (
            "id",
            "connector_id",
            "connector_name",
            "name",
            "description",
            "integration_type",
            "status",
            "last_tested_at",
            "last_test_job_id",
            "last_sync_job_id",
            "last_error_code",
            "last_error_message",
            "credentials_count",
            "mappings_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    @staticmethod
    def get_credentials_count(instance: Integration) -> int:
        annotated = getattr(instance, "credentials_count", None)
        return int(annotated) if annotated is not None else instance.credentials.count()

    @staticmethod
    def get_mappings_count(instance: Integration) -> int:
        annotated = getattr(instance, "mappings_count", None)
        return int(annotated) if annotated is not None else instance.mappings.filter(is_deleted=False).count()


class IntegrationDetailSerializer(IntegrationListSerializer):
    latest_test_evidence = serializers.SerializerMethodField()
    latest_sync_evidence = serializers.SerializerMethodField()

    class Meta(IntegrationListSerializer.Meta):
        fields = IntegrationListSerializer.Meta.fields + (
            "config",
            "transition_history",
            "latest_test_evidence",
            "latest_sync_evidence",
        )
        read_only_fields = fields

    @staticmethod
    def _job_evidence(instance: Integration, job_id: object | None) -> dict[str, object] | None:
        if job_id is None:
            return None
        job = (
            AsyncJob.objects.filter(id=job_id, tenant_id=instance.tenant_id)
            .only("id", "status", "result", "error_message", "correlation_id", "completed_at", "created_at")
            .first()
        )
        if job is None:
            return None
        if job.status not in {"succeeded", "failed"}:
            return None
        result = job.result if isinstance(job.result, Mapping) else {}
        return {
            "outcome": "succeeded" if job.status == "succeeded" else "failed",
            "occurred_at": (job.completed_at or job.created_at).isoformat(),
            "correlation_id": job.correlation_id,
            "job_id": str(job.id),
            "duration_ms": result.get("duration_ms"),
            "error_code": result.get("error_code", ""),
            "error_message": job.error_message,
            "records_read": result.get("records_read"),
            "records_written": result.get("records_written"),
            "records_failed": result.get("records_failed"),
            "zero_source_proven": result.get("zero_source_proven"),
        }

    def get_latest_test_evidence(self, instance: Integration) -> dict[str, object] | None:
        return self._job_evidence(instance, instance.last_test_job_id)

    def get_latest_sync_evidence(self, instance: Integration) -> dict[str, object] | None:
        return self._job_evidence(instance, instance.last_sync_job_id)


class IntegrationCreateSerializer(StrictInputMixin, serializers.ModelSerializer):
    connector_id = serializers.PrimaryKeyRelatedField(
        source="connector", queryset=Connector.objects.filter(is_active=True)
    )

    class Meta:
        model = Integration
        fields = ("connector_id", "name", "description", "integration_type", "config")

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name cannot be blank.")
        return value

    def validate_config(self, value: object) -> object:
        _walk_json(value)
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        connector = attrs["connector"]
        if attrs["integration_type"] != connector.connector_type:
            raise serializers.ValidationError({"integration_type": "Must match the selected connector type."})
        config = attrs.get("config", {})
        schema = connector.schema or {}
        errors = sorted(Draft202012Validator(schema).iter_errors(config), key=lambda error: list(error.path))
        if errors:
            raise serializers.ValidationError({"config": [error.message for error in errors]})
        declared = set(schema.get("properties", {})) if isinstance(schema, Mapping) else set()
        if isinstance(config, Mapping):
            unknown = sorted(set(config).difference(declared))
            if unknown:
                raise serializers.ValidationError({"config": {key: "Unknown connector field." for key in unknown}})
        return attrs


class IntegrationUpdateSerializer(StrictInputMixin, serializers.ModelSerializer):
    class Meta:
        model = Integration
        fields = ("name", "description", "config")
        extra_kwargs = {field: {"required": False} for field in fields}

    validate_name = IntegrationCreateSerializer.validate_name
    validate_config = IntegrationCreateSerializer.validate_config

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if "config" not in attrs:
            return attrs
        instance = self.instance
        if instance is None:
            raise serializers.ValidationError("An existing integration is required.")
        schema = instance.connector.schema or {}
        errors = sorted(Draft202012Validator(schema).iter_errors(attrs["config"]), key=lambda error: list(error.path))
        if errors:
            raise serializers.ValidationError({"config": [error.message for error in errors]})
        declared = set(schema.get("properties", {})) if isinstance(schema, Mapping) else set()
        unknown = sorted(set(attrs["config"]).difference(declared))
        if unknown:
            raise serializers.ValidationError({"config": {key: "Unknown connector field." for key in unknown}})
        return attrs


class IntegrationTestRequestSerializer(StrictInputMixin, serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=255, trim_whitespace=True)


class IntegrationSyncRequestSerializer(StrictInputMixin, serializers.Serializer):
    direction = serializers.ChoiceField(choices=("pull", "push"))
    mapping_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=True, default=list)
    idempotency_key = serializers.CharField(max_length=255, trim_whitespace=True)


class AsyncJobReceiptSerializer(serializers.Serializer):
    job_id = serializers.UUIDField(read_only=True, required=False)
    status = serializers.CharField(read_only=True)
    correlation_id = serializers.CharField(read_only=True)
    accepted_at = serializers.DateTimeField(read_only=True, required=False)
    poll_after_ms = serializers.IntegerField(read_only=True, min_value=0)


class AsyncJobStateSerializer(AsyncJobReceiptSerializer):
    operation = serializers.ChoiceField(
        choices=("integration_test", "integration_sync", "webhook_delivery"), read_only=True
    )
    started_at = serializers.DateTimeField(read_only=True, allow_null=True, required=False)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True, required=False)
    progress_percent = serializers.IntegerField(read_only=True, min_value=0, max_value=100)
    evidence = serializers.JSONField(read_only=True, allow_null=True)


class CredentialMetadataSerializer(serializers.ModelSerializer):
    integration_id = serializers.UUIDField(read_only=True)
    integration_name = serializers.CharField(source="integration.name", read_only=True)

    class Meta:
        model = IntegrationCredential
        fields = (
            "id",
            "integration_id",
            "integration_name",
            "credential_type",
            "display_hint",
            "version",
            "status",
            "expires_at",
            "rotated_at",
            "revoked_at",
            "created_at",
        )
        read_only_fields = fields


class CredentialCreateSerializer(StrictInputMixin, serializers.Serializer):
    credential_type = serializers.ChoiceField(choices=("api_key", "oauth_token", "username_password", "certificate"))
    plaintext = serializers.CharField(write_only=True, trim_whitespace=False, allow_blank=False, max_length=65536)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class CredentialRotateSerializer(StrictInputMixin, serializers.Serializer):
    plaintext = serializers.CharField(write_only=True, trim_whitespace=False, allow_blank=False, max_length=65536)
    idempotency_key = serializers.CharField(max_length=255, trim_whitespace=True)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class TransitionRequestSerializer(StrictInputMixin, serializers.Serializer):
    transition_key = serializers.CharField(max_length=255, trim_whitespace=True)


class WebhookListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Webhook
        fields = (
            "id",
            "name",
            "direction",
            "url",
            "public_id",
            "events",
            "status",
            "timeout_seconds",
            "max_attempts",
            "last_received_at",
            "last_delivered_at",
            "last_error_code",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class WebhookDetailSerializer(WebhookListSerializer):
    delivery_summary = serializers.SerializerMethodField()

    class Meta(WebhookListSerializer.Meta):
        fields = WebhookListSerializer.Meta.fields + (
            "config",
            "transition_history",
            "delivery_summary",
        )
        read_only_fields = fields

    @staticmethod
    def get_delivery_summary(instance: Webhook) -> dict[str, object]:
        counts = instance.deliveries.aggregate(
            queued=Count("id", filter=Q(status="queued")),
            retrying=Count("id", filter=Q(status="retrying")),
            delivered=Count("id", filter=Q(status="delivered")),
            dead_letter=Count("id", filter=Q(status="dead_letter")),
        )
        terminal = counts["delivered"] + counts["dead_letter"]
        counts["success_rate"] = None if terminal == 0 else round(100 * counts["delivered"] / terminal, 2)
        return counts


class WebhookCreateSerializer(StrictInputMixin, serializers.ModelSerializer):
    class Meta:
        model = Webhook
        fields = ("name", "direction", "url", "events", "config", "timeout_seconds", "max_attempts")
        extra_kwargs = {"url": {"required": False, "allow_blank": True}}

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name cannot be blank.")
        return value

    def validate_url(self, value: str) -> str:
        return _validate_safe_destination(value) if value else value

    def validate_events(self, value: list[str]) -> list[str]:
        events = [event.strip() for event in value if isinstance(event, str) and event.strip()]
        if not events:
            raise serializers.ValidationError("At least one registered event is required.")
        if len(events) != len(value) or len(events) != len(set(events)):
            raise serializers.ValidationError("Events must be non-empty and unique.")
        return events

    def validate_config(self, value: object) -> object:
        _walk_json(value, path="config")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        direction = attrs.get("direction")
        url = attrs.get("url", "")
        if direction == "outbound" and not url:
            raise serializers.ValidationError({"url": "Outbound webhooks require a destination URL."})
        if direction == "inbound" and url:
            raise serializers.ValidationError({"url": "Inbound webhooks cannot define an outbound URL."})
        return attrs


class WebhookUpdateSerializer(WebhookCreateSerializer):
    class Meta(WebhookCreateSerializer.Meta):
        fields = ("name", "url", "events", "config", "timeout_seconds", "max_attempts")
        extra_kwargs = {field: {"required": False} for field in fields}

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.instance
        if instance is None:
            raise serializers.ValidationError("An existing webhook is required.")
        url = attrs.get("url", instance.url)
        if instance.direction == "outbound" and not url:
            raise serializers.ValidationError({"url": "Outbound webhooks require a destination URL."})
        if instance.direction == "inbound" and url:
            raise serializers.ValidationError({"url": "Inbound webhooks cannot define an outbound URL."})
        return attrs


class WebhookSecretOnceSerializer(serializers.Serializer):
    webhook = WebhookDetailSerializer(read_only=True)
    signing_secret = serializers.CharField(read_only=True)
    shown_once = serializers.BooleanField(read_only=True)


class InboundWebhookSerializer(StrictInputMixin, serializers.Serializer):
    timestamp = serializers.IntegerField(min_value=1)
    nonce = serializers.CharField(min_length=16, max_length=128)
    signature = serializers.RegexField(regex=r"^sha256=[0-9a-fA-F]{64}$", max_length=71)


class WebhookDeliveryListSerializer(serializers.ModelSerializer):
    webhook_id = serializers.UUIDField(read_only=True)
    webhook_name = serializers.CharField(source="webhook.name", read_only=True)

    class Meta:
        model = WebhookDelivery
        fields = (
            "id",
            "webhook_id",
            "webhook_name",
            "event",
            "status",
            "attempt_count",
            "max_attempts",
            "next_attempt_at",
            "response_code",
            "error_code",
            "duration_ms",
            "job_id",
            "correlation_id",
            "delivered_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class WebhookDeliveryAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDeliveryAttempt
        fields = (
            "id",
            "attempt_number",
            "outcome",
            "response_code",
            "error_code",
            "duration_ms",
            "job_id",
            "correlation_id",
            "occurred_at",
        )
        read_only_fields = fields


class WebhookDeliveryDetailSerializer(WebhookDeliveryListSerializer):
    attempts = WebhookDeliveryAttemptSerializer(many=True, read_only=True)

    class Meta(WebhookDeliveryListSerializer.Meta):
        fields = WebhookDeliveryListSerializer.Meta.fields + (
            "payload",
            "payload_hash",
            "idempotency_key",
            "transition_history",
            "error_message",
            "attempts",
        )
        read_only_fields = fields


class DeliveryRedriveSerializer(TransitionRequestSerializer):
    pass


class ConfigurationDocumentSerializer(StrictInputMixin, serializers.Serializer):
    environment = serializers.CharField(max_length=64, default="default")
    document = serializers.JSONField()


class ConfigurationRollbackSerializer(StrictInputMixin, serializers.Serializer):
    environment = serializers.CharField(max_length=64, default="default")
    version = serializers.IntegerField(min_value=1)


class ConfigurationSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True, allow_null=True)
    tenant_id = serializers.UUIDField(read_only=True)
    environment = serializers.CharField(read_only=True)
    version = serializers.IntegerField(read_only=True)
    document = serializers.JSONField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True, allow_null=True)
    updated_by = serializers.UUIDField(read_only=True, allow_null=True)


class ConfigurationPreviewSerializer(serializers.Serializer):
    valid = serializers.BooleanField(read_only=True)
    environment = serializers.CharField(read_only=True)
    from_version = serializers.IntegerField(read_only=True)
    to_version = serializers.IntegerField(read_only=True)
    changed_sections = serializers.ListField(child=serializers.CharField(), read_only=True)
    before = serializers.JSONField(read_only=True)
    after = serializers.JSONField(read_only=True)


class ConfigurationVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationPlatformConfigurationVersion
        fields = (
            "id", "environment", "version", "document", "created_by",
            "correlation_id", "created_at",
        )
        read_only_fields = fields


class ConfigurationAuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationPlatformConfigurationAudit
        fields = (
            "id", "environment", "action", "from_version", "to_version",
            "before", "after", "changed_by", "correlation_id", "created_at",
        )
        read_only_fields = fields


class DataMappingListSerializer(serializers.ModelSerializer):
    integration_id = serializers.UUIDField(read_only=True)
    integration_name = serializers.CharField(source="integration.name", read_only=True)

    class Meta:
        model = DataMapping
        fields = (
            "id",
            "integration_id",
            "integration_name",
            "name",
            "source_field",
            "target_field",
            "transform",
            "position",
            "is_required",
            "default_value",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DataMappingDetailSerializer(DataMappingListSerializer):
    class Meta(DataMappingListSerializer.Meta):
        fields = DataMappingListSerializer.Meta.fields
        read_only_fields = fields


class _MappingWriteSerializer(StrictInputMixin, serializers.ModelSerializer):
    class Meta:
        model = DataMapping
        fields = ("name", "source_field", "target_field", "transform", "position", "is_required", "default_value")

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name cannot be blank.")
        return value

    def validate_transform(self, value: object) -> object:
        return _validate_transform(value)


class DataMappingCreateSerializer(_MappingWriteSerializer):
    integration_id = serializers.UUIDField(write_only=True)

    class Meta(_MappingWriteSerializer.Meta):
        fields = ("integration_id",) + _MappingWriteSerializer.Meta.fields

    def validate_integration_id(self, value: object) -> object:
        tenant_id = _request_tenant_id(self)
        if (
            tenant_id is None
            or not Integration.objects.filter(id=value, tenant_id=tenant_id, is_deleted=False).exists()
        ):
            raise serializers.ValidationError("Integration was not found.")
        return value


class DataMappingUpdateSerializer(_MappingWriteSerializer):
    class Meta(_MappingWriteSerializer.Meta):
        extra_kwargs = {field: {"required": False} for field in _MappingWriteSerializer.Meta.fields}


class MappingItemSerializer(StrictInputMixin, serializers.Serializer):
    integration_id = serializers.UUIDField(required=False)
    name = serializers.CharField(max_length=255)
    source_field = serializers.CharField(max_length=255)
    target_field = serializers.CharField(max_length=255)
    transform = serializers.JSONField(default=dict)
    position = serializers.IntegerField(min_value=0, default=0)
    is_required = serializers.BooleanField(default=False)
    default_value = serializers.JSONField(required=False, allow_null=True)

    def validate_transform(self, value: object) -> object:
        return _validate_transform(value)


class MappingValidateSerializer(StrictInputMixin, serializers.Serializer):
    integration_id = serializers.UUIDField()
    mappings = MappingItemSerializer(many=True, allow_empty=False)
    source_schema = serializers.JSONField()
    target_schema = serializers.JSONField()

    def validate_integration_id(self, value: object) -> object:
        tenant_id = _request_tenant_id(self)
        if (
            tenant_id is None
            or not Integration.objects.filter(id=value, tenant_id=tenant_id, is_deleted=False).exists()
        ):
            raise serializers.ValidationError("Integration was not found.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        integration_id = attrs["integration_id"]
        mismatched = [
            index
            for index, mapping in enumerate(attrs["mappings"])
            if mapping.get("integration_id", integration_id) != integration_id
        ]
        if mismatched:
            raise serializers.ValidationError(
                {"mappings": "Nested mapping integration_id values must match the requested integration."}
            )
        for mapping in attrs["mappings"]:
            mapping.pop("integration_id", None)
        return attrs


class MappingPreviewSerializer(StrictInputMixin, serializers.Serializer):
    integration_id = serializers.UUIDField()
    mapping_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    sample = serializers.DictField(allow_empty=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        tenant_id = _request_tenant_id(self)
        integration_id = attrs["integration_id"]
        if (
            tenant_id is None
            or not Integration.objects.filter(id=integration_id, tenant_id=tenant_id, is_deleted=False).exists()
        ):
            raise serializers.ValidationError({"integration_id": "Integration was not found."})
        found = set(
            DataMapping.objects.filter(
                tenant_id=tenant_id,
                integration_id=integration_id,
                id__in=attrs["mapping_ids"],
                is_deleted=False,
            ).values_list("id", flat=True)
        )
        requested = set(attrs["mapping_ids"])
        if found != requested:
            raise serializers.ValidationError({"mapping_ids": "One or more mappings were not found."})
        return attrs


__all__ = [name for name in tuple(globals()) if name.endswith("Serializer")]
