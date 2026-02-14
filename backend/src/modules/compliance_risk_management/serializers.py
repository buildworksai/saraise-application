"""
DRF Serializers for Compliance Risk Management module.
"""

from rest_framework import serializers

from .models import ComplianceRisk


class ComplianceRiskSerializer(serializers.ModelSerializer):
    """ComplianceRisk serializer."""

    class Meta:
        model = ComplianceRisk
        fields = [
            "id",
            "tenant_id",
            "risk_code",
            "risk_name",
            "description",
            "risk_level",
            "status",
            "mitigation_plan",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]
