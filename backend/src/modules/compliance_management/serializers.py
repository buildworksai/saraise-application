"""
DRF Serializers for Compliance Management module.
"""

from rest_framework import serializers

from .models import CompliancePolicy, ComplianceRequirement


class CompliancePolicySerializer(serializers.ModelSerializer):
    """CompliancePolicy serializer."""

    class Meta:
        model = CompliancePolicy
        fields = [
            "id",
            "tenant_id",
            "policy_code",
            "policy_name",
            "regulation_type",
            "description",
            "effective_date",
            "expiry_date",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class ComplianceRequirementSerializer(serializers.ModelSerializer):
    """ComplianceRequirement serializer."""

    policy_code = serializers.CharField(source="policy.policy_code", read_only=True)
    policy_name = serializers.CharField(source="policy.policy_name", read_only=True)

    class Meta:
        model = ComplianceRequirement
        fields = [
            "id",
            "tenant_id",
            "policy",
            "policy_code",
            "policy_name",
            "requirement_code",
            "requirement_name",
            "description",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]
