"""Explicit notification API serializers.

Input serializers intentionally contain no tenant, actor, correlation, state,
attempt, job, encryption, or provider-evidence fields.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from .models import (
    Notification,
    NotificationConfiguration,
    NotificationConfigurationAudit,
    NotificationConfigurationVersion,
    NotificationDelivery,
    NotificationDeliveryAttempt,
    NotificationEndpoint,
    NotificationPreference,
    NotificationTemplate,
    NotificationTemplateVersion,
)
from .services import CHANNELS, DIGEST_MODES, ENVIRONMENTS


class StrictSerializer(serializers.Serializer):
    """DRF already rejects unknown fields; this names that public contract."""


class TemplateListSerializer(serializers.ModelSerializer):
    active_version_number = serializers.IntegerField(source="active_version.version", read_only=True, allow_null=True)
    class Meta:
        model = NotificationTemplate
        fields = ("id", "code", "name", "category", "channel", "locale", "status", "active_version_number", "updated_at")


class TemplateVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplateVersion
        fields = ("id", "version", "subject_template", "body_template", "variables_schema", "content_type", "created_by", "correlation_id", "created_at")
        read_only_fields = fields


class TemplateDetailSerializer(TemplateListSerializer):
    active_version = TemplateVersionSerializer(read_only=True)
    latest_version = serializers.SerializerMethodField()
    transition_history = serializers.JSONField(read_only=True)
    class Meta(TemplateListSerializer.Meta):
        fields = TemplateListSerializer.Meta.fields + ("active_version", "latest_version", "transition_history", "created_by", "updated_by", "created_at")
    def get_latest_version(self, obj):
        latest = obj.versions.order_by("-version").first()
        return TemplateVersionSerializer(latest).data if latest else None


class TemplateCreateSerializer(StrictSerializer):
    code = serializers.RegexField(r"^[a-z][a-z0-9_.-]{0,99}$", max_length=100)
    name = serializers.CharField(max_length=255, trim_whitespace=True)
    category = serializers.RegexField(r"^[a-z][a-z0-9_.-]{0,99}$", max_length=100)
    channel = serializers.ChoiceField(choices=sorted(CHANNELS))
    locale = serializers.RegexField(r"^[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-[A-Z]{2}|-[0-9]{3})?$", default="en")
    subject_template = serializers.CharField(max_length=500, allow_blank=True, default="")
    body_template = serializers.CharField()
    variables_schema = serializers.DictField(default=dict)
    content_type = serializers.ChoiceField(choices=("text/plain", "text/html", "application/json"), default="text/plain")
    idempotency_key = serializers.CharField(max_length=255, required=False, write_only=True)


class TemplateVersionCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=255, required=False)
    category = serializers.RegexField(r"^[a-z][a-z0-9_.-]{0,99}$", max_length=100, required=False)
    subject_template = serializers.CharField(max_length=500, allow_blank=True, required=False)
    body_template = serializers.CharField(required=False)
    variables_schema = serializers.DictField(required=False)
    content_type = serializers.ChoiceField(choices=("text/plain", "text/html", "application/json"), required=False)


class TemplatePreviewSerializer(StrictSerializer):
    version_id = serializers.UUIDField(required=False, allow_null=True)
    context = serializers.DictField(default=dict)


class UnsavedTemplatePreviewSerializer(StrictSerializer):
    draft = TemplateVersionCreateSerializer()
    context = serializers.DictField(default=dict)


class TransitionSerializer(StrictSerializer):
    transition_key = serializers.CharField(max_length=255)


class TemplateTransitionSerializer(TransitionSerializer):
    version_id = serializers.UUIDField(required=False)
    version = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        if "version_id" not in attrs and "version" not in attrs:
            raise serializers.ValidationError({"version": "A version number or version_id is required."})
        return attrs


class TemplateRollbackSerializer(TransitionSerializer):
    version_id = serializers.UUIDField(required=False)
    version = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        if "version_id" not in attrs and "version" not in attrs:
            raise serializers.ValidationError({"version": "A version number or version_id is required."})
        return attrs


class DeliveryAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationDeliveryAttempt
        fields = ("id", "attempt_number", "adapter_key", "outcome", "provider_message_id", "error_code", "latency_ms", "started_at", "completed_at", "correlation_id")
        read_only_fields = fields


class DeliveryListSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationDelivery
        fields = ("id", "recipient_type", "recipient_display", "channel", "category", "priority", "status", "attempt_count", "max_attempts", "failure_code", "scheduled_at", "next_attempt_at", "sent_at", "delivered_at", "correlation_id", "created_at", "updated_at")
        read_only_fields = fields


class DeliveryDetailSerializer(DeliveryListSerializer):
    attempts = DeliveryAttemptSerializer(many=True, read_only=True)
    template_version_id = serializers.UUIDField(read_only=True)
    class Meta(DeliveryListSerializer.Meta):
        fields = DeliveryListSerializer.Meta.fields + ("template_version_id", "provider_message_id", "failure_message", "transition_history", "attempts")


class DispatchCreateSerializer(StrictSerializer):
    template_id = serializers.UUIDField()
    recipient_type = serializers.ChoiceField(choices=("user", "email", "phone", "push_endpoint", "webhook_endpoint"), required=False)
    recipient_user_id = serializers.CharField(required=False)
    recipient = serializers.JSONField(required=False, write_only=True)
    context = serializers.DictField(default=dict, write_only=True)
    priority = serializers.IntegerField(min_value=1, max_value=10, default=5)
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)
    environment = serializers.ChoiceField(choices=sorted(ENVIRONMENTS), default="development")
    idempotency_key = serializers.CharField(max_length=255, write_only=True)

    def validate(self, attrs):
        recipient = attrs.get("recipient")
        if isinstance(recipient, dict):
            attrs["recipient_type"] = recipient.get("type")
            attrs["recipient_user_id"] = recipient.get("user_id") or recipient.get("endpoint_id")
            attrs["recipient"] = recipient.get("address", "")
        if attrs.get("recipient_type") not in {"user", "email", "phone", "push_endpoint", "webhook_endpoint"}:
            raise serializers.ValidationError({"recipient": "A valid recipient type is required."})
        direct = attrs["recipient_type"] in {"email", "phone"}
        if direct and not attrs.get("recipient"):
            raise serializers.ValidationError({"recipient": "Required for direct delivery."})
        if attrs["recipient_type"] in {"user", "push_endpoint"} and not attrs.get("recipient_user_id"):
            raise serializers.ValidationError({"recipient_user_id": "Required for user delivery."})
        return attrs


class DispatchPreviewSerializer(StrictSerializer):
    template_id = serializers.UUIDField()
    recipient_type = serializers.ChoiceField(choices=("user", "email", "phone", "push_endpoint", "webhook_endpoint"), required=False)
    recipient_user_id = serializers.CharField(required=False)
    recipient = serializers.JSONField(required=False, write_only=True)
    context = serializers.DictField(default=dict, write_only=True)
    priority = serializers.IntegerField(min_value=1, max_value=10, default=5)
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)
    environment = serializers.ChoiceField(choices=sorted(ENVIRONMENTS), default="development")

    def validate(self, attrs):
        recipient = attrs.get("recipient")
        if isinstance(recipient, dict):
            attrs["recipient_type"] = recipient.get("type")
            attrs["recipient_user_id"] = recipient.get("user_id") or recipient.get("endpoint_id")
            attrs["recipient"] = recipient.get("address", "")
        if attrs.get("recipient_type") not in {"user", "email", "phone", "push_endpoint", "webhook_endpoint"}:
            raise serializers.ValidationError({"recipient": "A valid recipient type is required."})
        direct = attrs["recipient_type"] in {"email", "phone"}
        if direct and not attrs.get("recipient"):
            raise serializers.ValidationError({"recipient": "Required for direct delivery."})
        if attrs["recipient_type"] in {"user", "push_endpoint"} and not attrs.get("recipient_user_id"):
            raise serializers.ValidationError({"recipient_user_id": "Required for user delivery."})
        return attrs


class BulkDispatchSerializer(StrictSerializer):
    requests = DispatchPreviewSerializer(many=True, allow_empty=False, required=False)
    deliveries = DispatchPreviewSerializer(many=True, allow_empty=False, required=False, write_only=True)
    idempotency_key = serializers.CharField(max_length=255, write_only=True)

    def validate(self, attrs):
        items = attrs.get("requests") or attrs.get("deliveries")
        if not items: raise serializers.ValidationError({"deliveries": "At least one delivery is required."})
        attrs["requests"] = items; attrs.pop("deliveries", None)
        return attrs


class DeliveryRetrySerializer(StrictSerializer):
    idempotency_key = serializers.CharField(max_length=255)


class DeliveryCancelSerializer(TransitionSerializer):
    pass


class DeliveryConfirmationSerializer(StrictSerializer):
    provider_message_id = serializers.CharField(max_length=255)
    signature_verified = serializers.BooleanField()
    occurred_at = serializers.DateTimeField(required=False)
    idempotency_key = serializers.CharField(max_length=255)


class InboxListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "notification_type", "category", "title", "message", "status", "read_at", "action_url", "expires_at", "created_at", "updated_at")
        read_only_fields = fields


class InboxDetailSerializer(InboxListSerializer):
    class Meta(InboxListSerializer.Meta):
        fields = InboxListSerializer.Meta.fields + ("metadata", "transition_history")


class InboxTransitionSerializer(TransitionSerializer):
    pass


class MarkAllReadResultSerializer(StrictSerializer):
    affected_count = serializers.IntegerField(min_value=0, read_only=True)


class UnreadCountResultSerializer(StrictSerializer):
    count = serializers.IntegerField(min_value=0, read_only=True)


class PreferenceReadSerializer(serializers.ModelSerializer):
    mandatory = serializers.SerializerMethodField()
    source = serializers.SerializerMethodField()
    class Meta:
        model = NotificationPreference
        fields = ("id", "channel", "category", "enabled", "digest_mode", "quiet_hours_start", "quiet_hours_end", "timezone", "mandatory", "source", "created_at", "updated_at")
        read_only_fields = fields
    def get_mandatory(self, obj): return obj.category in {"security_alerts", "password_reset"}
    def get_source(self, obj): return "mandatory_policy" if self.get_mandatory(obj) else "override"


class PreferenceUpsertSerializer(StrictSerializer):
    channel = serializers.ChoiceField(choices=sorted(CHANNELS))
    category = serializers.RegexField(r"^[a-z][a-z0-9_.-]{0,99}$", max_length=100)
    enabled = serializers.BooleanField(default=True)
    digest_mode = serializers.ChoiceField(choices=sorted(DIGEST_MODES), default="immediate")
    quiet_hours_start = serializers.TimeField(required=False, allow_null=True)
    quiet_hours_end = serializers.TimeField(required=False, allow_null=True)
    timezone = serializers.CharField(max_length=64, default="UTC")

    def validate(self, attrs):
        if (attrs.get("quiet_hours_start") is None) != (attrs.get("quiet_hours_end") is None):
            raise serializers.ValidationError({"quiet_hours": "Start and end must both be set or null."})
        try: ZoneInfo(attrs.get("timezone", "UTC"))
        except ZoneInfoNotFoundError as exc: raise serializers.ValidationError({"timezone": "Must be a valid IANA timezone."}) from exc
        return attrs


class PreferenceBulkReplacementSerializer(StrictSerializer):
    preferences = PreferenceUpsertSerializer(many=True, allow_empty=True)


class EndpointListSerializer(serializers.ModelSerializer):
    health = serializers.SerializerMethodField()
    address_display = serializers.SerializerMethodField()
    class Meta:
        model = NotificationEndpoint
        fields = ("id", "user_id", "kind", "device_type", "address_display", "display_name", "is_active", "last_verified_at", "last_used_at", "health", "created_by", "created_at", "updated_at")
        read_only_fields = fields
    def get_health(self, obj):
        return "healthy" if obj.last_verified_at else ("revoked" if not obj.is_active else "unverified")
    def get_address_display(self, obj): return f"Protected {obj.kind} endpoint"


class EndpointDetailSerializer(EndpointListSerializer):
    secret_ref = serializers.CharField(read_only=True)
    class Meta(EndpointListSerializer.Meta):
        fields = EndpointListSerializer.Meta.fields + ("secret_ref",)


class EndpointRegisterSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=("push", "webhook"))
    device_type = serializers.ChoiceField(choices=("", "web", "android", "ios"), default="")
    address = serializers.CharField(max_length=4096, write_only=True)
    display_name = serializers.CharField(max_length=255)
    secret_ref = serializers.CharField(max_length=255, required=False, allow_blank=True, write_only=True)


class EndpointUpdateSerializer(StrictSerializer):
    display_name = serializers.CharField(max_length=255, required=False)
    is_active = serializers.BooleanField(required=False)
    secret_ref = serializers.CharField(max_length=255, required=False, allow_blank=True)


class EndpointVerifySerializer(StrictSerializer):
    pass


class EndpointRevokeSerializer(StrictSerializer):
    pass


class EndpointSecretRotationSerializer(StrictSerializer):
    secret_ref = serializers.RegexField(r"^(?:vault|aws-secrets|gcp-secrets|azure-keyvault)://[A-Za-z0-9_./-]+$", max_length=255, write_only=True)


class ConfigurationReadSerializer(serializers.ModelSerializer):
    checksum = serializers.SerializerMethodField()
    class Meta:
        model = NotificationConfiguration
        fields = ("id", "environment", "active_version", "document", "checksum", "created_by", "updated_by", "created_at", "updated_at")
        read_only_fields = fields
    def get_checksum(self, obj):
        version = obj.versions.order_by("-version").first()
        return version.checksum if version else ""


class ConfigurationWriteSerializer(StrictSerializer):
    document = serializers.DictField()
    reason = serializers.CharField(max_length=500, required=False)
    change_summary = serializers.CharField(max_length=500, required=False, write_only=True)
    expected_version = serializers.IntegerField(min_value=1, required=False, write_only=True)

    def validate(self, attrs):
        attrs["reason"] = attrs.get("reason") or attrs.get("change_summary")
        if not attrs["reason"]: raise serializers.ValidationError({"change_summary": "A change reason is required."})
        attrs.pop("change_summary", None)
        return attrs


class ConfigurationSimulationSerializer(StrictSerializer):
    document = serializers.DictField()
    scenario = serializers.DictField(default=dict)


class ConfigurationVersionSerializer(serializers.ModelSerializer):
    change_summary = serializers.CharField(source="change_reason", read_only=True)
    class Meta:
        model = NotificationConfigurationVersion
        fields = ("id", "version", "document", "checksum", "previous_version_id", "created_by", "correlation_id", "change_summary", "created_at")
        read_only_fields = fields


class ConfigurationAuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationConfigurationAudit
        fields = ("id", "action", "diff", "actor_id", "correlation_id", "created_at")
        read_only_fields = fields


class ConfigurationImportSerializer(StrictSerializer):
    document = serializers.DictField()
    dry_run = serializers.BooleanField(required=True)
    expected_version = serializers.IntegerField(min_value=1, required=False, write_only=True)
    change_summary = serializers.CharField(max_length=500, required=False, write_only=True)


class ConfigurationExportSerializer(StrictSerializer):
    schema_version = serializers.IntegerField(read_only=True)
    environment = serializers.CharField(read_only=True)
    configuration = serializers.DictField(read_only=True)
    exported_at = serializers.DateTimeField(read_only=True)


class ConfigurationRollbackSerializer(StrictSerializer):
    version = serializers.IntegerField(min_value=1, required=False)
    target_version = serializers.IntegerField(min_value=1, required=False, write_only=True)
    reason = serializers.CharField(max_length=500, required=False)
    change_summary = serializers.CharField(max_length=500, required=False, write_only=True)
    expected_version = serializers.IntegerField(min_value=1, required=False, write_only=True)

    def validate(self, attrs):
        attrs["version"] = attrs.get("version") or attrs.get("target_version")
        attrs["reason"] = attrs.get("reason") or attrs.get("change_summary")
        if not attrs["version"] or not attrs["reason"]: raise serializers.ValidationError("target_version and change_summary are required.")
        attrs.pop("target_version", None); attrs.pop("change_summary", None)
        return attrs


class HealthLivenessSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=("alive",), read_only=True)


class HealthReadinessSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=("ready", "not_ready"), read_only=True)
    checks = serializers.DictField(read_only=True)
    queue = serializers.DictField(read_only=True, required=False)
    adapters = serializers.DictField(read_only=True, required=False)


# Stable compatibility names for integrations that adopted the prototype.
NotificationSerializer = InboxDetailSerializer
NotificationPreferenceSerializer = PreferenceReadSerializer

TemplateList = TemplateListSerializer
TemplateDetail = TemplateDetailSerializer
TemplateCreate = TemplateCreateSerializer
TemplateVersionCreate = TemplateVersionCreateSerializer
TemplatePreview = TemplatePreviewSerializer
TemplateTransition = TemplateTransitionSerializer
TemplateRollback = TemplateRollbackSerializer
DeliveryList = DeliveryListSerializer
DeliveryDetail = DeliveryDetailSerializer
DispatchCreate = DispatchCreateSerializer
BulkDispatch = BulkDispatchSerializer
DeliveryRetry = DeliveryRetrySerializer
DeliveryCancel = DeliveryCancelSerializer
DeliveryConfirmation = DeliveryConfirmationSerializer
InboxList = InboxListSerializer
InboxDetail = InboxDetailSerializer
InboxTransition = InboxTransitionSerializer
PreferenceRead = PreferenceReadSerializer
PreferenceUpsert = PreferenceUpsertSerializer
PreferenceBulkReplacement = PreferenceBulkReplacementSerializer
EndpointList = EndpointListSerializer
EndpointDetail = EndpointDetailSerializer
EndpointRegister = EndpointRegisterSerializer
EndpointVerify = EndpointVerifySerializer
EndpointRevoke = EndpointRevokeSerializer
ConfigurationRead = ConfigurationReadSerializer
ConfigurationWrite = ConfigurationWriteSerializer
ConfigurationSimulation = ConfigurationSimulationSerializer
ConfigurationVersion = ConfigurationVersionSerializer
ConfigurationAudit = ConfigurationAuditSerializer
ConfigurationImport = ConfigurationImportSerializer
ConfigurationExport = ConfigurationExportSerializer
ConfigurationRollback = ConfigurationRollbackSerializer
