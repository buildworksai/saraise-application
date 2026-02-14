"""
Service tests for Multi-Company module.
"""

import uuid
import pytest

from src.modules.multi_company.models import Company
from src.modules.multi_company.services import CompanyService


@pytest.mark.django_db
class TestCompanyService:
    """Test CompanyService."""

    def test_create_company(self):
        """Test creating a company via service."""
        tenant_id = uuid.uuid4()
        company = CompanyService.create_company(
            tenant_id=str(tenant_id),
            company_code="COMP-001",
            company_name="Test Company",
        )

        assert company.company_code == "COMP-001"
        assert company.company_name == "Test Company"
        assert str(company.tenant_id) == str(tenant_id)
