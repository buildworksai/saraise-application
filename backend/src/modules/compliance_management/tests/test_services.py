"""
Service tests for Compliance Management module.
"""

import uuid
import pytest
from datetime import date

from src.modules.compliance_management.models import CompliancePolicy
from src.modules.compliance_management.services import CompliancePolicyService


@pytest.mark.django_db
class TestCompliancePolicyService:
    """Test CompliancePolicyService."""

    def test_create_policy(self):
        """Test creating a policy via service."""
        tenant_id = uuid.uuid4()
        policy = CompliancePolicyService.create_policy(
            tenant_id=str(tenant_id),
            policy_code="POL-001",
            policy_name="Test Policy",
            regulation_type="GDPR",
            effective_date=date(2024, 1, 1),
        )

        assert policy.policy_code == "POL-001"
        assert policy.regulation_type == "GDPR"
        assert str(policy.tenant_id) == str(tenant_id)
