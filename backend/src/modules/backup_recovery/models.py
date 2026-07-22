"""Tenant-safe persistence models for backup capture and artifact evidence.

The models deliberately contain no provider credentials.  Provider locations and
configuration are opaque references resolved at the adapter boundary.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from src.core.tenancy import TENANT_SCOPED, TenantQuerySet, TenantScopedModel, TimestampedModel, tenancy_scope


def generate_uuid() -> str:
    """Historical migration callable retained for ``0001_initial`` loading."""

    return str(uuid.uuid4())


class BackupJobStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class BackupType(models.TextChoices):
    FULL = "full", "Full"
    INCREMENTAL = "incremental", "Incremental"
    DIFFERENTIAL = "differential", "Differential"


class BackupScopeType(models.TextChoices):
    TENANT = "tenant", "Tenant"
    MODULE = "module", "Module"
    DATABASE = "database", "Database"
    FILES = "files", "Files"


class BackupFrequency(models.TextChoices):
    HOURLY = "hourly", "Hourly"
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"


# Public compatibility spelling used by the v2 service and serializer layers.
ScheduleFrequency = BackupFrequency


class ArchiveLifecycle(models.TextChoices):
    AVAILABLE = "available", "Available"
    EXPIRED = "expired", "Expired"
    PURGED = "purged", "Purged"


class IntegrityStatus(models.TextChoices):
    UNKNOWN = "unknown", "Unknown"
    VERIFYING = "verifying", "Verifying"
    VERIFIED = "verified", "Verified"
    CORRUPT = "corrupt", "Corrupt"


class VerificationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    PASSED = "passed", "Passed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class ActiveQuerySet(TenantQuerySet):
    """Default catalog queryset that hides soft-deleted mutable aggregates."""

    def delete(self) -> tuple[int, dict[str, int]]:  # pragma: no cover - defensive API
        raise TypeError("Backup catalog aggregates must be deleted through their service")


class ActiveManager(models.Manager.from_queryset(ActiveQuerySet)):  # type: ignore[misc]
    def get_queryset(self) -> ActiveQuerySet:
        return super().get_queryset().filter(is_deleted=False)


class AllWithDeletedManager(models.Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    """Explicit manager for retention and audit workflows."""


class CatalogModel(TenantScopedModel, TimestampedModel):
    """Shared identifiers and actor attribution for all six tenant tables."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.CharField(max_length=255)
    updated_by = models.CharField(max_length=255, blank=True)

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Relation and evidence invariants must also hold for internal ORM callers.
        self.full_clean()
        super().save(*args, **kwargs)


class MutableCatalogModel(CatalogModel):
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveManager()
    all_with_deleted = AllWithDeletedManager()

    class Meta:
        abstract = True

    def clean(self) -> None:
        super().clean()
        if self.is_deleted and self.deleted_at is None:
            raise ValidationError({"deleted_at": "Soft-deleted records require deleted_at."})
        if not self.is_deleted and self.deleted_at is not None:
            raise ValidationError({"deleted_at": "Active records cannot have deleted_at."})


def _validate_same_tenant(instance: models.Model, relation_names: Iterable[str]) -> None:
    errors: dict[str, str] = {}
    tenant_id = getattr(instance, "tenant_id", None)
    for name in relation_names:
        related_id = getattr(instance, f"{name}_id", None)
        if related_id is None:
            continue
        related = getattr(instance, name)
        if related.tenant_id != tenant_id:
            errors[name] = "Related record must belong to the same tenant."
    if errors:
        raise ValidationError(errors)


def _reject_secret_reference(value: str, field_name: str) -> None:
    lowered = value.lower()
    forbidden = ("?", "#", "password=", "passwd=", "secret=", "token=", "signature=", "x-amz-")
    if "://" in lowered and "@" in lowered.split("://", 1)[1].split("/", 1)[0]:
        raise ValidationError({field_name: "References must not contain inline credentials."})
    if any(fragment in lowered for fragment in forbidden):
        raise ValidationError({field_name: "References must not contain credentials or signed query data."})


