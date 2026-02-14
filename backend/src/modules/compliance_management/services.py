"""
Business logic services for Compliance Management module.
"""

from datetime import date
from .models import CompliancePolicy, ComplianceRequirement


class CompliancePolicyService:
    """Service for compliance policy operations."""

    @staticmethod
    def create_policy(tenant_id: str, policy_code: str, policy_name: str, regulation_type: str, effective_date: date, **kwargs) -> CompliancePolicy:
        """Create a new compliance policy."""
        return CompliancePolicy.objects.create(
            tenant_id=tenant_id,
            policy_code=policy_code,
            policy_name=policy_name,
            regulation_type=regulation_type,
            effective_date=effective_date,
            **kwargs,
        )


class ComplianceRequirementService:
    """Service for compliance requirement operations."""

    @staticmethod
    def create_requirement(tenant_id: str, policy_id: str, requirement_code: str, requirement_name: str, **kwargs) -> ComplianceRequirement:
        """Create a new compliance requirement."""
        return ComplianceRequirement.objects.create(
            tenant_id=tenant_id,
            policy_id=policy_id,
            requirement_code=requirement_code,
            requirement_name=requirement_name,
            **kwargs,
        )
