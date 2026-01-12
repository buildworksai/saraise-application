"""Compliance Models.

Database models for compliance checks and validation.
Task: 503.3 - Compliance Checks
"""

from __future__ import annotations

import uuid

from django.db import models


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class ComplianceCheckType(models.TextChoices):
    """Compliance check types."""

    RESIDENCY = "residency", "Data Residency"
    POLICY_BUNDLE = "policy_bundle", "Policy Bundle"
    SCHEMA_COMPLIANCE = "schema_compliance", "Schema Compliance"
    PERMISSION_COMPLIANCE = "permission_compliance", "Permission Compliance"
    SOD_COMPLIANCE = "sod_compliance", "SoD Compliance"


class ComplianceCheck(models.Model):
    """Compliance check model.

    Tracks compliance checks for modules and tenants.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    tenant_id = models.CharField(max_length=36, db_index=True, null=True, blank=True)
    module_name = models.CharField(max_length=255, db_index=True, null=True, blank=True)
    check_type = models.CharField(
        max_length=50,
        choices=ComplianceCheckType.choices,
        db_index=True,
    )
    status = models.CharField(
        max_length=50,
        choices=[
            ("pending", "Pending"),
            ("passing", "Passing"),
            ("failing", "Failing"),
            ("warning", "Warning"),
        ],
        default="pending",
        db_index=True,
    )
    checked_at = models.DateTimeField(auto_now_add=True, db_index=True)
    checked_by = models.CharField(
        max_length=50,
        default="compliance_scanner",
        help_text="Check method/scanner",
    )
    check_details = models.JSONField(default=dict, help_text="Detailed check information")
    violations = models.JSONField(default=list, help_text="List of violations found")
    metadata = models.JSONField(default=dict, help_text="Check metadata")

    class Meta:
        db_table = "compliance_checks"
        indexes = [
            models.Index(fields=["tenant_id", "module_name"]),
            models.Index(fields=["tenant_id", "check_type"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["module_name", "check_type"]),
            models.Index(fields=["checked_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.check_type} check for " f"{self.module_name or 'tenant ' + self.tenant_id} - {self.status}"


class ResidencyRule(models.Model):
    """Data residency rule model.

    Defines data residency requirements.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    tenant_id = models.CharField(
        max_length=36, db_index=True, null=True, blank=True, help_text="Tenant-specific rule (null = global)"
    )
    module_name = models.CharField(
        max_length=255, db_index=True, null=True, blank=True, help_text="Module-specific rule (null = all modules)"
    )
    required_region = models.CharField(max_length=100, db_index=True, help_text="Required data residency region")
    is_active = models.BooleanField(default=True, db_index=True)
    description = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict, help_text="Rule metadata")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "residency_rules"
        indexes = [
            models.Index(fields=["tenant_id", "module_name"]),
            models.Index(fields=["required_region"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        scope = (
            f"{self.module_name}" if self.module_name else f"Tenant {self.tenant_id}" if self.tenant_id else "Global"
        )
        return f"Residency rule: {scope} → {self.required_region}"


class PolicyBundleValidation(models.Model):
    """Policy bundle validation model.

    Tracks policy bundle validation results.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    tenant_id = models.CharField(max_length=36, db_index=True)
    module_name = models.CharField(max_length=255, db_index=True)
    policy_bundle_version = models.CharField(max_length=50, db_index=True)
    validation_status = models.CharField(
        max_length=50,
        choices=[
            ("valid", "Valid"),
            ("invalid", "Invalid"),
            ("warning", "Warning"),
        ],
        db_index=True,
    )
    validated_at = models.DateTimeField(auto_now_add=True, db_index=True)
    validation_errors = models.JSONField(default=list, help_text="Validation errors")
    validation_warnings = models.JSONField(default=list, help_text="Validation warnings")
    metadata = models.JSONField(default=dict, help_text="Validation metadata")

    class Meta:
        db_table = "policy_bundle_validations"
        indexes = [
            models.Index(fields=["tenant_id", "module_name"]),
            models.Index(fields=["tenant_id", "validation_status"]),
            models.Index(fields=["policy_bundle_version"]),
        ]

    def __str__(self) -> str:
        return (
            f"Policy bundle validation: {self.module_name} " f"v{self.policy_bundle_version} - {self.validation_status}"
        )
