"""
Model tests for Business Intelligence module.
"""

import uuid
import pytest

from src.modules.business_intelligence.models import Report


@pytest.mark.django_db
class TestReportModel:
    """Test Report model."""

    def test_create_report(self):
        """Test creating a report."""
        tenant_id = uuid.uuid4()
        report = Report.objects.create(
            tenant_id=tenant_id,
            report_code="RPT-001",
            report_name="Test Report",
            report_type="financial",
            query="SELECT * FROM accounts",
        )
        assert report.report_code == "RPT-001"
        assert report.report_type == "financial"
        assert report.is_active is True
