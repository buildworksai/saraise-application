"""
Service tests for Business Intelligence module.
"""

import uuid
import pytest

from src.modules.business_intelligence.models import Report
from src.modules.business_intelligence.services import ReportService


@pytest.mark.django_db
class TestReportService:
    """Test ReportService."""

    def test_create_report(self):
        """Test creating a report via service."""
        tenant_id = uuid.uuid4()
        report = ReportService.create_report(
            tenant_id=str(tenant_id),
            report_code="RPT-001",
            report_name="Test Report",
            report_type="financial",
            query="SELECT * FROM accounts",
        )

        assert report.report_code == "RPT-001"
        assert report.report_type == "financial"
        assert str(report.tenant_id) == str(tenant_id)
