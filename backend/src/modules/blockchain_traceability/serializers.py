"""
DRF Serializers for BlockchainTraceability module.
Provides request/response validation for all models.
"""

from rest_framework import serializers

from .models import BlockchainTraceabilityResource


class BlockchainTraceabilityResourceSerializer(serializers.ModelSerializer):
    """Serializer for BlockchainTraceabilityResource model."""

    class Meta:
        model = BlockchainTraceabilityResource
        fields = [
            "id",
            "tenant_id",
            "name",
            "description",
            "is_active",
            "config",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_by", "created_at", "updated_at"]

    def validate(self, data):
        """Custom validation."""
        # TODO: Add module-specific validation logic
        return data

    def validate_name(self, value):
        """Validate name field."""
        if not value or not value.strip():
            raise serializers.ValidationError("Name cannot be empty")
        return value.strip()
