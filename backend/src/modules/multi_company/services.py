"""
Business logic services for Multi-Company module.
"""

from .models import Company


class CompanyService:
    """Service for company operations."""

    @staticmethod
    def create_company(tenant_id: str, company_code: str, company_name: str, **kwargs) -> Company:
        """Create a new company."""
        return Company.objects.create(
            tenant_id=tenant_id,
            company_code=company_code,
            company_name=company_name,
            **kwargs,
        )
