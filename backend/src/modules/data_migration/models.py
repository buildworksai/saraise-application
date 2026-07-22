"""Tenant-safe domain models for durable data migration."""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from src.core.tenancy import TenantQuerySet, TenantScopedModel, TimestampedModel


def generate_uuid() -> str:
    """Legacy migration callable retained for applied migrations 0001/0002."""
    return str(uuid.uuid4())


def default_allowed_target_adapters() -> list[str]:
    """Return a fresh, migration-serializable default adapter allow-list."""
    return ["core.record"]


class ImmutableEvidenceError(ValidationError):
    """Raised when append-only migration evidence is changed or removed."""


class AppendOnlyQuerySet(TenantQuerySet):
    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ImmutableEvidenceError("Migration evidence is append-only.", code="append_only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableEvidenceError("Migration evidence is append-only.", code="append_only")


class AppendOnlyTenantModel(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableEvidenceError("Migration evidence is append-only.", code="append_only")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ImmutableEvidenceError("Migration evidence is append-only.", code="append_only")


class MutableTenantModel(TenantScopedModel, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class ExternalConnection(MutableTenantModel):
    class Kind(models.TextChoices):
        POSTGRESQL = "postgresql", "PostgreSQL"
        MYSQL = "mysql", "MySQL"
        HTTP = "http", "HTTP API"

    class TLSMode(models.TextChoices):
        VERIFY_FULL = "verify-full", "Verify hostname and certificate"
        VERIFY_CA = "verify-ca", "Verify certificate authority"

    name = models.CharField(max_length=255)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    host = models.CharField(max_length=255, null=True, blank=True)
    port = models.PositiveIntegerField(null=True, blank=True)
    database = models.CharField(max_length=128, null=True, blank=True)
    username = models.CharField(max_length=128, null=True, blank=True)
    base_url = models.URLField(null=True, blank=True)
    credential_ref = models.CharField(max_length=255)
    tls_mode = models.CharField(max_length=20, choices=TLSMode.choices, default=TLSMode.VERIFY_FULL)
    public_options = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.UUIDField()
    updated_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "data_migration_external_connections"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "name"), name="dm_conn_tenant_name_uniq"),
            models.CheckConstraint(condition=Q(port__isnull=True) | Q(port__gte=1, port__lte=65535), name="dm_conn_port_range"),
            models.CheckConstraint(
                condition=(Q(kind__in=("postgresql", "mysql"), host__isnull=False, port__isnull=False, database__isnull=False, username__isnull=False, base_url__isnull=True) | Q(kind="http", host__isnull=True, port__isnull=True, database__isnull=True, username__isnull=True, base_url__isnull=False)),
                name="dm_conn_kind_fields",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "is_active", "name"), name="dm_conn_active_name_idx"),
            models.Index(fields=("tenant_id", "kind", "is_active"), name="dm_conn_kind_active_idx"),
        ]

    @property
    def db_scheme(self) -> str:
        """Read-only compatibility name for pre-v2 callers."""
        return self.kind

    def clean(self) -> None:
        super().clean()
        if self.kind == self.Kind.HTTP and self.base_url and not self.base_url.lower().startswith("https://"):
            raise ValidationError({"base_url": "HTTP connections require an HTTPS base URL."})
        if not isinstance(self.public_options, dict):
            raise ValidationError({"public_options": "Public options must be an object."})

    def __str__(self) -> str:
        return f"{self.name} ({self.kind})"


