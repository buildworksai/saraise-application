"""
Backup & Recovery (Extended) Models.

Extended backup capabilities: incremental backups, retention policies, archive management.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from django.db import models
from django.utils import timezone


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class BackupJobStatus(models.TextChoices):
    """Backup job status choices."""

    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class BackupType(models.TextChoices):
    """Backup type choices."""

    FULL = "full", "Full Backup"
    INCREMENTAL = "incremental", "Incremental Backup"
    DIFFERENTIAL = "differential", "Differential Backup"


class BackupFrequency(models.TextChoices):
    """Backup schedule frequency choices."""

    HOURLY = "hourly", "Hourly"
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"


class TenantBaseModel(models.Model):
    """Base model for tenant-scoped models with Row-Level Multitenancy.

    CRITICAL: All tenant-scoped models MUST inherit from this base class
    and include tenant_id. All queries MUST filter explicitly by tenant_id.
    """

    tenant_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "backup_recovery"
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class BackupJob(TenantBaseModel):
    """Backup job model for tracking backup operations."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    backup_type = models.CharField(
        max_length=20,
        choices=BackupType.choices,
        db_index=True,
        help_text="Type of backup: full, incremental, or differential",
    )
    status = models.CharField(
        max_length=20,
        choices=BackupJobStatus.choices,
        default=BackupJobStatus.PENDING,
        db_index=True,
    )
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    backup_size_bytes = models.BigIntegerField(null=True, blank=True)
    storage_location = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        app_label = "backup_recovery"
        db_table = "backup_recovery_jobs"
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "backup_type"]),
            models.Index(fields=["tenant_id", "start_time"]),
            models.Index(fields=["status", "start_time"]),
        ]

    def __str__(self) -> str:
        return f"{self.backup_type} backup - {self.status} ({self.id})"


class BackupSchedule(TenantBaseModel):
    """Backup schedule model for automated backups."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    frequency = models.CharField(
        max_length=20,
        choices=BackupFrequency.choices,
        db_index=True,
        help_text="How often to run backups",
    )
    schedule_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Time of day to run (for daily/weekly/monthly)",
    )
    retention_days = models.IntegerField(
        default=30,
        help_text="Number of days to retain backups",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    backup_type = models.CharField(
        max_length=20,
        choices=BackupType.choices,
        default=BackupType.FULL,
        help_text="Type of backup to create",
    )
    description = models.TextField(blank=True)
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        app_label = "backup_recovery"
        db_table = "backup_recovery_schedules"
        indexes = [
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["tenant_id", "frequency"]),
            models.Index(fields=["is_active", "frequency"]),
        ]

    def __str__(self) -> str:
        return f"{self.frequency} backup schedule ({self.id})"


class BackupRetentionPolicy(TenantBaseModel):
    """Backup retention policy model for managing backup lifecycle."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    policy_name = models.CharField(max_length=255, db_index=True)
    retention_days = models.IntegerField(
        help_text="Number of days to retain backups before archiving",
    )
    archive_after_days = models.IntegerField(
        help_text="Number of days after which backups are archived",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    description = models.TextField(blank=True)
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        app_label = "backup_recovery"
        db_table = "backup_recovery_retention_policies"
        indexes = [
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["tenant_id", "policy_name"]),
        ]

    def __str__(self) -> str:
        return f"{self.policy_name} ({self.id})"


class BackupArchive(TenantBaseModel):
    """Backup archive model for archived backups."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    backup_job = models.ForeignKey(
        BackupJob,
        on_delete=models.CASCADE,
        related_name="archives",
        help_text="Reference to the original backup job",
    )
    archive_location = models.CharField(
        max_length=500,
        help_text="Location where archived backup is stored",
    )
    archived_at = models.DateTimeField(auto_now_add=True, db_index=True)
    archive_size_bytes = models.BigIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        app_label = "backup_recovery"
        db_table = "backup_recovery_archives"
        indexes = [
            models.Index(fields=["tenant_id", "archived_at"]),
            models.Index(fields=["backup_job", "archived_at"]),
        ]

    def __str__(self) -> str:
        return f"Archive of {self.backup_job.id} ({self.id})"
