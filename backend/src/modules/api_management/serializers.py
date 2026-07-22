"""Transport-only serializers for API management contracts."""

from __future__ import annotations

from rest_framework import serializers

from .models import ApiManagementConfiguration, ApiManagementConfigurationVersion, ApiManagementResource


class ApiManagementResourceInputSerializer(serializers.Serializer):
    """Accepted client fields; ownership and lifecycle state are excluded."""

    name = serializers.CharField(trim_whitespace=False)
    description = serializers.CharField(required=False, allow_blank=True)
    config = serializers.DictField(required=False)

    def validate(self, attrs):
        allowed = {"name", "description", "config"}
        unknown = set(self.initial_data) - allowed
        if unknown:
            raise serializers.ValidationError(
                {field: "Field is not accepted from clients." for field in sorted(unknown)}
            )
        return attrs


class ApiManagementResourceSerializer(serializers.ModelSerializer):
    """Public resource representation without tenant or actor identifiers."""

    class Meta:
        model = ApiManagementResource
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "config",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ConfigurationDocumentSerializer(serializers.Serializer):
    """Opaque at transport; services.py is the authoritative typed validator."""

    document = serializers.DictField()
    idempotency_key = serializers.UUIDField(required=False)


class ConfigurationRollbackSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.UUIDField(required=False)


class ApiManagementConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiManagementConfiguration
        fields = ["version", "document", "updated_at"]
        read_only_fields = fields


class ApiManagementConfigurationVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiManagementConfigurationVersion
        fields = ["version", "document", "actor_id", "correlation_id", "created_at"]
        read_only_fields = fields


class ConfigurationPreviewSerializer(serializers.Serializer):
    valid = serializers.BooleanField(read_only=True)
    normalized_document = serializers.DictField(read_only=True)
    changes = serializers.ListField(child=serializers.DictField(), read_only=True)


# Legacy import name now resolves to the safe output contract.
TenantBaseModelSerializer = ApiManagementResourceSerializer


__all__ = [
    "ApiManagementConfigurationSerializer",
    "ApiManagementConfigurationVersionSerializer",
    "ApiManagementResourceInputSerializer",
    "ApiManagementResourceSerializer",
    "ConfigurationDocumentSerializer",
    "ConfigurationPreviewSerializer",
    "ConfigurationRollbackSerializer",
    "TenantBaseModelSerializer",
]
