"""
Business logic services for Compliance Risk Management module.
"""

from .models import ComplianceRisk


class ComplianceRiskService:
    """Service for compliance risk operations."""

    @staticmethod
    def create_risk(tenant_id: str, risk_code: str, risk_name: str, risk_level: str, **kwargs) -> ComplianceRisk:
        """Create a new compliance risk."""
        return ComplianceRisk.objects.create(
            tenant_id=tenant_id,
            risk_code=risk_code,
            risk_name=risk_name,
            risk_level=risk_level,
            **kwargs,
        )