class MigrationJob(MutableTenantModel):
    class SourceType(models.TextChoices):
        CSV = "csv", "CSV"
        EXCEL = "excel", "Excel"
        JSON = "json", "JSON"
        XML = "xml", "XML"
        DATABASE = "database", "Database"
        API = "api", "API"

    class WriteMode(models.TextChoices):
        CREATE = "create", "Create"
        UPSERT = "upsert", "Upsert"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        READY = "ready", "Ready"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=255)
    description = models.TextField(default="", blank=True)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    source_artifact_id = models.UUIDField(null=True, blank=True)
    source_config = models.JSONField(default=dict, blank=True)
    target_adapter = models.CharField(max_length=100)
    target_entity = models.CharField(max_length=100)
    write_mode = models.CharField(max_length=20, choices=WriteMode.choices, default=WriteMode.CREATE)
    lookup_fields = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    configuration_version = models.PositiveIntegerField(default=1)
    transition_history = models.JSONField(default=list, blank=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.UUIDField()
    updated_by = models.UUIDField(null=True, blank=True)
    # Preserved legacy execution evidence. New executions write MigrationRun.
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    records_processed = models.IntegerField(default=0)
    records_failed = models.IntegerField(default=0)
    records_total = models.IntegerField(default=0)
    error_message = models.TextField(default="", blank=True)

    class Meta:
        db_table = "data_migration_jobs"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "name"), condition=Q(is_deleted=False), name="dm_job_live_name_uniq"),
            models.CheckConstraint(condition=Q(configuration_version__gte=1), name="dm_job_version_gte_1"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "-created_at"), name="dm_job_status_created_idx"),
            models.Index(fields=("tenant_id", "source_type", "-created_at"), name="dm_job_source_created_idx"),
            models.Index(fields=("tenant_id", "target_adapter", "target_entity"), name="dm_job_target_idx"),
            models.Index(fields=("tenant_id", "is_deleted", "name"), name="dm_job_deleted_name_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        from .schemas import validate_source_config

        self.source_config = validate_source_config(self.source_type, self.source_config)
        if self.source_type in {self.SourceType.CSV, self.SourceType.EXCEL, self.SourceType.JSON, self.SourceType.XML} and not self.source_artifact_id:
            raise ValidationError({"source_artifact_id": "File sources require an immutable DMS artifact version."})
        if self.write_mode == self.WriteMode.UPSERT and not self.lookup_fields:
            raise ValidationError({"lookup_fields": "Upsert mode requires at least one lookup field."})
        if not isinstance(self.lookup_fields, list) or not all(isinstance(v, str) and v.strip() for v in self.lookup_fields):
            raise ValidationError({"lookup_fields": "Lookup fields must be a list of non-empty field names."})

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"


class MigrationJobVersion(AppendOnlyTenantModel):
    job = models.ForeignKey(MigrationJob, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    change_summary = models.CharField(max_length=500)
    created_by = models.UUIDField()
    correlation_id = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "data_migration_job_versions"
        constraints = [models.UniqueConstraint(fields=("job", "version"), name="dm_job_version_uniq")]
        indexes = [models.Index(fields=("tenant_id", "job", "-version"), name="dm_job_version_idx")]

    def clean(self) -> None:
        super().clean()
        if self.job_id and self.tenant_id and not MigrationJob.objects.filter(id=self.job_id, tenant_id=self.tenant_id).exists():
            raise ValidationError({"job": "The job must belong to the same tenant."})
        if isinstance(self.snapshot, dict):
            if self.snapshot.get("tenant_id") != str(self.tenant_id) or self.snapshot.get("job_id") != str(self.job_id):
                raise ValidationError({"snapshot": "Snapshot tenant and job identity must match the parent."})
            forbidden = {"created_by", "updated_by", "async_job_id"}.intersection(self.snapshot)
            if forbidden:
                raise ValidationError({"snapshot": f"Snapshot contains forbidden identity fields: {', '.join(sorted(forbidden))}."})

    def __str__(self) -> str:
        return f"{self.job_id} v{self.version}"


class MigrationMapping(MutableTenantModel):
    class Origin(models.TextChoices):
        MANUAL = "manual", "Manual"
        DETERMINISTIC = "deterministic", "Deterministic"
        EXTENSION = "extension", "Extension"

    job = models.ForeignKey(MigrationJob, on_delete=models.CASCADE, related_name="mappings")
    source_field = models.CharField(max_length=255)
    target_field = models.CharField(max_length=255)
    position = models.PositiveIntegerField()
    transform_type = models.CharField(max_length=30, default="identity")
    transform_config = models.JSONField(default=dict, blank=True)
    is_required = models.BooleanField(default=False)
    origin = models.CharField(max_length=20, choices=Origin.choices, default=Origin.MANUAL)
    confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    created_by = models.UUIDField()
    updated_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "data_migration_mappings"
        constraints = [
            models.UniqueConstraint(fields=("job", "source_field"), name="dm_mapping_source_uniq"),
            models.UniqueConstraint(fields=("job", "target_field"), name="dm_mapping_target_uniq"),
            models.UniqueConstraint(fields=("job", "position"), name="dm_mapping_position_uniq"),
            models.CheckConstraint(condition=Q(confidence__isnull=True) | Q(confidence__gte=0, confidence__lte=1), name="dm_mapping_confidence_range"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "job", "position"), name="dm_mapping_position_idx"),
            models.Index(fields=("tenant_id", "job", "target_field"), name="dm_mapping_target_idx"),
        ]

    @property
    def transform(self) -> dict[str, Any]:
        return {"type": self.transform_type, **self.transform_config}

    def clean(self) -> None:
        super().clean()
        from .schemas import validate_transform_config

        self.transform_config = validate_transform_config(self.transform_type, self.transform_config)
        if self.job_id and not MigrationJob.objects.filter(id=self.job_id, tenant_id=self.tenant_id).exists():
            raise ValidationError({"job": "The job must belong to the same tenant."})

    def __str__(self) -> str:
        return f"{self.job_id}: {self.source_field} -> {self.target_field}"


class ValidationRule(MutableTenantModel):
    class Severity(models.TextChoices):
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    job = models.ForeignKey(MigrationJob, on_delete=models.CASCADE, related_name="validation_rules")
    field_name = models.CharField(max_length=255)
    rule_type = models.CharField(max_length=30)
    rule_config = models.JSONField(default=dict, blank=True)
    error_message = models.CharField(max_length=500)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.ERROR)
    position = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    created_by = models.UUIDField()
    updated_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "data_migration_validation_rules"
        constraints = [models.UniqueConstraint(fields=("job", "position"), name="dm_rule_position_uniq")]
        indexes = [
            models.Index(fields=("tenant_id", "job", "is_active", "position"), name="dm_rule_active_position_idx"),
            models.Index(fields=("tenant_id", "job", "field_name"), name="dm_rule_field_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        from .schemas import validate_rule_config

        self.rule_config = validate_rule_config(self.rule_type, self.rule_config)
        if self.job_id and not MigrationJob.objects.filter(id=self.job_id, tenant_id=self.tenant_id).exists():
            raise ValidationError({"job": "The job must belong to the same tenant."})

    def __str__(self) -> str:
        return f"{self.job_id}: {self.field_name} {self.rule_type}"


class MigrationRun(MutableTenantModel):
    class Mode(models.TextChoices):
        DRY_RUN = "dry_run", "Dry run"
        COMMIT = "commit", "Commit"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        ROLLED_BACK = "rolled_back", "Rolled back"

    job = models.ForeignKey(MigrationJob, on_delete=models.PROTECT, related_name="runs")
    job_version = models.ForeignKey(MigrationJobVersion, on_delete=models.PROTECT, related_name="runs")
    async_job_id = models.UUIDField(unique=True)
    mode = models.CharField(max_length=10, choices=Mode.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    idempotency_key = models.CharField(max_length=255)
    source_checksum = models.CharField(max_length=128)
    total_records = models.PositiveBigIntegerField(default=0)
    processed_records = models.PositiveBigIntegerField(default=0)
    succeeded_records = models.PositiveBigIntegerField(default=0)
    failed_records = models.PositiveBigIntegerField(default=0)
    warning_records = models.PositiveBigIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancel_requested_at = models.DateTimeField(null=True, blank=True)
    transition_history = models.JSONField(default=list, blank=True)
    created_by = models.UUIDField()
    correlation_id = models.CharField(max_length=128)

    class Meta:
        db_table = "data_migration_runs"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="dm_run_idempotency_uniq"),
            models.CheckConstraint(condition=Q(processed_records__lte=models.F("total_records")), name="dm_run_processed_lte_total"),
            models.CheckConstraint(condition=Q(succeeded_records__lte=models.F("processed_records") - models.F("failed_records")), name="dm_run_outcomes_lte_processed"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "job", "-created_at"), name="dm_run_job_created_idx"),
            models.Index(fields=("tenant_id", "status", "-created_at"), name="dm_run_status_created_idx"),
            models.Index(fields=("tenant_id", "mode", "-created_at"), name="dm_run_mode_created_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.job_id and not MigrationJob.objects.filter(id=self.job_id, tenant_id=self.tenant_id).exists():
            raise ValidationError({"job": "The job must belong to the same tenant."})
        if self.job_version_id and not MigrationJobVersion.objects.filter(id=self.job_version_id, tenant_id=self.tenant_id, job_id=self.job_id).exists():
            raise ValidationError({"job_version": "The version must belong to this tenant and job."})

    def __str__(self) -> str:
        return f"{self.job_id} {self.mode} ({self.status})"


class MigrationRunIssue(AppendOnlyTenantModel):
    class Stage(models.TextChoices):
        SOURCE = "source", "Source"
        MAPPING = "mapping", "Mapping"
        VALIDATION = "validation", "Validation"
        TARGET = "target", "Target"
        SYSTEM = "system", "System"

    class Severity(models.TextChoices):
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    run = models.ForeignKey(MigrationRun, on_delete=models.PROTECT, related_name="issues")
    row_number = models.PositiveBigIntegerField(null=True, blank=True)
    field_name = models.CharField(max_length=255, default="", blank=True)
    stage = models.CharField(max_length=20, choices=Stage.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    code = models.CharField(max_length=100)
    message = models.CharField(max_length=500)
    redacted_sample = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "data_migration_run_issues"
        indexes = [
            models.Index(fields=("tenant_id", "run", "severity", "row_number"), name="dm_issue_severity_row_idx"),
            models.Index(fields=("tenant_id", "run", "code"), name="dm_issue_code_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.run_id and not MigrationRun.objects.filter(id=self.run_id, tenant_id=self.tenant_id).exists():
            raise ValidationError({"run": "The run must belong to the same tenant."})
        forbidden = {"password", "secret", "token", "credential", "email", "phone", "ssn"}
        if not isinstance(self.redacted_sample, dict) or any(
            any(marker in str(key).lower() for marker in forbidden) and value != "[REDACTED]"
            for key, value in self.redacted_sample.items()
        ):
            raise ValidationError({"redacted_sample": "Samples must be structured and redact PII and secrets."})


class MigrationChange(AppendOnlyTenantModel):
    class Operation(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"

    run = models.ForeignKey(MigrationRun, on_delete=models.PROTECT, related_name="changes")
    sequence = models.PositiveBigIntegerField()
    target_adapter = models.CharField(max_length=100)
    target_entity = models.CharField(max_length=100)
    target_record_id = models.CharField(max_length=255)
    operation = models.CharField(max_length=10, choices=Operation.choices)
    before_payload_encrypted = models.TextField(default="", blank=True)
    after_checksum = models.CharField(max_length=128)
    idempotency_key = models.CharField(max_length=255)
    reversed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "data_migration_changes"
        constraints = [
            models.UniqueConstraint(fields=("run", "sequence"), name="dm_change_sequence_uniq"),
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="dm_change_idempotency_uniq"),
            models.CheckConstraint(condition=Q(operation="create", before_payload_encrypted="") | (Q(operation="update") & ~Q(before_payload_encrypted="")), name="dm_change_before_payload"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "run", "-sequence"), name="dm_change_sequence_idx"),
            models.Index(fields=("tenant_id", "target_adapter", "target_entity", "target_record_id"), name="dm_change_target_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.run_id and not MigrationRun.objects.filter(id=self.run_id, tenant_id=self.tenant_id, mode=MigrationRun.Mode.COMMIT).exists():
            raise ValidationError({"run": "Changes require a committed run owned by the tenant."})

    def mark_reversed(self, occurred_at: Any) -> None:
        """Record the single permitted evidence evolution without exposing general updates."""
        if self.reversed_at is not None:
            return
        self.reversed_at = occurred_at
        models.Model.save(self, update_fields=("reversed_at",))


class MigrationRollback(MutableTenantModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    run = models.OneToOneField(MigrationRun, on_delete=models.PROTECT, related_name="rollback")
    async_job_id = models.UUIDField(unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    idempotency_key = models.CharField(max_length=255)
    records_total = models.PositiveBigIntegerField(default=0)
    records_reversed = models.PositiveBigIntegerField(default=0)
    records_failed = models.PositiveBigIntegerField(default=0)
    failure_summary = models.TextField(default="", blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    transition_history = models.JSONField(default=list, blank=True)
    requested_by = models.UUIDField()
    correlation_id = models.CharField(max_length=128)

    class Meta:
        db_table = "data_migration_rollbacks"
        constraints = [models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="dm_rollback_idempotency_uniq")]
        indexes = [
            models.Index(fields=("tenant_id", "status", "-created_at"), name="dm_rollback_status_idx"),
            models.Index(fields=("tenant_id", "run"), name="dm_rollback_run_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        allowed = (MigrationRun.Status.SUCCEEDED, MigrationRun.Status.PARTIAL)
        if self.run_id and not MigrationRun.objects.filter(id=self.run_id, tenant_id=self.tenant_id, mode=MigrationRun.Mode.COMMIT, status__in=allowed).exists():
            raise ValidationError({"run": "Only successful or partial committed runs may be rolled back."})

    def __str__(self) -> str:
        return f"Rollback {self.id} ({self.status})"


class DataMigrationConfiguration(MutableTenantModel):
    """Runtime operational controls; exactly one current document per tenant."""

    source_row_limit = models.PositiveIntegerField(default=100_000, validators=[MinValueValidator(1), MaxValueValidator(10_000_000)])
    batch_size = models.PositiveIntegerField(default=500, validators=[MinValueValidator(1), MaxValueValidator(10_000)])
    connect_timeout_seconds = models.PositiveIntegerField(default=10, validators=[MinValueValidator(1), MaxValueValidator(120)])
    read_timeout_seconds = models.PositiveIntegerField(default=30, validators=[MinValueValidator(1), MaxValueValidator(600)])
    retry_count = models.PositiveSmallIntegerField(default=2, validators=[MinValueValidator(0), MaxValueValidator(10)])
    issue_sample_limit = models.PositiveSmallIntegerField(default=25, validators=[MinValueValidator(0), MaxValueValidator(1000)])
    preview_row_limit = models.PositiveSmallIntegerField(default=100, validators=[MinValueValidator(1), MaxValueValidator(100)])
    retention_days = models.PositiveIntegerField(default=90, validators=[MinValueValidator(1), MaxValueValidator(3650)])
    allowed_target_adapters = models.JSONField(default=default_allowed_target_adapters)
    enabled_roles = models.JSONField(default=list, blank=True)
    rollout_percentage = models.PositiveSmallIntegerField(default=100, validators=[MinValueValidator(0), MaxValueValidator(100)])
    enabled = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.UUIDField()
    updated_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "data_migration_configuration"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id",), name="dm_config_tenant_uniq"),
            models.CheckConstraint(condition=Q(version__gte=1), name="dm_config_version_gte_1"),
            models.CheckConstraint(condition=Q(source_row_limit__gte=1, source_row_limit__lte=10_000_000), name="dm_config_row_limit_range"),
            models.CheckConstraint(condition=Q(batch_size__gte=1, batch_size__lte=10_000), name="dm_config_batch_range"),
            models.CheckConstraint(condition=Q(connect_timeout_seconds__gte=1, connect_timeout_seconds__lte=120), name="dm_config_connect_range"),
            models.CheckConstraint(condition=Q(read_timeout_seconds__gte=1, read_timeout_seconds__lte=600), name="dm_config_read_range"),
            models.CheckConstraint(condition=Q(retry_count__lte=10), name="dm_config_retry_range"),
            models.CheckConstraint(condition=Q(issue_sample_limit__lte=1000), name="dm_config_sample_range"),
            models.CheckConstraint(condition=Q(retention_days__gte=1, retention_days__lte=3650), name="dm_config_retention_range"),
        ]

    def clean(self) -> None:
        super().clean()
        for field in ("allowed_target_adapters", "enabled_roles"):
            values = getattr(self, field)
            if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
                raise ValidationError({field: "Must be a list of non-empty stable names."})
            if len(values) != len(set(values)):
                raise ValidationError({field: "Duplicate values are not allowed."})
        allowed_roles = {"tenant_admin", "data_operator", "auditor"}
        if set(self.enabled_roles) - allowed_roles:
            raise ValidationError({"enabled_roles": "Contains an unsupported rollout role."})

    def as_document(self) -> dict[str, Any]:
        return {
            field: getattr(self, field)
            for field in (
                "source_row_limit", "batch_size", "connect_timeout_seconds", "read_timeout_seconds",
                "retry_count", "issue_sample_limit", "preview_row_limit", "retention_days",
                "enabled_roles", "rollout_percentage", "enabled",
                "allowed_target_adapters",
            )
        }


class DataMigrationConfigurationAudit(AppendOnlyTenantModel):
    """Immutable configuration version used for audit, export, and rollback."""

    configuration = models.ForeignKey(DataMigrationConfiguration, on_delete=models.PROTECT, related_name="audit_versions")
    version = models.PositiveIntegerField()
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField()
    changed_by = models.UUIDField()
    correlation_id = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "data_migration_configuration_audits"
        constraints = [models.UniqueConstraint(fields=("configuration", "version"), name="dm_config_audit_version_uniq")]
        indexes = [models.Index(fields=("tenant_id", "configuration", "-version"), name="dm_config_audit_version_idx")]

    def clean(self) -> None:
        super().clean()
        if self.configuration_id and not DataMigrationConfiguration.objects.filter(id=self.configuration_id, tenant_id=self.tenant_id).exists():
            raise ValidationError({"configuration": "Configuration must belong to the same tenant."})


class MigrationLog(MutableTenantModel):
    """Preserved read-only-compatible legacy execution log."""
    created_by = models.UUIDField()
    updated_by = models.UUIDField(null=True, blank=True)
    job = models.ForeignKey(MigrationJob, on_delete=models.CASCADE, related_name="legacy_logs")
    level = models.CharField(max_length=20)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "data_migration_logs"
        indexes = [models.Index(fields=("tenant_id", "job", "timestamp"), name="dm_legacy_log_idx")]


class MigrationValidation(MutableTenantModel):
    """Preserved legacy validation outcome; new rules use ValidationRule."""
    created_by = models.UUIDField()
    updated_by = models.UUIDField(null=True, blank=True)
    job = models.ForeignKey(MigrationJob, on_delete=models.CASCADE, related_name="legacy_validations")
    field = models.CharField(max_length=255)
    rule = models.CharField(max_length=255)
    status = models.CharField(max_length=20)
    message = models.TextField(blank=True)
    record_index = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "data_migration_validations"
        indexes = [models.Index(fields=("tenant_id", "job", "status"), name="dm_legacy_validation_idx")]


class LegacyMigrationRollback(MutableTenantModel):
    """Preserved ambiguous v1 checkpoints; never executable."""
    created_by = models.UUIDField()
    updated_by = models.UUIDField(null=True, blank=True)
    job = models.ForeignKey(MigrationJob, on_delete=models.CASCADE, related_name="legacy_rollbacks")
    checkpoint_data = models.JSONField(default=dict)

    class Meta:
        db_table = "data_migration_legacy_rollbacks"


__all__ = [
    "DataMigrationConfiguration", "DataMigrationConfigurationAudit", "ExternalConnection",
    "LegacyMigrationRollback", "MigrationChange", "MigrationJob", "MigrationJobVersion",
    "MigrationLog", "MigrationMapping", "MigrationRollback", "MigrationRun", "MigrationRunIssue",
    "MigrationValidation", "ValidationRule", "generate_uuid",
]
