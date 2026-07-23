"""Operation-specific, non-spoofable serializers for API v2."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from rest_framework import serializers

from src.core.async_jobs.models import AsyncJob

from .models import (
    CampaignRecipient,
    ConsentRecord,
    DeliveryAttempt,
    DeliveryEvent,
    EmailCampaign,
    EmailMarketingConfiguration,
    EmailMarketingConfigurationVersion,
    EmailTemplate,
    SuppressionEntry,
)


def validate_bounded_json(value: object) -> object:
    """Reject secret-bearing JSON; tenant size/depth limits are service-enforced."""

    def inspect(candidate: object) -> None:
        if isinstance(candidate, Mapping):
            for key, nested in candidate.items():
                if not isinstance(key, str):
                    raise serializers.ValidationError("JSON keys must be strings.")
                if any(marker in key.lower() for marker in ("password", "secret", "credential", "token")):
                    raise serializers.ValidationError("JSON data contains a prohibited secret-like key.")
                inspect(nested)
        elif isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes, bytearray)):
            for nested in candidate:
                inspect(nested)

    inspect(value)
    return value


class BoundedJSONField(serializers.JSONField):
    def to_internal_value(self, data: object) -> object:
        return validate_bounded_json(super().to_internal_value(data))


class StrictSerializer(serializers.Serializer[dict[str, Any]]):
    """Reject undeclared input instead of silently discarding spoofed fields."""

    def to_internal_value(self, data: object) -> dict[str, Any]:
        if isinstance(data, Mapping):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({field: "This field is not allowed." for field in sorted(unknown)})
        return super().to_internal_value(data)


class CampaignListSerializer(serializers.ModelSerializer[EmailCampaign]):
    template_id = serializers.UUIDField(allow_null=True, read_only=True)

    class Meta:
        model = EmailCampaign
        fields = (
            "id",
            "campaign_code",
            "campaign_name",
            "campaign_type",
            "template_id",
            "subject",
            "status",
            "scheduled_at",
            "timezone",
            "resolved_recipient_count",
            "sent_count",
            "delivered_count",
            "opened_count",
            "clicked_count",
            "bounced_count",
            "failed_count",
            "created_at",
            "updated_at",
        )


class CampaignDetailSerializer(serializers.ModelSerializer[EmailCampaign]):
    template_id = serializers.UUIDField(allow_null=True, read_only=True)

    class Meta:
        model = EmailCampaign
        exclude = (
            "tenant_id",
            "legacy_template_id",
            "legacy_sent_at",
            "legacy_recipient_count",
            "template",
        )
        read_only_fields = tuple(field.name for field in EmailCampaign._meta.fields)


class CampaignCreateSerializer(StrictSerializer):
    campaign_code = serializers.CharField(max_length=50)
    campaign_name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    campaign_type = serializers.CharField(required=False, max_length=32)
    template_id = serializers.UUIDField(required=False, allow_null=True)
    subject = serializers.CharField(max_length=500)
    preview_text = serializers.CharField(required=False, allow_blank=True, max_length=255)
    from_name = serializers.CharField(max_length=255)
    from_email = serializers.EmailField(max_length=254)
    reply_to_email = serializers.EmailField(required=False, allow_null=True, max_length=254)
    audience_definition = BoundedJSONField(required=False, default=dict)
    timezone = serializers.CharField(required=False, max_length=63)


class CampaignUpdateSerializer(StrictSerializer):
    campaign_name = serializers.CharField(required=False, max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    campaign_type = serializers.CharField(required=False, max_length=32)
    template_id = serializers.UUIDField(required=False, allow_null=True)
    subject = serializers.CharField(required=False, max_length=500)
    preview_text = serializers.CharField(required=False, allow_blank=True, max_length=255)
    from_name = serializers.CharField(required=False, max_length=255)
    from_email = serializers.EmailField(required=False, max_length=254)
    reply_to_email = serializers.EmailField(required=False, allow_null=True, max_length=254)
    audience_definition = BoundedJSONField(required=False)
    timezone = serializers.CharField(required=False, max_length=63)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs:
            raise serializers.ValidationError("At least one editable field is required.")
        return attrs


class IdempotentActionSerializer(StrictSerializer):
    idempotency_key = serializers.CharField(max_length=255, trim_whitespace=True)


class CampaignScheduleSerializer(IdempotentActionSerializer):
    scheduled_at = serializers.DateTimeField()
    timezone = serializers.CharField(max_length=63)


class CampaignAudienceResolutionSerializer(IdempotentActionSerializer):
    pass


class CampaignSendSerializer(IdempotentActionSerializer):
    preflight_receipt = serializers.CharField(max_length=2048)


class CampaignTransitionSerializer(IdempotentActionSerializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class CampaignAnalyticsSerializer(serializers.Serializer[dict[str, Any]]):
    campaign_id = serializers.UUIDField()
    resolved = serializers.IntegerField(min_value=0)
    eligible = serializers.IntegerField(min_value=0)
    suppressed = serializers.IntegerField(min_value=0)
    sent = serializers.IntegerField(min_value=0)
    delivered = serializers.IntegerField(min_value=0)
    unique_opened = serializers.IntegerField(min_value=0)
    unique_clicked = serializers.IntegerField(min_value=0)
    bounced = serializers.IntegerField(min_value=0)
    failed = serializers.IntegerField(min_value=0)
    unsubscribed = serializers.IntegerField(min_value=0)
    complained = serializers.IntegerField(min_value=0)
    delivery_rate = serializers.FloatField(min_value=0, max_value=1)
    unique_open_rate = serializers.FloatField(min_value=0, max_value=1)
    unique_click_rate = serializers.FloatField(min_value=0, max_value=1)
    bounce_rate = serializers.FloatField(min_value=0, max_value=1)
    counter_drift = serializers.DictField(child=serializers.IntegerField())
    preflight = serializers.DictField()


class TemplateListSerializer(serializers.ModelSerializer[EmailTemplate]):
    class Meta:
        model = EmailTemplate
        fields = (
            "id",
            "template_code",
            "template_name",
            "category",
            "subject",
            "status",
            "version",
            "usage_count",
            "last_used_at",
            "created_at",
            "updated_at",
        )


class TemplateDetailSerializer(serializers.ModelSerializer[EmailTemplate]):
    class Meta:
        model = EmailTemplate
        exclude = ("tenant_id",)
        read_only_fields = tuple(field.name for field in EmailTemplate._meta.fields)


class TemplateCreateSerializer(StrictSerializer):
    template_code = serializers.CharField(max_length=50)
    template_name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(required=False, max_length=64)
    subject = serializers.CharField(max_length=500)
    preview_text = serializers.CharField(required=False, allow_blank=True, max_length=255)
    body_html = serializers.CharField(required=False, allow_blank=True)
    body_text = serializers.CharField(required=False, allow_blank=True)
    design_json = BoundedJSONField(required=False, default=dict)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs.get("body_html", "").strip() and not attrs.get("body_text", "").strip():
            raise serializers.ValidationError("At least one email body is required.")
        return attrs


class TemplateUpdateSerializer(TemplateCreateSerializer):
    template_code = None  # type: ignore[assignment]
    template_name = serializers.CharField(required=False, max_length=255)
    subject = serializers.CharField(required=False, max_length=500)
    design_json = BoundedJSONField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs:
            raise serializers.ValidationError("At least one editable field is required.")
        return attrs


class TemplateCloneSerializer(StrictSerializer):
    new_code = serializers.CharField(max_length=50)


class TemplatePreviewSerializer(StrictSerializer):
    sample_data = BoundedJSONField(required=False, default=dict)


class RenderedEmailSerializer(serializers.Serializer[dict[str, Any]]):
    subject = serializers.CharField()
    html = serializers.CharField(allow_blank=True)
    text = serializers.CharField(allow_blank=True)
    preview_text = serializers.CharField(allow_blank=True)
    warnings = serializers.ListField(child=serializers.CharField(), default=list)


class DeliveryEventListSerializer(serializers.ModelSerializer[DeliveryEvent]):
    recipient_id = serializers.UUIDField(read_only=True)
    attempt_id = serializers.UUIDField(allow_null=True, read_only=True)

    class Meta:
        model = DeliveryEvent
        fields = (
            "id",
            "recipient_id",
            "attempt_id",
            "gateway_key",
            "provider_event_id",
            "event_type",
            "occurred_at",
            "link_url_hash",
            "bounce_class",
            "metadata",
            "correlation_id",
            "created_at",
        )
        read_only_fields = fields


class DeliveryEventDetailSerializer(serializers.ModelSerializer[DeliveryEvent]):
    recipient_id = serializers.UUIDField(read_only=True)
    attempt_id = serializers.UUIDField(allow_null=True, read_only=True)

    class Meta:
        model = DeliveryEvent
        fields = DeliveryEventListSerializer.Meta.fields
        read_only_fields = fields


class DeliveryAttemptListSerializer(serializers.ModelSerializer[DeliveryAttempt]):
    recipient_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = DeliveryAttempt
        fields = (
            "id",
            "recipient_id",
            "attempt_number",
            "status",
            "error_code",
            "started_at",
            "accepted_at",
            "completed_at",
            "created_at",
        )
        read_only_fields = fields


class DeliveryAttemptDetailSerializer(serializers.ModelSerializer[DeliveryAttempt]):
    recipient_id = serializers.UUIDField(read_only=True)
    events = DeliveryEventDetailSerializer(many=True, read_only=True)

    class Meta:
        model = DeliveryAttempt
        fields = (
            "id",
            "recipient_id",
            "attempt_number",
            "status",
            "error_code",
            "started_at",
            "accepted_at",
            "completed_at",
            "created_at",
            "updated_at",
            "events",
        )
        read_only_fields = fields


class RecipientListSerializer(serializers.ModelSerializer[CampaignRecipient]):
    campaign_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = CampaignRecipient
        fields = (
            "id",
            "campaign_id",
            "recipient_key",
            "email",
            "display_name",
            "status",
            "suppression_reason",
            "created_at",
        )
        read_only_fields = fields


class RecipientDetailSerializer(serializers.ModelSerializer[CampaignRecipient]):
    campaign_id = serializers.UUIDField(read_only=True)
    consent_record_id = serializers.UUIDField(allow_null=True, read_only=True)
    delivery_attempts = DeliveryAttemptListSerializer(many=True, read_only=True)
    events = DeliveryEventListSerializer(many=True, read_only=True)

    class Meta:
        model = CampaignRecipient
        fields = (
            "id",
            "campaign_id",
            "recipient_key",
            "email",
            "display_name",
            "personalization_data",
            "consent_record_id",
            "status",
            "suppression_reason",
            "resolved_at",
            "queued_at",
            "accepted_at",
            "delivered_at",
            "failed_at",
            "last_error_code",
            "transition_history",
            "created_at",
            "updated_at",
            "delivery_attempts",
            "events",
        )
        read_only_fields = fields


class RecipientRetrySerializer(IdempotentActionSerializer):
    pass


class SuppressionListSerializer(serializers.ModelSerializer[SuppressionEntry]):
    class Meta:
        model = SuppressionEntry
        exclude = ("tenant_id", "notes")
        read_only_fields = tuple(field.name for field in SuppressionEntry._meta.fields)


class SuppressionDetailSerializer(serializers.ModelSerializer[SuppressionEntry]):
    evidence_event_id = serializers.UUIDField(allow_null=True, read_only=True)

    class Meta:
        model = SuppressionEntry
        exclude = ("tenant_id", "evidence_event")
        read_only_fields = tuple(field.name for field in SuppressionEntry._meta.fields)


class SuppressionCreateSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)
    scope = serializers.CharField(required=False, max_length=16)
    reason = serializers.CharField(max_length=16)
    source = serializers.CharField(max_length=16)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class SuppressionDeactivateSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=500, trim_whitespace=True)


class ConsentListSerializer(serializers.ModelSerializer[ConsentRecord]):
    class Meta:
        model = ConsentRecord
        exclude = ("tenant_id", "evidence", "ip_hash", "user_agent_hash")
        read_only_fields = tuple(field.name for field in ConsentRecord._meta.fields)


class ConsentDetailSerializer(serializers.ModelSerializer[ConsentRecord]):
    supersedes_id = serializers.UUIDField(allow_null=True, read_only=True)

    class Meta:
        model = ConsentRecord
        fields = (
            "id",
            "email",
            "purpose",
            "status",
            "lawful_basis",
            "source",
            "notice_version",
            "captured_at",
            "actor_id",
            "supersedes_id",
            "created_at",
        )
        read_only_fields = fields


class ConsentCreateSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)
    purpose = serializers.CharField(required=False, max_length=64)
    status = serializers.ChoiceField(choices=("granted", "revoked"))
    lawful_basis = serializers.CharField(max_length=32)
    source = serializers.CharField(max_length=32)
    notice_version = serializers.CharField(max_length=64)

    def to_internal_value(self, data: object) -> dict[str, Any]:
        if isinstance(data, Mapping):
            data = {
                key: value
                for key, value in data.items()
                if key
                not in {
                    "captured_at",
                    "ip_hash",
                    "user_agent_hash",
                    "evidence",
                }
            }
        return super().to_internal_value(data)


class ConsentRevokeSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)
    purpose = serializers.CharField(required=False, max_length=64)
    source = serializers.CharField(max_length=32)


class AsyncJobSummarySerializer(serializers.ModelSerializer[AsyncJob]):
    job_type = serializers.CharField(source="command", read_only=True)

    class Meta:
        model = AsyncJob
        fields = (
            "id",
            "job_type",
            "status",
            "idempotency_key",
            "created_at",
            "correlation_id",
        )
        read_only_fields = fields


class ModuleHealthSerializer(serializers.Serializer[dict[str, Any]]):
    module = serializers.CharField()
    status = serializers.ChoiceField(choices=("ready", "degraded", "unhealthy"))
    checks = serializers.DictField()
    checked_at = serializers.DateTimeField()


class ConfigurationSerializer(serializers.ModelSerializer[EmailMarketingConfiguration]):
    class Meta:
        model = EmailMarketingConfiguration
        fields = (
            "id",
            "environment",
            "version",
            "document",
            "updated_at",
            "updated_by",
        )
        read_only_fields = fields


class ConfigurationVersionSerializer(serializers.ModelSerializer[EmailMarketingConfigurationVersion]):
    rollback_source_version = serializers.IntegerField(allow_null=True, read_only=True)

    class Meta:
        model = EmailMarketingConfigurationVersion
        fields = (
            "id",
            "version",
            "previous_version",
            "change_type",
            "actor_id",
            "correlation_id",
            "previous_document",
            "document",
            "created_at",
            "rollback_source_version",
        )
        read_only_fields = fields


class ConfigurationUpdateSerializer(StrictSerializer):
    document = serializers.JSONField()
    expected_version = serializers.IntegerField(min_value=1)


class ConfigurationPreviewSerializer(StrictSerializer):
    document = serializers.JSONField()


class ConfigurationRollbackSerializer(StrictSerializer):
    target_version = serializers.IntegerField(min_value=1)
    expected_version = serializers.IntegerField(min_value=1)


class PublicUnsubscribeResponseSerializer(StrictSerializer):
    suppression_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=("unsubscribed",))


# Compatibility imports intentionally remain read-only; v2 mutations use the
# operation serializers above.
EmailCampaignSerializer = CampaignDetailSerializer
EmailTemplateSerializer = TemplateDetailSerializer


__all__ = [name for name in globals() if name.endswith("Serializer")]
