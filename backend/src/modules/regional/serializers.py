"""Strict transport serializers for Regional APIs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rest_framework import serializers

from .models import RegionalConfiguration, RegionalConfigurationVersion, RegionalResource


class StrictSerializer(serializers.Serializer):
    """Reject unknown input instead of silently discarding it."""

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if isinstance(data, Mapping):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {key: "Unknown field." for key in sorted(unknown)}
                )
        return super().to_internal_value(data)


class RegionalResourceConfigSerializer(StrictSerializer):
    """Typed per-resource regional metadata."""

    country_code = serializers.CharField(required=False, min_length=2, max_length=2)
    jurisdiction_type = serializers.CharField(required=False, max_length=64)
    compliance_tags = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
    )


class RegionalResourceWriteSerializer(StrictSerializer):
    """Create/update payload; lifecycle and ownership are never client-writable."""

    name = serializers.CharField(max_length=512)
    description = serializers.CharField(required=False, allow_blank=True, max_length=10000)
    config = RegionalResourceConfigSerializer(required=False)


class RegionalResourceResponseSerializer(serializers.ModelSerializer):
    """Public resource representation without tenant or actor internals."""

    config = RegionalResourceConfigSerializer(read_only=True)

    class Meta:
        model = RegionalResource
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "config",
            "created_at",
            "updated_at",
            "deleted_at",
        ]
        read_only_fields = fields


class ResourcePolicySerializer(StrictSerializer):
    name_min_length = serializers.IntegerField()
    name_max_length = serializers.IntegerField()
    name_default = serializers.CharField()
    description_default = serializers.CharField(allow_blank=True)
    description_max_length = serializers.IntegerField()
    default_active = serializers.BooleanField()
    default_config = RegionalResourceConfigSerializer()
    allowed_config_keys = serializers.ListField(child=serializers.CharField())
    allowed_jurisdiction_types = serializers.ListField(child=serializers.CharField())
    max_compliance_tags = serializers.IntegerField()
    max_config_bytes = serializers.IntegerField()
    search_fields = serializers.ListField(child=serializers.CharField())


class WorkflowPolicySerializer(StrictSerializer):
    activation_state = serializers.BooleanField()
    deactivation_state = serializers.BooleanField()
    require_delete_confirmation = serializers.BooleanField()


class ApiPolicySerializer(StrictSerializer):
    default_page_size = serializers.IntegerField()
    max_page_size = serializers.IntegerField()
    allowed_filters = serializers.ListField(child=serializers.CharField())
    allowed_ordering = serializers.ListField(child=serializers.CharField())


class HealthPolicySerializer(StrictSerializer):
    cache_probe_ttl_seconds = serializers.IntegerField()


class RolloutPolicySerializer(StrictSerializer):
    enabled = serializers.BooleanField()
    roles = serializers.ListField(child=serializers.CharField())
    cohorts = serializers.ListField(child=serializers.CharField())


class RegionalConfigurationDocumentSerializer(StrictSerializer):
    """Typed configuration-as-code document."""

    resource = ResourcePolicySerializer()
    workflow = WorkflowPolicySerializer()
    api = ApiPolicySerializer()
    health = HealthPolicySerializer()
    rollout = RolloutPolicySerializer()


class RegionalConfigurationWriteSerializer(StrictSerializer):
    environment = serializers.CharField(required=False, max_length=32)
    document = RegionalConfigurationDocumentSerializer()


class RegionalConfigurationRollbackSerializer(StrictSerializer):
    environment = serializers.CharField(required=False, max_length=32)
    version = serializers.IntegerField(min_value=1)


class RegionalConfigurationResponseSerializer(serializers.ModelSerializer):
    document = RegionalConfigurationDocumentSerializer(read_only=True)

    class Meta:
        model = RegionalConfiguration
        fields = ["environment", "version", "document", "updated_at"]
        read_only_fields = fields


class RegionalConfigurationVersionSerializer(serializers.ModelSerializer):
    document = RegionalConfigurationDocumentSerializer(read_only=True)

    class Meta:
        model = RegionalConfigurationVersion
        fields = [
            "id",
            "environment",
            "version",
            "document",
            "operation",
            "actor_id",
            "correlation_id",
            "previous_version",
            "created_at",
        ]
        read_only_fields = fields


# Compatibility alias for imports outside this module. It is deliberately a
# response-only serializer so it cannot reintroduce serializer.save writes.
RegionalResourceSerializer = RegionalResourceResponseSerializer
