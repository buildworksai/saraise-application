"""
Model tests for Compliance Management module.
"""

import uuid
import pytest
from datetime import date

from src.modules.compliance_management.models import CompliancePolicy


@pytest.mark.django_db
class TestCompliancePolicyModel:
    """Test CompliancePolicy model."""

    def test_create_policy(self):
        """Test creating a compliance policy."""
        tenant_id = uuid.uuid4()
        policy = CompliancePolicy.objects.create(
            tenant_id=tenant_id,
            policy_code="POL-001",
            policy_name="Test Policy",
            regulation_type="GDPR",
            effective_date=date(2024, 1, 1),
        )
        assert policy.policy_code == "POL-001"
        assert policy.regulation_type == "GDPR"
        assert policy.is_active is True
