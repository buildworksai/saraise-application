"""
Compliance Risk Management Models.

Defines data models for risks, assessments, and mitigations.
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


class RiskLevel(models.TextChoices):
    """Risk level choices."""

    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class ComplianceRisk(TenantBaseModel):
    """Compliance risk model - Risk assessment record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    risk_code = models.CharField(max_length=50, db_index=True)
    risk_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    risk_level = models.CharField(max_length=50, choices=RiskLevel.choices, default=RiskLevel.MEDIUM, db_index=True)
    status = models.CharField(max_length=50, default="open", db_index=True)  # open, mitigated, closed
    mitigation_plan = models.TextField(blank=True)

    class Meta:
        db_table = "compliance_risks"
        indexes = [
            models.Index(fields=["tenant_id", "risk_code"]),
            models.Index(fields=["tenant_id", "risk_level"]),
            models.Index(fields=["tenant_id", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "risk_code"], name="unique_risk_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.risk_code} - {self.risk_name}"
