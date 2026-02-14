"""
Business Intelligence Models.

Defines data models for reports, dashboards, and insights.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from django.db import models


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class TenantBaseModel(models.Model):
    """Base model for tenant-scoped models with Row-Level Multitenancy.

    CRITICAL: All tenant-scoped models MUST inherit from this base class
    and include tenant_id. All queries MUST filter explicitly by tenant_id.
    """

    tenant_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class Report(TenantBaseModel):
    """Report model - BI report definition."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    report_code = models.CharField(max_length=50, db_index=True)
    report_name = models.CharField(max_length=255)
    report_type = models.CharField(max_length=50, db_index=True)  # financial, sales, inventory, etc.
    query = models.TextField(help_text="SQL query or report definition")
    parameters = models.JSONField(default=dict, help_text="Report parameters")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "bi_reports"
        indexes = [
            models.Index(fields=["tenant_id", "report_code"]),
            models.Index(fields=["tenant_id", "report_type"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "report_code"], name="unique_report_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.report_code} - {self.report_name}"


class Dashboard(TenantBaseModel):
    """Dashboard model - BI dashboard configuration."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    dashboard_code = models.CharField(max_length=50, db_index=True)
    dashboard_name = models.CharField(max_length=255)
    layout = models.JSONField(default=dict, help_text="Dashboard widget layout")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "bi_dashboards"
        indexes = [
            models.Index(fields=["tenant_id", "dashboard_code"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "dashboard_code"], name="unique_dashboard_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.dashboard_code} - {self.dashboard_name}"
