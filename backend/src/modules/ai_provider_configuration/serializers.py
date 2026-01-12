"""
DRF Serializers for AiProviderConfiguration module.
Provides request/response validation for all models.
"""

from rest_framework import serializers

from .models import (
    AIModel,
    AIModelDeployment,
    AIProvider,
    AIProviderCredential,
    AIUsageLog,
)


class AIProviderSerializer(serializers.ModelSerializer):
    """Serializer for AIProvider model (read-only, platform-level)."""

    models_count = serializers.IntegerField(source="models.count", read_only=True)

    class Meta:
        model = AIProvider
        fields = [
            "id",
            "name",
            "provider_type",
            "base_url",
            "is_active",
            "models_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AIProviderCredentialSerializer(serializers.ModelSerializer):
    """Serializer for AIProviderCredential model."""

    provider_name = serializers.CharField(source="provider.name", read_only=True)
    provider_type = serializers.CharField(source="provider.provider_type", read_only=True)

    class Meta:
        model = AIProviderCredential
        fields = [
            "id",
            "tenant_id",
            "provider",
            "provider_name",
            "provider_type",
            "api_key_encrypted",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]

    def validate_api_key_encrypted(self, value):
        """Validate API key is not empty."""
        if not value:
            raise serializers.ValidationError("API key cannot be empty")
        return value


class AIModelSerializer(serializers.ModelSerializer):
    """Serializer for AIModel model (read-only, platform-level)."""

    provider_name = serializers.CharField(source="provider.name", read_only=True)
    provider_type = serializers.CharField(source="provider.provider_type", read_only=True)
    deployments_count = serializers.IntegerField(source="deployments.count", read_only=True)

    class Meta:
        model = AIModel
        fields = [
            "id",
            "provider",
            "provider_name",
            "provider_type",
            "model_id",
            "display_name",
            "capabilities",
            "pricing",
            "max_tokens",
            "is_active",
            "deployments_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AIModelDeploymentSerializer(serializers.ModelSerializer):
    """Serializer for AIModelDeployment model."""

    model_name = serializers.CharField(source="model.display_name", read_only=True)
    model_id = serializers.CharField(source="model.model_id", read_only=True)
    provider_name = serializers.CharField(source="model.provider.name", read_only=True)

    class Meta:
        model = AIModelDeployment
        fields = [
            "id",
            "tenant_id",
            "model",
            "model_name",
            "model_id",
            "provider_name",
            "config",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_by", "created_at", "updated_at"]


class AIUsageLogSerializer(serializers.ModelSerializer):
    """Serializer for AIUsageLog model."""

    deployment_model_name = serializers.CharField(source="deployment.model.display_name", read_only=True)

    class Meta:
        model = AIUsageLog
        fields = [
            "id",
            "tenant_id",
            "deployment",
            "deployment_model_name",
            "tokens_used",
            "input_tokens",
            "output_tokens",
            "cost",
            "timestamp",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "timestamp", "created_at", "updated_at"]