@tenancy_scope(TENANT_SCOPED)
class BackupStorageTarget(MutableCatalogModel):
    name = models.CharField(max_length=120)
    adapter_key = models.CharField(max_length=120)
    locator_prefix_ref = models.CharField(max_length=1024)
    configuration_ref = models.CharField(max_length=255)
    encryption_key_ref = models.CharField(max_length=255, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "backup_recovery_storage_targets"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "name"), condition=Q(is_deleted=False), name="br_target_active_name_uq"
            ),
            models.UniqueConstraint(
                fields=("tenant_id",),
                condition=Q(is_deleted=False, is_active=True, is_default=True),
                name="br_target_one_default_uq",
            ),
            models.CheckConstraint(
                condition=Q(adapter_key__regex=r"^[a-z0-9]+(?:[-_.][a-z0-9]+)*$"),
                name="br_target_adapter_key_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "is_active", "is_default"), name="br_target_active_default_ix"),
            models.Index(fields=("tenant_id", "adapter_key"), name="br_target_adapter_ix"),
            models.Index(fields=("tenant_id", "is_deleted", "created_at"), name="br_target_deleted_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        if not re.fullmatch(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*", self.adapter_key or ""):
            raise ValidationError({"adapter_key": "Use a lowercase provider adapter key."})
        _reject_secret_reference(self.locator_prefix_ref, "locator_prefix_ref")
        _reject_secret_reference(self.configuration_ref, "configuration_ref")
        if self.encryption_key_ref:
            _reject_secret_reference(self.encryption_key_ref, "encryption_key_ref")
        if self.is_default and (not self.is_active or self.is_deleted):
            raise ValidationError({"is_default": "The default storage target must be active."})

    def __str__(self) -> str:
        return self.name


@tenancy_scope(TENANT_SCOPED)
class BackupRetentionPolicy(MutableCatalogModel):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    archive_after_days = models.PositiveIntegerField(null=True, blank=True)
    retention_days = models.PositiveIntegerField()
    keep_last_successful = models.PositiveIntegerField(default=3)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "backup_recovery_retention_policies"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "name"), condition=Q(is_deleted=False), name="br_policy_active_name_uq"
            ),
            models.CheckConstraint(
                condition=Q(retention_days__gte=1, retention_days__lte=3650), name="br_policy_retention_ck"
            ),
            models.CheckConstraint(
                condition=Q(archive_after_days__isnull=True) | Q(archive_after_days__lt=models.F("retention_days")),
                name="br_policy_archive_lt_ret_ck",
            ),
            models.CheckConstraint(condition=Q(keep_last_successful__gte=1), name="br_policy_keep_last_ck"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "is_active"), name="br_policy_active_ix"),
            models.Index(fields=("tenant_id", "name"), name="br_policy_name_ix"),
            models.Index(fields=("tenant_id", "is_deleted", "created_at"), name="br_policy_deleted_ix"),
        ]

    @property
    def policy_name(self) -> str:
        """Read-only compatibility alias for pre-v2 internal callers."""

        return self.name

    def __str__(self) -> str:
        return self.name


