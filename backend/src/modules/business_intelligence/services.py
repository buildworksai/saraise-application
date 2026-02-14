"""
Business logic services for Business Intelligence module.
"""

from .models import Dashboard, Report


class ReportService:
    """Service for report operations."""

    @staticmethod
    def create_report(tenant_id: str, report_code: str, report_name: str, report_type: str, query: str, **kwargs) -> Report:
        """Create a new report."""
        return Report.objects.create(
            tenant_id=tenant_id,
            report_code=report_code,
            report_name=report_name,
            report_type=report_type,
            query=query,
            **kwargs,
        )


class DashboardService:
    """Service for dashboard operations."""

    @staticmethod
    def create_dashboard(tenant_id: str, dashboard_code: str, dashboard_name: str, layout: dict, **kwargs) -> Dashboard:
        """Create a new dashboard."""
        return Dashboard.objects.create(
            tenant_id=tenant_id,
            dashboard_code=dashboard_code,
            dashboard_name=dashboard_name,
            layout=layout,
            **kwargs,
        )
