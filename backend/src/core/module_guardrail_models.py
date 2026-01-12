"""Module Guardrail Models.

Database models for tracking guardrail violations and enforcement.
Task: 503.2 - Module Guardrails
"""

from __future__ import annotations

import uuid

from django.db import models


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class GuardrailViolationType(models.TextChoices):
    """Guardrail violation types."""

    AUTH_DRIFT = "auth_drift", "Auth Drift"
    POLICY_DRIFT = "policy_drift", "Policy Drift"
    SESSION_MANAGEMENT = "session_management", "Session Management"
    CREDENTIAL_HANDLING = "credential_handling", "Credential Handling"
    IDENTITY_FEDERATION = "identity_federation", "Identity Federation"
    PERMISSION_BYPASS = "permission_bypass", "Permission Bypass"
    POLICY_BYPASS = "policy_bypass", "Policy Bypass"


class GuardrailViolation(models.Model):
    """Guardrail violation model.

    Tracks guardrail violations detected in modules.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    tenant_id = models.CharField(max_length=36, db_index=True)
    module_name = models.CharField(max_length=255, db_index=True)
    violation_type = models.CharField(
        max_length=50,
        choices=GuardrailViolationType.choices,
        db_index=True,
    )
    severity = models.CharField(
        max_length=20,
        choices=[
            ("critical", "Critical"),
            ("high", "High"),
            ("medium", "Medium"),
            ("low", "Low"),
        ],
        default="high",
        db_index=True,
    )
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)
    detected_by = models.CharField(
        max_length=50,
        default="guardrail_scanner",
        help_text="Detection method/scanner",
    )
    violation_details = models.JSONField(default=dict, help_text="Detailed violation information")
    code_location = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        help_text="File path and line number",
    )
    status = models.CharField(
        max_length=50,
        choices=[
            ("detected", "Detected"),
            ("blocked", "Blocked"),
            ("resolved", "Resolved"),
            ("false_positive", "False Positive"),
        ],
        default="detected",
        db_index=True,
    )
    resolution_notes = models.TextField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(max_length=36, null=True, blank=True)

    class Meta:
        db_table = "guardrail_violations"
        indexes = [
            models.Index(fields=["tenant_id", "module_name"]),
            models.Index(fields=["tenant_id", "violation_type"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["module_name", "violation_type"]),
            models.Index(fields=["detected_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.violation_type} violation in {self.module_name} " f"(Tenant: {self.tenant_id}) - {self.status}"


class GuardrailRule(models.Model):
    """Guardrail rule model.

    Defines guardrail rules for enforcement.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    rule_name = models.CharField(max_length=255, unique=True, db_index=True)
    violation_type = models.CharField(
        max_length=50,
        choices=GuardrailViolationType.choices,
        db_index=True,
    )
    description = models.TextField(blank=True, null=True)
    pattern = models.TextField(help_text="Pattern/regex to detect violation")
    is_active = models.BooleanField(default=True, db_index=True)
    severity = models.CharField(
        max_length=20,
        choices=[
            ("critical", "Critical"),
            ("high", "High"),
            ("medium", "Medium"),
            ("low", "Low"),
        ],
        default="high",
    )
    action = models.CharField(
        max_length=50,
        choices=[
            ("block", "Block"),
            ("warn", "Warn"),
            ("audit", "Audit Only"),
        ],
        default="block",
        help_text="Action to take on violation",
    )
    metadata = models.JSONField(default=dict, help_text="Rule metadata")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "guardrail_rules"
        indexes = [
            models.Index(fields=["violation_type"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.rule_name} ({self.violation_type})"
