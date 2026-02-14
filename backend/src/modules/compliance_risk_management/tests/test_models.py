"""
Model tests for Compliance Risk Management module.
"""

import uuid
import pytest

from src.modules.compliance_risk_management.models import ComplianceRisk


@pytest.mark.django_db
class TestComplianceRiskModel:
    """Test ComplianceRisk model."""

    def test_create_risk(self):
        """Test creating a compliance risk."""
        tenant_id = uuid.uuid4()
        risk = ComplianceRisk.objects.create(
            tenant_id=tenant_id,
            risk_code="RISK-001",
            risk_name="Test Risk",
            risk_level="high",
        )
        assert risk.risk_code == "RISK-001"
        assert risk.risk_level == "high"
        assert risk.status == "open"
