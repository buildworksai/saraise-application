"""
Compliance Management Models.

Defines data models for policies, requirements, and audit records.
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


class CompliancePolicy(TenantBaseModel):
    """Compliance policy model - Regulatory policy definition."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    policy_code = models.CharField(max_length=50, db_index=True)
    policy_name = models.CharField(max_length=255)
    regulation_type = models.CharField(max_length=100, db_index=True)  # GDPR, SOX, HIPAA, etc.
    description = models.TextField(blank=True)
    effective_date = models.DateField(db_index=True)
    expiry_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "compliance_policies"
        indexes = [
            models.Index(fields=["tenant_id", "policy_code"]),
            models.Index(fields=["tenant_id", "regulation_type"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "policy_code"], name="unique_policy_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.policy_code} - {self.policy_name}"


class ComplianceRequirement(TenantBaseModel):
    """Compliance requirement model - Specific compliance requirement."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    policy = models.ForeignKey(CompliancePolicy, on_delete=models.CASCADE, related_name="requirements")
    requirement_code = models.CharField(max_length=50, db_index=True)
    requirement_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=50, default="pending", db_index=True)  # pending, compliant, non_compliant

    class Meta:
        db_table = "compliance_requirements"
        indexes = [
            models.Index(fields=["tenant_id", "policy"]),
            models.Index(fields=["tenant_id", "requirement_code"]),
            models.Index(fields=["tenant_id", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.requirement_code} - {self.requirement_name}"
