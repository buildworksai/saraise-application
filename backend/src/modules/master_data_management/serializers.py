"""
DRF Serializers for Master Data Management module.
"""

from rest_framework import serializers

from .models import MasterDataEntity


class MasterDataEntitySerializer(serializers.ModelSerializer):
    """MasterDataEntity serializer."""

    class Meta:
        model = MasterDataEntity
        fields = [
            "id",
            "tenant_id",
            "entity_type",
            "entity_code",
            "entity_name",
            "data",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]
