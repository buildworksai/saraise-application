"""
Model tests for Multi-Company module.
"""

import uuid
import pytest

from src.modules.multi_company.models import Company


@pytest.mark.django_db
class TestCompanyModel:
    """Test Company model."""

    def test_create_company(self):
        """Test creating a company."""
        tenant_id = uuid.uuid4()
        company = Company.objects.create(
            tenant_id=tenant_id,
            company_code="COMP-001",
            company_name="Test Company",
        )
        assert company.company_code == "COMP-001"
        assert company.company_name == "Test Company"
        assert company.is_active is True
