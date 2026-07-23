"""Explicit read/write contracts for AI-provider configuration."""

from __future__ import annotations

from uuid import UUID

from rest_framework import serializers

from .models import (
    AIModel,
    AIModelDeployment,
    AIProvider,
    AIProviderConfigurationResource,
    AIProviderCredential,
    AIProviderRuntimeConfiguration,
    AIProviderRuntimeConfigurationAudit,
    AIProviderRuntimeConfigurationVersion,
    AIUsageLog,
)


class UUIDIdentityField(serializers.UUIDField):
    """Keep UUID identity typed in ``response.data`` and stringify in JSON."""

    def to_representation(self, value: object) -> UUID:
        return value if isinstance(value, UUID) else UUID(str(value))


class AIProviderConfigurationResourceSerializer(serializers.ModelSerializer):
    """Read/write contract for the original tenant resource endpoint."""

    class Meta:
        model = AIProviderConfigurationResource
        fields = (
            "id",
            "tenant_id",
            "name",
            "description",
            "is_active",
            "config",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "tenant_id", "created_by", "created_at", "updated_at")

    def validate_name(self, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError("Name cannot be empty.")
        return normalized


class AIProviderListSerializer(serializers.ModelSerializer):
    id = UUIDIdentityField(read_only=True)
    models_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = AIProvider
        fields = (
            "id",
            "name",
            "provider_type",
            "is_active",
            "models_count",
            "created_at",
            "updated_at",
        )


class AIProviderDetailSerializer(AIProviderListSerializer):
    pass


class AIProviderCredentialListSerializer(serializers.ModelSerializer):
    id = UUIDIdentityField(read_only=True)
    provider_name = serializers.CharField(source="provider.name", read_only=True)
    provider_type = serializers.CharField(source="provider.provider_type", read_only=True)
    has_secret = serializers.BooleanField(read_only=True)
    last_error_code = serializers.CharField(read_only=True)

    class Meta:
        model = AIProviderCredential
        fields = (
            "id",
            "tenant_id",
            "provider",
            "provider_name",
            "provider_type",
            "label",
            "status",
            "secret_hint",
            "has_secret",
            "last_verified_at",
            "last_error_code",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AIProviderCredentialDetailSerializer(AIProviderCredentialListSerializer):
    pass


class AIProviderCredentialCreateSerializer(serializers.Serializer):
    provider = serializers.UUIDField()
    label = serializers.CharField(required=False, trim_whitespace=True)
    api_key = serializers.CharField(
        write_only=True,
        trim_whitespace=True,
        style={"input_type": "password"},
    )


class AIProviderCredentialUpdateSerializer(serializers.Serializer):
    provider = serializers.UUIDField(required=False)
    label = serializers.CharField(required=False, trim_whitespace=True)
    api_key = serializers.CharField(
        required=False,
        write_only=True,
        trim_whitespace=True,
        style={"input_type": "password"},
    )

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if not attrs:
            raise serializers.ValidationError("At least one editable field is required.")
        return attrs


class AIModelListSerializer(serializers.ModelSerializer):
    id = UUIDIdentityField(read_only=True)
    name = serializers.CharField(source="display_name", read_only=True)
    provider_name = serializers.CharField(source="provider.name", read_only=True)
    provider_type = serializers.CharField(source="provider.provider_type", read_only=True)
    deployments_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = AIModel
        fields = (
            "id",
            "provider",
            "provider_name",
            "provider_type",
            "model_id",
            "name",
            "display_name",
            "capabilities",
            "pricing",
            "max_tokens",
            "is_active",
            "deployments_count",
            "created_at",
            "updated_at",
        )


class AIModelDetailSerializer(AIModelListSerializer):
    pass


class AIModelDeploymentListSerializer(serializers.ModelSerializer):
    id = UUIDIdentityField(read_only=True)
    model_name = serializers.CharField(source="model.display_name", read_only=True)
    model_id = serializers.CharField(source="model.model_id", read_only=True)
    provider = serializers.UUIDField(source="model.provider_id", read_only=True)
    provider_name = serializers.CharField(source="model.provider.name", read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = AIModelDeployment
        fields = (
            "id",
            "tenant_id",
            "model",
            "model_id",
            "model_name",
            "provider",
            "provider_name",
            "credential",
            "deployment_name",
            "config",
            "status",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AIModelDeploymentDetailSerializer(AIModelDeploymentListSerializer):
    pass


class AIModelDeploymentCreateSerializer(serializers.Serializer):
    model = serializers.UUIDField()
    credential = serializers.UUIDField(required=False, allow_null=True)
    deployment_name = serializers.CharField(trim_whitespace=True)
    config = serializers.DictField(required=False, default=dict)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        return attrs


class AIModelDeploymentUpdateSerializer(serializers.Serializer):
    model = serializers.UUIDField(required=False)
    credential = serializers.UUIDField(required=False, allow_null=True)
    deployment_name = serializers.CharField(required=False, trim_whitespace=True)
    config = serializers.DictField(required=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if not attrs:
            raise serializers.ValidationError("At least one editable field is required.")
        return attrs


class AIUsageLogSerializer(serializers.ModelSerializer):
    id = UUIDIdentityField(read_only=True)
    deployment_name = serializers.CharField(source="deployment.deployment_name", read_only=True)
    model = serializers.UUIDField(source="deployment.model_id", read_only=True)
    model_id = serializers.CharField(source="deployment.model.model_id", read_only=True)
    model_name = serializers.CharField(source="deployment.model.display_name", read_only=True)
    input_tokens = serializers.IntegerField(source="prompt_tokens", read_only=True)
    output_tokens = serializers.IntegerField(source="completion_tokens", read_only=True)
    tokens_used = serializers.IntegerField(source="total_tokens", read_only=True)
    timestamp = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = AIUsageLog
        fields = (
            "id",
            "tenant_id",
            "deployment",
            "deployment_name",
            "model",
            "model_id",
            "model_name",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "input_tokens",
            "output_tokens",
            "tokens_used",
            "cost",
            "currency",
            "provider_request_id",
            "created_at",
            "timestamp",
        )
        read_only_fields = fields


class RotateKeySerializer(serializers.Serializer):
    """The generation action has no client-controlled fields."""


class ReEncryptSerializer(serializers.Serializer):
    old_key = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_key = serializers.CharField(write_only=True, style={"input_type": "password"})


class AIProviderRuntimeConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIProviderRuntimeConfiguration
        fields = ("id", "tenant_id", "environment", "values", "version", "updated_by", "created_at", "updated_at")
        read_only_fields = fields


class AIProviderRuntimeConfigurationWriteSerializer(serializers.Serializer):
    environment = serializers.CharField(max_length=64, required=False, default="default")
    values = serializers.DictField()


class AIProviderRuntimeConfigurationImportSerializer(serializers.Serializer):
    document = serializers.DictField()


class AIProviderRuntimeConfigurationRollbackSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    environment = serializers.CharField(max_length=64, required=False, default="default")


class AIProviderRuntimeConfigurationVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIProviderRuntimeConfigurationVersion
        fields = (
            "id",
            "tenant_id",
            "configuration",
            "version",
            "environment",
            "values",
            "created_by",
            "correlation_id",
            "rollback_of",
            "created_at",
        )
        read_only_fields = fields


class AIProviderRuntimeConfigurationAuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIProviderRuntimeConfigurationAudit
        fields = (
            "id",
            "tenant_id",
            "configuration",
            "action",
            "actor_id",
            "correlation_id",
            "from_version",
            "to_version",
            "before",
            "after",
            "rollback_of",
            "created_at",
        )
        read_only_fields = fields


# Stable names kept for existing schema imports.
AIProviderSerializer = AIProviderDetailSerializer
AIProviderCredentialSerializer = AIProviderCredentialDetailSerializer
AIModelSerializer = AIModelDetailSerializer
AIModelDeploymentSerializer = AIModelDeploymentDetailSerializer


__all__ = [name for name in globals() if name.endswith("Serializer")]
