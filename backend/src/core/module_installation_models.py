"""Module Installation Models.

Database models for tracking module installation lifecycle.
Task: 502.1 - Module Installation
"""

from __future__ import annotations

import uuid

from django.db import models


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class InstallationStatus(models.TextChoices):
    """Installation status enumeration."""

    PENDING = "pending", "Pending"
    VALIDATING = "validating", "Validating"
    INSTALLING = "installing", "Installing"
    MIGRATING = "migrating", "Migrating"
    REGISTERING = "registering", "Registering Permissions"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    ROLLING_BACK = "rolling_back", "Rolling Back"


class ModuleInstallation(models.Model):
    """Module installation tracking model.

    Tracks the installation lifecycle of a module for a tenant.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    tenant_id = models.CharField(max_length=36, db_index=True)
    module_name = models.CharField(max_length=255, db_index=True)
    module_version = models.CharField(max_length=50, db_index=True)
    registry_entry = models.ForeignKey(
        "ModuleRegistryEntry",
        on_delete=models.PROTECT,
        related_name="module_installations",
        db_index=True,
    )
    status = models.CharField(
        max_length=50,
        choices=InstallationStatus.choices,
        default=InstallationStatus.PENDING,
        db_index=True,
    )
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    installed_by = models.CharField(max_length=36, help_text="User/system who initiated installation")
    error_message = models.TextField(null=True, blank=True)
    error_details = models.JSONField(default=dict, help_text="Detailed error information")
    installation_log = models.JSONField(default=list, help_text="Installation step log")
    metadata = models.JSONField(default=dict, help_text="Installation metadata")

    class Meta:
        db_table = "module_installations"
        indexes = [
            models.Index(fields=["tenant_id", "module_name"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "started_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.module_name} v{self.module_version} (Tenant: {self.tenant_id}) - {self.status}"


class InstallationStep(models.Model):
    """Installation step tracking model.

    Tracks individual steps within an installation.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    installation = models.ForeignKey(
        ModuleInstallation,
        on_delete=models.CASCADE,
        related_name="steps",
        db_index=True,
    )
    step_name = models.CharField(max_length=255, db_index=True)
    step_order = models.IntegerField(db_index=True)
    status = models.CharField(
        max_length=50,
        choices=[
            ("pending", "Pending"),
            ("running", "Running"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("skipped", "Skipped"),
        ],
        default="pending",
        db_index=True,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    output = models.JSONField(default=dict, help_text="Step output/result")

    class Meta:
        db_table = "module_installation_steps"
        indexes = [
            models.Index(fields=["installation_id", "step_order"]),
            models.Index(fields=["installation_id", "status"]),
        ]
        ordering = ["step_order"]

    def __str__(self) -> str:
        return f"{self.step_name} ({self.status}) - Installation {self.installation.id}"
