"""
DataMigration Models.

Defines data models for DataMigration module.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from django.db import models
from django.utils import timezone


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class TenantBaseModel(models.Model):
    """Base model for tenant-scoped models with Row-Level Multitenancy.

    CRITICAL: All tenant-scoped models MUST inherit from this base class
    and include tenant_id. All queries MUST filter explicitly by tenant_id.
    """

    tenant_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "data_migration"
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class MigrationJob(TenantBaseModel):
    """Migration job model for tracking data migration tasks."""

    SOURCE_TYPE_CHOICES = [
        ("csv", "CSV File"),
        ("excel", "Excel File"),
        ("json", "JSON File"),
        ("database", "Database"),
        ("api", "API"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255, db_index=True)
    source_type = models.CharField(
        max_length=50,
        choices=SOURCE_TYPE_CHOICES,
        db_index=True,
    )
    source_config = models.JSONField(
        default=dict,
        help_text="Source configuration (file path, database connection, etc.)",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    records_processed = models.IntegerField(default=0)
    records_failed = models.IntegerField(default=0)
    records_total = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        app_label = "data_migration"
        db_table = "data_migration_jobs"
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "source_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"


class MigrationMapping(TenantBaseModel):
    """Migration mapping model for field transformations."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    job = models.ForeignKey(
        MigrationJob,
        on_delete=models.CASCADE,
        related_name="mappings",
    )
    source_field = models.CharField(
        max_length=255,
        help_text="Source field name",
    )
    target_field = models.CharField(
        max_length=255,
        help_text="Target field name",
    )
    transform = models.JSONField(
        default=dict,
        help_text="Transformation rules (type conversion, default values, etc.)",
    )

    class Meta:
        app_label = "data_migration"
        db_table = "data_migration_mappings"
        indexes = [
            models.Index(fields=["tenant_id", "job"]),
        ]
        unique_together = [["job", "source_field"]]

    def __str__(self) -> str:
        return f"{self.job.name}: {self.source_field} -> {self.target_field}"


class MigrationLog(TenantBaseModel):
    """Migration log model for tracking migration progress."""

    LEVEL_CHOICES = [
        ("debug", "Debug"),
        ("info", "Info"),
        ("warning", "Warning"),
        ("error", "Error"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    job = models.ForeignKey(
        MigrationJob,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    level = models.CharField(
        max_length=20,
        choices=LEVEL_CHOICES,
        db_index=True,
    )
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "data_migration"
        db_table = "data_migration_logs"
        indexes = [
            models.Index(fields=["tenant_id", "job", "timestamp"]),
            models.Index(fields=["job", "level"]),
        ]

    def __str__(self) -> str:
        return f"{self.job.name} - {self.level}: {self.message[:50]}"


class MigrationValidation(TenantBaseModel):
    """Migration validation model for tracking validation errors."""

    STATUS_CHOICES = [
        ("passed", "Passed"),
        ("failed", "Failed"),
        ("warning", "Warning"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    job = models.ForeignKey(
        MigrationJob,
        on_delete=models.CASCADE,
        related_name="validations",
    )
    field = models.CharField(
        max_length=255,
        help_text="Field name being validated",
    )
    rule = models.CharField(
        max_length=255,
        help_text="Validation rule name",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        db_index=True,
    )
    message = models.TextField(blank=True)
    record_index = models.IntegerField(null=True, blank=True, help_text="Record index in source data")

    class Meta:
        app_label = "data_migration"
        db_table = "data_migration_validations"
        indexes = [
            models.Index(fields=["tenant_id", "job", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.job.name} - {self.field}: {self.status}"


class MigrationRollback(TenantBaseModel):
    """Migration rollback model for storing checkpoint data."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    job = models.ForeignKey(
        MigrationJob,
        on_delete=models.CASCADE,
        related_name="rollbacks",
    )
    checkpoint_data = models.JSONField(
        default=dict,
        help_text="Checkpoint data for rollback",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "data_migration"
        db_table = "data_migration_rollbacks"
        indexes = [
            models.Index(fields=["tenant_id", "job", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Rollback checkpoint for {self.job.name} at {self.created_at}"
