"""
DRF Serializers for IntegrationPlatform module.
Provides request/response validation for all models.
"""

from rest_framework import serializers

from .models import (
    Connector,
    DataMapping,
    Integration,
    IntegrationCredential,
    Webhook,
    WebhookDelivery,
)


class IntegrationSerializer(serializers.ModelSerializer):
    """Serializer for Integration model."""

    credentials_count = serializers.IntegerField(source="credentials.count", read_only=True)
    mappings_count = serializers.IntegerField(source="mappings.count", read_only=True)

    class Meta:
        model = Integration
        fields = [
            "id",
            "tenant_id",
            "name",
            "integration_type",
            "config",
            "status",
            "credentials_count",
            "mappings_count",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_by", "created_at", "updated_at"]

    def validate_name(self, value):
        """Validate name field."""
        if not value or not value.strip():
            raise serializers.ValidationError("Name cannot be empty")
        return value.strip()


class IntegrationCredentialSerializer(serializers.ModelSerializer):
    """Serializer for IntegrationCredential model."""

    integration_name = serializers.CharField(source="integration.name", read_only=True)

    class Meta:
        model = IntegrationCredential
        fields = [
            "id",
            "integration",
            "integration_name",
            "credential_type",
            "encrypted_value",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_encrypted_value(self, value):
        """Validate encrypted value is not empty."""
        if not value:
            raise serializers.ValidationError("Encrypted value cannot be empty")
        return value


class WebhookSerializer(serializers.ModelSerializer):
    """Serializer for Webhook model."""

    deliveries_count = serializers.IntegerField(source="deliveries.count", read_only=True)

    class Meta:
        model = Webhook
        fields = [
            "id",
            "tenant_id",
            "name",
            "url",
            "events",
            "secret",
            "is_active",
            "deliveries_count",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "secret", "created_by", "created_at", "updated_at"]

    def validate_name(self, value):
        """Validate name field."""
        if not value or not value.strip():
            raise serializers.ValidationError("Name cannot be empty")
        return value.strip()

    def validate_url(self, value):
        """Validate URL field."""
        if not value:
            raise serializers.ValidationError("URL cannot be empty")
        return value


class WebhookDeliverySerializer(serializers.ModelSerializer):
    """Serializer for WebhookDelivery model."""

    webhook_name = serializers.CharField(source="webhook.name", read_only=True)
    webhook_url = serializers.URLField(source="webhook.url", read_only=True)

    class Meta:
        model = WebhookDelivery
        fields = [
            "id",
            "webhook",
            "webhook_name",
            "webhook_url",
            "event",
            "payload",
            "status",
            "response_code",
            "response_body",
            "error_message",
            "delivered_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "response_code",
            "response_body",
            "error_message",
            "delivered_at",
            "created_at",
        ]


class ConnectorSerializer(serializers.ModelSerializer):
    """Serializer for Connector model (read-only, platform-level)."""

    class Meta:
        model = Connector
        fields = [
            "id",
            "name",
            "connector_type",
            "schema",
            "config",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class DataMappingSerializer(serializers.ModelSerializer):
    """Serializer for DataMapping model."""

    integration_name = serializers.CharField(source="integration.name", read_only=True)

    class Meta:
        model = DataMapping
        fields = [
            "id",
            "tenant_id",
            "integration",
            "integration_name",
            "source_field",
            "target_field",
            "transform",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]

    def validate_integration(self, value):
        """Validate integration belongs to same tenant."""
        if value and hasattr(self, "initial_data"):
            tenant_id = self.initial_data.get("tenant_id")
            if tenant_id and value.tenant_id != tenant_id:
                raise serializers.ValidationError("Integration must belong to the same tenant")
        return value
