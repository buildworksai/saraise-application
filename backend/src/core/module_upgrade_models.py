"""Module Upgrade & Rollback Models.

Database models for tracking module upgrades and rollbacks.
Task: 502.2 - Module Upgrade & Rollback
"""

from __future__ import annotations

import uuid

from django.db import models


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class UpgradeStatus(models.TextChoices):
    """Upgrade status enumeration."""

    PENDING = "pending", "Pending"
    VALIDATING = "validating", "Validating"
    BACKING_UP = "backing_up", "Backing Up"
    UPGRADING = "upgrading", "Upgrading"
    MIGRATING = "migrating", "Migrating"
    VERIFYING = "verifying", "Verifying"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    ROLLING_BACK = "rolling_back", "Rolling Back"
    ROLLED_BACK = "rolled_back", "Rolled Back"


class ModuleUpgrade(models.Model):
    """Module upgrade tracking model.

    Tracks the upgrade lifecycle of a module for a tenant.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    tenant_id = models.CharField(max_length=36, db_index=True)
    module_name = models.CharField(max_length=255, db_index=True)
    from_version = models.CharField(max_length=50, db_index=True)
    to_version = models.CharField(max_length=50, db_index=True)
    registry_entry = models.ForeignKey(
        "ModuleRegistryEntry",
        on_delete=models.PROTECT,
        related_name="upgrades",
        db_index=True,
    )
    status = models.CharField(
        max_length=50,
        choices=UpgradeStatus.choices,
        default=UpgradeStatus.PENDING,
        db_index=True,
    )
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    upgraded_by = models.CharField(max_length=36, help_text="User/system who initiated upgrade")
    error_message = models.TextField(null=True, blank=True)
    error_details = models.JSONField(default=dict, help_text="Detailed error information")
    upgrade_log = models.JSONField(default=list, help_text="Upgrade step log")
    backup_snapshot = models.JSONField(null=True, blank=True, help_text="Backup snapshot data")
    rollback_data = models.JSONField(null=True, blank=True, help_text="Rollback data preservation")
    metadata = models.JSONField(default=dict, help_text="Upgrade metadata")

    class Meta:
        db_table = "module_upgrades"
        indexes = [
            models.Index(fields=["tenant_id", "module_name"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "started_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.module_name} {self.from_version} -> {self.to_version} "
            f"(Tenant: {self.tenant_id}) - {self.status}"
        )


class UpgradeStep(models.Model):
    """Upgrade step tracking model.

    Tracks individual steps within an upgrade.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    upgrade = models.ForeignKey(
        ModuleUpgrade,
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
            ("rolled_back", "Rolled Back"),
        ],
        default="pending",
        db_index=True,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    output = models.JSONField(default=dict, help_text="Step output/result")
    rollback_data = models.JSONField(null=True, blank=True, help_text="Step-specific rollback data")

    class Meta:
        db_table = "module_upgrade_steps"
        indexes = [
            models.Index(fields=["upgrade_id", "step_order"]),
            models.Index(fields=["upgrade_id", "status"]),
        ]
        ordering = ["step_order"]

    def __str__(self) -> str:
        return f"{self.step_name} ({self.status}) - Upgrade {self.upgrade.id}"
