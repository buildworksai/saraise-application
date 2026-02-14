"""
Service tests for Compliance Risk Management module.
"""

import uuid
import pytest

from src.modules.compliance_risk_management.models import ComplianceRisk
from src.modules.compliance_risk_management.services import ComplianceRiskService


@pytest.mark.django_db
class TestComplianceRiskService:
    """Test ComplianceRiskService."""

    def test_create_risk(self):
        """Test creating a risk via service."""
        tenant_id = uuid.uuid4()
        risk = ComplianceRiskService.create_risk(
            tenant_id=str(tenant_id),
            risk_code="RISK-001",
            risk_name="Test Risk",
            risk_level="high",
        )

        assert risk.risk_code == "RISK-001"
        assert risk.risk_level == "high"
        assert str(risk.tenant_id) == str(tenant_id)
