"""
DRF Serializers for Multi-Company module.
"""

from rest_framework import serializers

from .models import Company


class CompanySerializer(serializers.ModelSerializer):
    """Company serializer."""

    class Meta:
        model = Company
        fields = [
            "id",
            "tenant_id",
            "company_code",
            "company_name",
            "legal_name",
            "tax_id",
            "address",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]