@tenancy_scope(TENANT_SCOPED)
class BackupSchedule(MutableCatalogModel):
    name = models.CharField(max_length=120)
    scope_type = models.CharField(max_length=20, choices=BackupScopeType.choices)
    scope_ref = models.CharField(max_length=255)
    backup_type = models.CharField(max_length=20, choices=BackupType.choices)
    frequency = models.CharField(max_length=20, choices=BackupFrequency.choices)
    schedule_time = models.TimeField(null=True, blank=True)
    day_of_week = models.PositiveSmallIntegerField(null=True, blank=True)
    day_of_month = models.PositiveSmallIntegerField(null=True, blank=True)
    timezone = models.CharField(max_length=64)
    storage_target = models.ForeignKey(BackupStorageTarget, on_delete=models.PROTECT, related_name="schedules")
    retention_policy = models.ForeignKey(BackupRetentionPolicy, on_delete=models.PROTECT, related_name="schedules")
    is_active = models.BooleanField(default=True, db_index=True)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "backup_recovery_schedules"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "name"), condition=Q(is_deleted=False), name="br_schedule_active_name_uq"
            ),
            models.CheckConstraint(
                condition=Q(day_of_week__isnull=True) | Q(day_of_week__range=(0, 6)), name="br_schedule_weekday_ck"
            ),
            models.CheckConstraint(
                condition=Q(day_of_month__isnull=True) | Q(day_of_month__range=(1, 28)), name="br_schedule_monthday_ck"
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        frequency="hourly",
                        schedule_time__isnull=True,
                        day_of_week__isnull=True,
                        day_of_month__isnull=True,
                    )
                    | Q(
                        frequency="daily",
                        schedule_time__isnull=False,
                        day_of_week__isnull=True,
                        day_of_month__isnull=True,
                    )
                    | Q(
                        frequency="weekly",
                        schedule_time__isnull=False,
                        day_of_week__isnull=False,
                        day_of_month__isnull=True,
                    )
                    | Q(
                        frequency="monthly",
                        schedule_time__isnull=False,
                        day_of_week__isnull=True,
                        day_of_month__isnull=False,
                    )
                ),
                name="br_schedule_frequency_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "is_active", "next_run_at"), name="br_schedule_due_ix"),
            models.Index(fields=("tenant_id", "scope_type", "scope_ref"), name="br_schedule_scope_ix"),
            models.Index(fields=("tenant_id", "backup_type", "frequency"), name="br_schedule_type_freq_ix"),
            models.Index(fields=("tenant_id", "is_deleted", "created_at"), name="br_schedule_deleted_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        _reject_secret_reference(self.scope_ref, "scope_ref")
        _validate_same_tenant(self, ("storage_target", "retention_policy"))
        if self.storage_target_id and (not self.storage_target.is_active or self.storage_target.is_deleted):
            raise ValidationError({"storage_target": "Storage target must be active."})
        if self.retention_policy_id and (not self.retention_policy.is_active or self.retention_policy.is_deleted):
            raise ValidationError({"retention_policy": "Retention policy must be active."})

    def __str__(self) -> str:
        return self.name


@tenancy_scope(TENANT_SCOPED)
class BackupJob(MutableCatalogModel):
    schedule = models.ForeignKey(
        BackupSchedule, null=True, blank=True, on_delete=models.PROTECT, related_name="backup_jobs"
    )
    storage_target = models.ForeignKey(BackupStorageTarget, on_delete=models.PROTECT, related_name="backup_jobs")
    retention_policy = models.ForeignKey(
        BackupRetentionPolicy, null=True, blank=True, on_delete=models.PROTECT, related_name="backup_jobs"
    )
    retry_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="retries")
    base_job = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="dependent_backups"
    )
    async_job_id = models.UUIDField(null=True, blank=True, unique=True)
    scope_type = models.CharField(max_length=20, choices=BackupScopeType.choices)
    scope_ref = models.CharField(max_length=255)
    backup_type = models.CharField(max_length=20, choices=BackupType.choices)
    status = models.CharField(max_length=20, choices=BackupJobStatus.choices, default=BackupJobStatus.PENDING)
    idempotency_key = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    requested_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    data_cutoff_at = models.DateTimeField(null=True, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    transition_history = models.JSONField(default=list, blank=True)
    storage_location = models.CharField(max_length=500, blank=True)  # deprecated, never exposed by API v2

    class Meta:
        db_table = "backup_recovery_jobs"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="br_job_idempotency_uq"),
            models.CheckConstraint(condition=Q(size_bytes__isnull=True) | Q(size_bytes__gte=0), name="br_job_size_ck"),
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True) | Q(started_at__isnull=False), name="br_job_completed_started_ck"
            ),
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True) | Q(completed_at__gte=models.F("started_at")),
                name="br_job_completion_order_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status="pending") | (Q(started_at__isnull=True) & Q(completed_at__isnull=True)),
                name="br_job_pending_times_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status="completed")
                | (Q(completed_at__isnull=False) & Q(data_cutoff_at__isnull=False) & Q(size_bytes__isnull=False)),
                name="br_job_completed_fields_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status="failed") | (Q(completed_at__isnull=False) & ~Q(error_code="")),
                name="br_job_failed_fields_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "requested_at"), name="br_job_status_ix"),
            models.Index(fields=("tenant_id", "backup_type", "requested_at"), name="br_job_type_ix"),
            models.Index(fields=("tenant_id", "schedule", "requested_at"), name="br_job_schedule_ix"),
            models.Index(fields=("tenant_id", "scope_type", "scope_ref", "requested_at"), name="br_job_scope_ix"),
            models.Index(fields=("tenant_id", "is_deleted", "created_at"), name="br_job_deleted_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        _reject_secret_reference(self.scope_ref, "scope_ref")
        _validate_same_tenant(self, ("schedule", "storage_target", "retention_policy", "retry_of", "base_job"))
        if self.retry_of_id == self.id:
            raise ValidationError({"retry_of": "A backup cannot retry itself."})
        if self.base_job_id == self.id:
            raise ValidationError({"base_job": "A backup cannot be its own baseline."})
        if self.backup_type in {BackupType.INCREMENTAL, BackupType.DIFFERENTIAL}:
            if self.base_job_id is None:
                raise ValidationError({"base_job": "Incremental and differential backups require a baseline."})
            if self.base_job.status != BackupJobStatus.COMPLETED:
                raise ValidationError({"base_job": "The baseline backup must be completed."})
        if self.status == BackupJobStatus.COMPLETED and self.pk and not self._state.adding:
            if not BackupArchive.objects.filter(backup_job_id=self.pk, tenant_id=self.tenant_id).exists():
                raise ValidationError({"status": "Completed backups require durable artifact evidence."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            previous = type(self).all_with_deleted.get(pk=self.pk)
            if self.transition_history[: len(previous.transition_history)] != previous.transition_history:
                raise ValidationError({"transition_history": "Transition history is append-only."})
            if previous.status in {
                BackupJobStatus.COMPLETED,
                BackupJobStatus.FAILED,
                BackupJobStatus.CANCELLED,
            }:
                mutable_after_terminal = {"is_deleted", "deleted_at", "updated_by"}
                changed = [
                    field.name
                    for field in self._meta.concrete_fields
                    if field.name not in mutable_after_terminal
                    and field.name not in {"updated_at"}
                    and getattr(previous, field.attname) != getattr(self, field.attname)
                ]
                if changed:
                    raise ValidationError({field: "Terminal backup jobs are immutable." for field in changed})
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.backup_type} backup - {self.status} ({self.id})"


@tenancy_scope(TENANT_SCOPED)
class BackupArchive(CatalogModel):
    backup_job = models.OneToOneField(BackupJob, on_delete=models.PROTECT, related_name="archive")
    lifecycle = models.CharField(max_length=20, choices=ArchiveLifecycle.choices, default=ArchiveLifecycle.AVAILABLE)
    adapter_key = models.CharField(max_length=120)
    artifact_locator_ref = models.CharField(max_length=1024)
    encryption_key_ref = models.CharField(max_length=255, blank=True)
    size_bytes = models.BigIntegerField()
    checksum_algorithm = models.CharField(max_length=20, default="sha256")
    checksum_digest = models.CharField(max_length=64)
    provider_acknowledgement = models.CharField(max_length=255)
    data_cutoff_at = models.DateTimeField()
    captured_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(default=timezone.now)
    integrity_status = models.CharField(max_length=20, choices=IntegrityStatus.choices, default=IntegrityStatus.UNKNOWN)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    purged_at = models.DateTimeField(null=True, blank=True)
    purge_async_job_id = models.UUIDField(null=True, blank=True, unique=True)
    purge_idempotency_key = models.CharField(max_length=128, blank=True)
    purge_attempt_count = models.PositiveIntegerField(default=0)
    last_purge_attempt_at = models.DateTimeField(null=True, blank=True)
    purge_error_code = models.CharField(max_length=64, blank=True)

    IMMUTABLE_FIELDS = frozenset(
        {
            "tenant_id",
            "backup_job_id",
            "adapter_key",
            "artifact_locator_ref",
            "encryption_key_ref",
            "size_bytes",
            "checksum_algorithm",
            "checksum_digest",
            "provider_acknowledgement",
            "data_cutoff_at",
            "captured_at",
            "expires_at",
            "archived_at",
            "created_by",
        }
    )

    class Meta:
        db_table = "backup_recovery_archives"
        constraints = [
            models.CheckConstraint(condition=Q(size_bytes__gte=0), name="br_archive_size_ck"),
            models.CheckConstraint(condition=Q(checksum_algorithm="sha256"), name="br_archive_sha256_ck"),
            models.CheckConstraint(condition=Q(checksum_digest__regex=r"^[0-9a-f]{64}$"), name="br_archive_digest_ck"),
            models.CheckConstraint(
                condition=~Q(lifecycle="purged") | Q(purged_at__isnull=False), name="br_archive_purged_ck"
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "lifecycle", "expires_at"), name="br_archive_lifecycle_ix"),
            models.Index(fields=("tenant_id", "integrity_status", "captured_at"), name="br_archive_integrity_ix"),
            models.Index(fields=("tenant_id", "captured_at"), name="br_archive_captured_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_same_tenant(self, ("backup_job",))
        _reject_secret_reference(self.artifact_locator_ref, "artifact_locator_ref")
        if self.encryption_key_ref:
            _reject_secret_reference(self.encryption_key_ref, "encryption_key_ref")
        _reject_secret_reference(self.provider_acknowledgement, "provider_acknowledgement")
        if self.checksum_algorithm != "sha256":
            raise ValidationError({"checksum_algorithm": "The OSS catalog supports SHA-256 evidence."})
        if not re.fullmatch(r"[0-9a-f]{64}", self.checksum_digest or ""):
            raise ValidationError({"checksum_digest": "Checksum must be 64 lowercase hexadecimal characters."})
        if self.purge_attempt_count < 0:
            raise ValidationError({"purge_attempt_count": "Purge attempts cannot be negative."})
        if self.backup_job_id and self.backup_job.status != BackupJobStatus.COMPLETED:
            completion_in_progress = (
                self.backup_job.status == BackupJobStatus.RUNNING
                and self.backup_job.completed_at is not None
                and self.backup_job.data_cutoff_at is not None
                and self.backup_job.size_bytes is not None
            )
            if not completion_in_progress:
                raise ValidationError({"backup_job": "Artifact evidence requires a completed backup job."})
        if self.backup_job_id and self.backup_job.status not in {
            BackupJobStatus.RUNNING,
            BackupJobStatus.COMPLETED,
        }:
            raise ValidationError({"backup_job": "Artifact evidence requires a running or completed backup."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            previous = type(self).objects.get(pk=self.pk)
            changed = [name for name in self.IMMUTABLE_FIELDS if getattr(previous, name) != getattr(self, name)]
            if changed:
                raise ValidationError({name: "Artifact evidence is immutable." for name in changed})
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("Backup archive evidence cannot be deleted")

    def __str__(self) -> str:
        return f"Artifact for {self.backup_job_id}"


@tenancy_scope(TENANT_SCOPED)
class BackupVerification(CatalogModel):
    archive = models.ForeignKey(BackupArchive, on_delete=models.PROTECT, related_name="verifications")
    # Durable linkage prevents verification redelivery and cancellation from
    # relying on a payload scan of the shared async-job table.
    async_job_id = models.UUIDField(null=True, blank=True, unique=True)
    status = models.CharField(max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING)
    idempotency_key = models.CharField(max_length=128)
    requested_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    checksum_matches = models.BooleanField(null=True, blank=True)
    artifact_available = models.BooleanField(null=True, blank=True)
    encryption_metadata_valid = models.BooleanField(null=True, blank=True)
    provider_acknowledged = models.BooleanField(null=True, blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    transition_history = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "backup_recovery_verifications"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="br_verify_idempotency_uq"),
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True) | Q(completed_at__gte=models.F("started_at")),
                name="br_verify_completion_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status="passed")
                | (
                    Q(checksum_matches=True)
                    & Q(artifact_available=True)
                    & Q(encryption_metadata_valid=True)
                    & Q(provider_acknowledged=True)
                ),
                name="br_verify_passed_ck",
            ),
            models.CheckConstraint(condition=~Q(status="failed") | ~Q(error_code=""), name="br_verify_failed_ck"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "requested_at"), name="br_verify_status_ix"),
            models.Index(fields=("tenant_id", "archive", "requested_at"), name="br_verify_archive_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_same_tenant(self, ("archive",))
        if not isinstance(self.evidence, dict):
            raise ValidationError({"evidence": "Verification evidence must be a JSON object."})
        if len(str(self.evidence)) > 16_384:
            raise ValidationError({"evidence": "Verification evidence exceeds the safe size limit."})
        serialized = str(self.evidence).lower()
        if any(key in serialized for key in ("password", "secret", "token", "signed_url", "artifact_content")):
            raise ValidationError({"evidence": "Verification evidence contains prohibited provider data."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            previous = type(self).objects.get(pk=self.pk)
            if self.transition_history[: len(previous.transition_history)] != previous.transition_history:
                raise ValidationError({"transition_history": "Transition history is append-only."})
            if previous.status in {
                VerificationStatus.PASSED,
                VerificationStatus.FAILED,
                VerificationStatus.CANCELLED,
            }:
                raise ValidationError({"status": "Terminal verification evidence is append-only."})
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("Backup verification evidence cannot be deleted")

    def __str__(self) -> str:
        return f"Verification {self.id} - {self.status}"
