"""Tenant-isolated disaster-recovery domain models.

Backup capture and retention remain owned by :mod:`backup_recovery`.  The UUID
fields in this module that point at that bounded context are deliberately
opaque: ownership and existence are established through the backup catalog
port, never through an ORM relationship.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.deletion import ProtectedError

from src.core.tenancy import TenantQuerySet, TenantScopedModel, TimestampedModel


def generate_uuid() -> str:
    """Retain the callable referenced by historical migration ``0001``."""

    return str(uuid.uuid4())


def configured_step_timeout_default() -> int:
    from .services import DEFAULT_CONFIGURATION_DOCUMENT

    return int(DEFAULT_CONFIGURATION_DOCUMENT["steps"]["default_timeout_seconds"])


def configured_step_retry_default() -> int:
    from .services import DEFAULT_CONFIGURATION_DOCUMENT

    return int(DEFAULT_CONFIGURATION_DOCUMENT["steps"]["default_retry_limit"])


def _tenant_policy(tenant_id: uuid.UUID) -> Mapping[str, Any]:
    from .services import get_configuration

    return get_configuration(tenant_id).document


class ScopeType(models.TextChoices):
    TENANT = "tenant", "Tenant"
    MODULE = "module", "Module"
    DATABASE = "database", "Database"
    FILES = "files", "Files"


class BackupType(models.TextChoices):
    FULL = "full", "Full"
    INCREMENTAL = "incremental", "Incremental"
    DIFFERENTIAL = "differential", "Differential"


class RecoveryPointStatus(models.TextChoices):
    DISCOVERED = "discovered", "Discovered"
    VERIFYING = "verifying", "Verifying"
    AVAILABLE = "available", "Available"
    CORRUPT = "corrupt", "Corrupt"
    EXPIRED = "expired", "Expired"
    DELETED = "deleted", "Deleted"


class TargetEnvironment(models.TextChoices):
    ISOLATED = "isolated", "Isolated"
    STANDBY = "standby", "Standby"
    PRODUCTION = "production", "Production"


class RestoreMode(models.TextChoices):
    FULL = "full", "Full"
    SELECTIVE = "selective", "Selective"


class RestoreRunStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    VALIDATING = "validating", "Validating"
    READY = "ready", "Ready"
    RESTORING = "restoring", "Restoring"
    VERIFYING = "verifying", "Verifying"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class RunbookStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    RETIRED = "retired", "Retired"


class RunbookActionType(models.TextChoices):
    VALIDATE_RECOVERY_POINT = "validate_recovery_point", "Validate recovery point"
    RESTORE = "restore", "Restore"
    VERIFY = "verify", "Verify"
    FAILOVER = "failover", "Failover"
    FAILBACK = "failback", "Failback"
    MANUAL_APPROVAL = "manual_approval", "Manual approval"
    NOTIFY = "notify", "Notify"
    EXTENSION = "extension", "Extension"


class StepFailureBehavior(models.TextChoices):
    STOP = "stop", "Stop"
    CONTINUE_DEGRADED = "continue_degraded", "Continue degraded"


class ExerciseType(models.TextChoices):
    TABLETOP = "tabletop", "Tabletop"
    RESTORE = "restore", "Restore"
    FAILOVER = "failover", "Failover"
    FULL = "full", "Full"


class ExerciseEnvironment(models.TextChoices):
    ISOLATED = "isolated", "Isolated"
    STANDBY = "standby", "Standby"
    PRODUCTION = "production", "Production"


class ExerciseStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    PASSED = "passed", "Passed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class StepExecutionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    PASSED = "passed", "Passed"
    FAILED = "failed", "Failed"
    DEGRADED = "degraded", "Degraded"
    SKIPPED = "skipped", "Skipped"


# Stable aliases make the domain vocabulary pleasant for ports and extensions.
ActionType = RunbookActionType
OnFailure = StepFailureBehavior
DRExerciseStatus = ExerciseStatus
DRStepExecutionStatus = StepExecutionStatus

_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SLUG = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
_COMPONENT = re.compile(r"^[a-z][a-z0-9_.-]{0,119}$")
_FORBIDDEN_PARAMETER_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "credential",
        "credentials",
        "password",
        "private_key",
        "script",
        "secret",
        "token",
        "url",
    }
)


def _require_non_empty(value: str, field: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not normalized:
        raise ValidationError({field: "This value must not be empty."})
    return normalized


def _require_object(value: Any, field: str) -> None:
    if not isinstance(value, dict):
        raise ValidationError({field: "Must be a JSON object."})


def _require_list(value: Any, field: str) -> None:
    if not isinstance(value, list):
        raise ValidationError({field: "Must be a JSON array."})


def _contains_unsafe_parameter(value: Any) -> bool:
    """Reject credentials, executable snippets, and network destinations."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in _FORBIDDEN_PARAMETER_KEYS or normalized_key.endswith(("_secret", "_token", "_url")):
                return True
            if _contains_unsafe_parameter(nested):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_unsafe_parameter(item) for item in value)
    elif isinstance(value, str):
        lowered = value.strip().lower()
        return lowered.startswith(("http://", "https://", "file://", "javascript:"))
    return False


class ProtectedDomainQuerySet(TenantQuerySet):
    """Prevent bulk writes from bypassing aggregate validation and retention."""

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ValidationError("Bulk updates are forbidden for disaster-recovery aggregates.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ProtectedError("Disaster-recovery domain records cannot be hard-deleted", list(self[:1]))


class DomainModel(TenantScopedModel, TimestampedModel):
    """Common validation and hard-deletion guard for governed evidence."""

    _immutable_fields: ClassVar[frozenset[str]] = frozenset({"tenant_id"})

    objects = ProtectedDomainQuerySet.as_manager()

    class Meta:
        abstract = True

    def _stored_values(self, fields: Sequence[str]) -> dict[str, Any] | None:
        if self._state.adding or self.pk is None:
            return None
        return type(self).objects.filter(pk=self.pk).values(*fields).first()

    def _validate_immutable_fields(self, fields: Sequence[str] | None = None) -> None:
        names = tuple(fields or self._immutable_fields)
        stored = self._stored_values(names)
        if stored is None:
            return
        changed = [name for name in names if stored[name] != getattr(self, name)]
        if changed:
            raise ValidationError({name: "This field is immutable after creation." for name in changed})

    def _validate_transition_append_only(self) -> None:
        """Require each status change to append one internally consistent record."""

        if not hasattr(self, "status") or not hasattr(self, "transition_history"):
            return
        history = self.transition_history
        if not isinstance(history, list):
            return  # The concrete model reports the more useful field error.
        if self._state.adding:
            if history:
                raise ValidationError({"transition_history": "New records cannot supply transition history."})
            return
        stored = self._stored_values(["status", "transition_history"])
        if stored is None:
            return
        previous_history = stored["transition_history"]
        if history == previous_history and self.status == stored["status"]:
            return
        if not isinstance(previous_history, list) or history[: len(previous_history)] != previous_history:
            raise ValidationError({"transition_history": "Transition history is append-only."})
        if len(history) != len(previous_history) + 1:
            raise ValidationError({"transition_history": "A state change must append exactly one transition."})
        record = history[-1]
        if not isinstance(record, dict):
            raise ValidationError({"transition_history": "Transition entries must be JSON objects."})
        required = {"transition_key", "command", "from_state", "to_state", "occurred_at", "metadata"}
        if set(record) != required or not isinstance(record.get("metadata"), dict):
            raise ValidationError({"transition_history": "Transition entry schema is invalid."})
        if record.get("from_state") != stored["status"] or record.get("to_state") != self.status:
            raise ValidationError({"transition_history": "Transition entry does not match the state change."})
        for field in ("transition_key", "command", "occurred_at"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValidationError({"transition_history": f"Transition {field} must be non-empty."})

    def clean(self) -> None:
        super().clean()
        self._validate_immutable_fields()
        self._validate_transition_append_only()

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not kwargs.get("raw", False):
            self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ProtectedError(f"{self._meta.label} records cannot be hard-deleted", [self])


class RecoveryPoint(DomainModel):
    """Immutable identity and integrity evidence for a restorable artifact."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    backup_job_id = models.UUIDField()
    backup_archive_id = models.UUIDField(null=True, blank=True)
    adapter_key = models.CharField(max_length=64)
    artifact_locator_ref = models.CharField(max_length=255)
    encryption_key_ref = models.CharField(max_length=255, null=True, blank=True)
    scope_type = models.CharField(max_length=16, choices=ScopeType.choices)
    scope_ref = models.CharField(max_length=255)
    backup_type = models.CharField(max_length=16, choices=BackupType.choices)
    status = models.CharField(
        max_length=16,
        choices=RecoveryPointStatus.choices,
        default=RecoveryPointStatus.DISCOVERED,
    )
    data_cutoff_at = models.DateTimeField()
    captured_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    checksum_algorithm = models.CharField(max_length=16, default="sha256")
    checksum_digest = models.CharField(max_length=64)
    verification_evidence = models.JSONField(default=dict, blank=True)
    latest_verification_evidence = models.ForeignKey(
        "RecoveryPointEvidence",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="current_for_points",
    )
    created_by = models.UUIDField()
    transition_history = models.JSONField(default=list, blank=True)

    _immutable_fields = frozenset(
        {
            "tenant_id",
            "backup_job_id",
            "backup_archive_id",
            "adapter_key",
            "artifact_locator_ref",
            "encryption_key_ref",
            "scope_type",
            "scope_ref",
            "backup_type",
            "data_cutoff_at",
            "captured_at",
            "expires_at",
            "size_bytes",
            "checksum_algorithm",
            "checksum_digest",
            "created_by",
        }
    )

    class Meta:
        app_label = "backup_disaster_recovery"
        db_table = "bdr_recovery_points"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "backup_job_id"], name="bdr_rp_tenant_job_uniq"),
            models.CheckConstraint(
                condition=models.Q(data_cutoff_at__lte=models.F("captured_at")),
                name="bdr_rp_cutoff_lte_capture",
            ),
            models.CheckConstraint(
                condition=models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=models.F("captured_at")),
                name="bdr_rp_expiry_after_capture",
            ),
            models.CheckConstraint(
                condition=models.Q(size_bytes__isnull=True) | models.Q(size_bytes__gte=0),
                name="bdr_rp_size_nonnegative",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "status", "-captured_at"], name="bdr_rp_tenant_status_cap_idx"),
            models.Index(
                fields=["tenant_id", "scope_type", "scope_ref", "-captured_at"],
                name="bdr_rp_tenant_scope_cap_idx",
            ),
            models.Index(fields=["tenant_id", "expires_at"], name="bdr_rp_tenant_expiry_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.adapter_key = _require_non_empty(self.adapter_key, "adapter_key")
        self.artifact_locator_ref = _require_non_empty(self.artifact_locator_ref, "artifact_locator_ref")
        self.scope_ref = _require_non_empty(self.scope_ref, "scope_ref")
        if self.data_cutoff_at and self.captured_at and self.data_cutoff_at > self.captured_at:
            raise ValidationError({"data_cutoff_at": "Must not be later than captured_at."})
        if self.expires_at and self.captured_at and self.expires_at <= self.captured_at:
            raise ValidationError({"expires_at": "Must be later than captured_at."})
        if self.checksum_algorithm != "sha256":
            raise ValidationError({"checksum_algorithm": "Only sha256 is supported."})
        if not _HEX_SHA256.fullmatch(self.checksum_digest):
            raise ValidationError({"checksum_digest": "Must be a lowercase hexadecimal SHA-256 digest."})
        _require_object(self.verification_evidence, "verification_evidence")
        _require_list(self.transition_history, "transition_history")


class DRRunbook(DomainModel):
    """Versioned disaster-recovery procedure."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(max_length=255, default=generate_uuid)
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=120)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=RunbookStatus.choices, default=RunbookStatus.DRAFT)
    description = models.TextField(blank=True)
    scope_type = models.CharField(max_length=16, choices=ScopeType.choices)
    scope_ref = models.CharField(max_length=255)
    backup_schedule_id = models.UUIDField(null=True, blank=True)
    adapter_key = models.CharField(max_length=64)
    rpo_target_seconds = models.PositiveBigIntegerField()
    rto_target_seconds = models.PositiveBigIntegerField()
    owner_id = models.UUIDField()
    supersedes = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="successor_versions",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)
    created_by = models.UUIDField()
    updated_by = models.UUIDField()
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.UUIDField(null=True, blank=True)
    transition_history = models.JSONField(default=list, blank=True)

    _immutable_fields = frozenset({"tenant_id", "idempotency_key"})

    class Meta:
        app_label = "backup_disaster_recovery"
        db_table = "bdr_runbooks"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "idempotency_key"], name="bdr_rb_tenant_idem_uniq"),
            models.UniqueConstraint(fields=["tenant_id", "slug", "version"], name="bdr_rb_tenant_slug_ver_uniq"),
            models.UniqueConstraint(
                fields=["tenant_id", "slug"],
                condition=models.Q(status=RunbookStatus.PUBLISHED, deleted_at__isnull=True),
                name="bdr_rb_one_published_uniq",
            ),
            models.CheckConstraint(condition=models.Q(version__gt=0), name="bdr_rb_version_positive"),
            models.CheckConstraint(condition=models.Q(rpo_target_seconds__gt=0), name="bdr_rb_rpo_positive"),
            models.CheckConstraint(condition=models.Q(rto_target_seconds__gt=0), name="bdr_rb_rto_positive"),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "status", "-updated_at"], name="bdr_rb_tenant_status_upd_idx"),
            models.Index(fields=["tenant_id", "owner_id", "status"], name="bdr_rb_tenant_owner_st_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.idempotency_key = _require_non_empty(self.idempotency_key, "idempotency_key")
        self.name = _require_non_empty(self.name, "name")
        self.slug = _require_non_empty(self.slug, "slug")
        if not _SLUG.fullmatch(self.slug):
            raise ValidationError({"slug": "Use a lowercase tenant-local slug."})
        self.scope_ref = _require_non_empty(self.scope_ref, "scope_ref")
        self.adapter_key = _require_non_empty(self.adapter_key, "adapter_key")
        if self.rpo_target_seconds is not None and self.rpo_target_seconds <= 0:
            raise ValidationError({"rpo_target_seconds": "Must be greater than zero."})
        if self.rto_target_seconds is not None and self.rto_target_seconds <= 0:
            raise ValidationError({"rto_target_seconds": "Must be greater than zero."})
        if self.deleted_at is not None and self.status != RunbookStatus.DRAFT:
            raise ValidationError({"deleted_at": "Only draft runbooks may be soft-deleted."})
        if (self.deleted_at is None) != (self.deleted_by is None):
            raise ValidationError({"deleted_by": "deleted_at and deleted_by must be set together."})
        if self.supersedes_id:
            previous = self.supersedes
            if previous.tenant_id != self.tenant_id:
                raise ValidationError({"supersedes": "The previous version must belong to the same tenant."})
            if previous.slug != self.slug:
                raise ValidationError({"supersedes": "The previous version must use the same slug."})
            if previous.status not in {RunbookStatus.PUBLISHED, RunbookStatus.RETIRED}:
                raise ValidationError({"supersedes": "Only a published or retired version may be superseded."})
        _require_list(self.transition_history, "transition_history")

        stored = self._stored_values([field.attname for field in self._meta.concrete_fields])
        if stored and stored["status"] in {RunbookStatus.PUBLISHED, RunbookStatus.RETIRED}:
            lifecycle_fields = {
                "status",
                "published_at",
                "retired_at",
                "transition_history",
                "updated_at",
                "updated_by",
            }
            changed = {name for name, value in stored.items() if name not in {"id"} and value != getattr(self, name)}
            if changed - lifecycle_fields:
                raise ValidationError("Published and retired runbook versions are immutable; clone a new draft.")
            if stored["status"] == RunbookStatus.RETIRED and changed:
                raise ValidationError("Retired runbook versions are immutable.")


class RunbookStep(DomainModel):
    """Ordered, typed action within a runbook version."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(max_length=255, default=generate_uuid)
    runbook = models.ForeignKey(DRRunbook, on_delete=models.PROTECT, related_name="steps")
    step_key = models.SlugField(max_length=80, db_index=False)
    position = models.PositiveIntegerField()
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    action_type = models.CharField(max_length=32, choices=RunbookActionType.choices)
    extension_action_key = models.CharField(max_length=120, null=True, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    timeout_seconds = models.PositiveIntegerField(default=configured_step_timeout_default)
    retry_limit = models.PositiveSmallIntegerField(default=configured_step_retry_default)
    on_failure = models.CharField(
        max_length=24,
        choices=StepFailureBehavior.choices,
        default=StepFailureBehavior.STOP,
    )
    approval_permission = models.CharField(max_length=255, null=True, blank=True)
    created_by = models.UUIDField()
    updated_by = models.UUIDField()
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.UUIDField(null=True, blank=True)

    _immutable_fields = frozenset({"tenant_id", "idempotency_key"})

    class Meta:
        app_label = "backup_disaster_recovery"
        db_table = "bdr_runbook_steps"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "idempotency_key"], name="bdr_step_tenant_idem_uniq"),
            models.UniqueConstraint(
                fields=["tenant_id", "runbook", "step_key"],
                condition=models.Q(deleted_at__isnull=True),
                name="bdr_step_active_key_uniq",
            ),
            models.UniqueConstraint(
                fields=["tenant_id", "runbook", "position"],
                condition=models.Q(deleted_at__isnull=True),
                name="bdr_step_active_pos_uniq",
            ),
            models.CheckConstraint(condition=models.Q(position__gt=0), name="bdr_step_position_positive"),
            models.CheckConstraint(
                condition=(
                    models.Q(action_type=RunbookActionType.EXTENSION, extension_action_key__isnull=False)
                    & ~models.Q(extension_action_key="")
                    | (~models.Q(action_type=RunbookActionType.EXTENSION) & models.Q(extension_action_key__isnull=True))
                ),
                name="bdr_step_extension_key_shape",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "runbook", "position"], name="bdr_step_tenant_rb_pos_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.idempotency_key = _require_non_empty(self.idempotency_key, "idempotency_key")
        policy = _tenant_policy(self.tenant_id)["steps"]
        self.step_key = _require_non_empty(self.step_key, "step_key")
        self.name = _require_non_empty(self.name, "name")
        if self.runbook_id:
            if self.runbook.tenant_id != self.tenant_id:
                raise ValidationError({"runbook": "The runbook must belong to the same tenant."})
            if policy["require_draft_for_edits"] and (
                self.runbook.status != RunbookStatus.DRAFT or self.runbook.deleted_at is not None
            ):
                raise ValidationError({"runbook": "Steps may only be changed on an active draft runbook."})
        if self.position is not None and self.position < 1:
            raise ValidationError({"position": "Positions are one-based."})
        if self.timeout_seconds is not None and not int(policy["min_timeout_seconds"]) <= self.timeout_seconds <= int(
            policy["max_timeout_seconds"]
        ):
            raise ValidationError({"timeout_seconds": "Outside configured safe limits."})
        if self.retry_limit is not None and not 0 <= self.retry_limit <= int(policy["max_retry_limit"]):
            raise ValidationError({"retry_limit": "Outside configured safe limits."})
        if self.action_type == RunbookActionType.EXTENSION:
            if not self.extension_action_key or not self.extension_action_key.strip():
                raise ValidationError({"extension_action_key": "Required for extension actions."})
        elif self.extension_action_key not in (None, ""):
            raise ValidationError({"extension_action_key": "Allowed only for extension actions."})
        if self.action_type == RunbookActionType.MANUAL_APPROVAL and policy["require_manual_approval_permission"]:
            if not self.approval_permission or not self.approval_permission.strip():
                raise ValidationError({"approval_permission": "Required for manual approval steps."})
        elif self.approval_permission not in (None, ""):
            raise ValidationError({"approval_permission": "Allowed only for manual approval steps."})
        _require_object(self.parameters, "parameters")
        if _contains_unsafe_parameter(self.parameters):
            raise ValidationError({"parameters": "Secrets, URLs, and executable code are forbidden."})
        if (self.deleted_at is None) != (self.deleted_by is None):
            raise ValidationError({"deleted_by": "deleted_at and deleted_by must be set together."})


class DRExercise(DomainModel):
    """Durable execution of an immutable published runbook version."""

    TERMINAL_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {ExerciseStatus.PASSED, ExerciseStatus.FAILED, ExerciseStatus.CANCELLED}
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    runbook = models.ForeignKey(DRRunbook, on_delete=models.PROTECT, related_name="exercises")
    recovery_point = models.ForeignKey(
        RecoveryPoint,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="exercises",
    )
    exercise_type = models.CharField(max_length=16, choices=ExerciseType.choices)
    environment = models.CharField(max_length=16, choices=ExerciseEnvironment.choices)
    status = models.CharField(max_length=16, choices=ExerciseStatus.choices, default=ExerciseStatus.SCHEDULED)
    scheduled_for = models.DateTimeField()
    async_job_id = models.UUIDField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255)
    initiated_by = models.UUIDField()
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    summary = models.TextField(blank=True)
    observed_rpo_seconds = models.PositiveBigIntegerField(null=True, blank=True)
    observed_rto_seconds = models.PositiveBigIntegerField(null=True, blank=True)
    rpo_met = models.BooleanField(null=True, blank=True)
    rto_met = models.BooleanField(null=True, blank=True)
    failed_step_id = models.UUIDField(null=True, blank=True)
    evidence_summary = models.JSONField(default=dict, blank=True)
    transition_history = models.JSONField(default=list, blank=True)

    _immutable_fields = frozenset({"tenant_id", "runbook_id", "idempotency_key", "initiated_by"})

    class Meta:
        app_label = "backup_disaster_recovery"
        db_table = "bdr_exercises"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "idempotency_key"], name="bdr_ex_tenant_idem_uniq"),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=[ExerciseStatus.PASSED, ExerciseStatus.FAILED, ExerciseStatus.CANCELLED],
                        completed_at__isnull=False,
                    )
                    | ~models.Q(status__in=[ExerciseStatus.PASSED, ExerciseStatus.FAILED, ExerciseStatus.CANCELLED])
                ),
                name="bdr_ex_terminal_completed",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "status", "scheduled_for"], name="bdr_ex_tenant_status_sched_idx"),
            models.Index(fields=["tenant_id", "runbook", "-created_at"], name="bdr_ex_tenant_rb_created_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        policy = _tenant_policy(self.tenant_id)["exercises"]
        self.name = _require_non_empty(self.name, "name")
        self.idempotency_key = _require_non_empty(self.idempotency_key, "idempotency_key")
        if self.environment == TargetEnvironment.PRODUCTION and not policy["production_enabled"]:
            raise ValidationError({"environment": "Production exercises are forbidden."})
        if self.runbook_id:
            if self.runbook.tenant_id != self.tenant_id:
                raise ValidationError({"runbook": "The runbook must belong to the same tenant."})
            if self.runbook.status != RunbookStatus.PUBLISHED:
                raise ValidationError({"runbook": "Exercises require a published runbook version."})
        if self.recovery_point_id and self.recovery_point.tenant_id != self.tenant_id:
            raise ValidationError({"recovery_point": "The recovery point must belong to the same tenant."})
        if self.status in self.TERMINAL_STATUSES and self.completed_at is None:
            raise ValidationError({"completed_at": "Terminal exercises require a completion time."})
        _require_object(self.evidence_summary, "evidence_summary")
        _require_list(self.transition_history, "transition_history")

        stored = self._stored_values([field.attname for field in self._meta.concrete_fields])
        if stored and stored["status"] in self.TERMINAL_STATUSES:
            if any(stored[name] != getattr(self, name) for name in stored if name not in {"id", "updated_at"}):
                raise ValidationError("Terminal exercise evidence is immutable.")


class RestoreRun(DomainModel):
    """Governed restore validation, execution, and verification record."""

    ACTIVE_TARGET_STATUSES: ClassVar[tuple[str, ...]] = (
        RestoreRunStatus.VALIDATING,
        RestoreRunStatus.READY,
        RestoreRunStatus.RESTORING,
        RestoreRunStatus.VERIFYING,
    )
    TERMINAL_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {RestoreRunStatus.SUCCEEDED, RestoreRunStatus.FAILED, RestoreRunStatus.CANCELLED}
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recovery_point = models.ForeignKey(RecoveryPoint, on_delete=models.PROTECT, related_name="restore_runs")
    runbook = models.ForeignKey(
        DRRunbook,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="restore_runs",
    )
    exercise = models.ForeignKey(
        DRExercise,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="restore_runs",
    )
    target_environment = models.CharField(max_length=16, choices=TargetEnvironment.choices)
    target_ref = models.CharField(max_length=255)
    restore_mode = models.CharField(max_length=16, choices=RestoreMode.choices)
    selected_components = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=RestoreRunStatus.choices, default=RestoreRunStatus.QUEUED)
    async_job_id = models.UUIDField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255)
    requested_by = models.UUIDField()
    approved_by = models.UUIDField(null=True, blank=True)
    requested_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    validation_evidence = models.JSONField(default=dict, blank=True)
    verification_evidence = models.JSONField(default=dict, blank=True)
    compensation_state = models.CharField(max_length=24, blank=True)
    compensation_evidence = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    achieved_rpo_seconds = models.PositiveBigIntegerField(null=True, blank=True)
    achieved_rto_seconds = models.PositiveBigIntegerField(null=True, blank=True)
    transition_history = models.JSONField(default=list, blank=True)

    _immutable_fields = frozenset(
        {
            "tenant_id",
            "recovery_point_id",
            "runbook_id",
            "exercise_id",
            "target_environment",
            "target_ref",
            "restore_mode",
            "selected_components",
            "idempotency_key",
            "requested_by",
            "approved_by",
            "requested_at",
        }
    )

    class Meta:
        app_label = "backup_disaster_recovery"
        db_table = "bdr_restore_runs"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "idempotency_key"], name="bdr_rr_tenant_idem_uniq"),
            models.UniqueConstraint(
                fields=["tenant_id", "target_ref"],
                condition=models.Q(
                    status__in=(
                        RestoreRunStatus.VALIDATING,
                        RestoreRunStatus.READY,
                        RestoreRunStatus.RESTORING,
                        RestoreRunStatus.VERIFYING,
                    )
                ),
                name="bdr_rr_active_target_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "status", "-requested_at"], name="bdr_rr_tenant_status_req_idx"),
            models.Index(fields=["tenant_id", "recovery_point", "-requested_at"], name="bdr_rr_tenant_rp_req_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        policy = _tenant_policy(self.tenant_id)["restores"]
        self.target_ref = _require_non_empty(self.target_ref, "target_ref")
        self.idempotency_key = _require_non_empty(self.idempotency_key, "idempotency_key")
        if (
            self.target_environment == TargetEnvironment.PRODUCTION
            and policy["production_requires_approver"]
            and self.approved_by is None
        ):
            raise ValidationError({"approved_by": "Production restores require an approver."})
        if self.recovery_point_id and self.recovery_point.tenant_id != self.tenant_id:
            raise ValidationError({"recovery_point": "The recovery point must belong to the same tenant."})
        if self.runbook_id:
            if self.runbook.tenant_id != self.tenant_id:
                raise ValidationError({"runbook": "The runbook must belong to the same tenant."})
            if self.runbook.status != RunbookStatus.PUBLISHED:
                raise ValidationError({"runbook": "Restore runs require a published runbook version."})
        if self.exercise_id and self.exercise.tenant_id != self.tenant_id:
            raise ValidationError({"exercise": "The exercise must belong to the same tenant."})
        _require_list(self.selected_components, "selected_components")
        if (
            self.restore_mode == RestoreMode.SELECTIVE
            and policy["selective_requires_components"]
            and not self.selected_components
        ):
            raise ValidationError({"selected_components": "Selective restores require at least one component."})
        if self.restore_mode == RestoreMode.FULL and policy["full_prohibits_components"] and self.selected_components:
            raise ValidationError({"selected_components": "Full restores do not accept selected components."})
        if len(set(self.selected_components)) != len(self.selected_components) or any(
            not isinstance(item, str) or not _COMPONENT.fullmatch(item) for item in self.selected_components
        ):
            raise ValidationError({"selected_components": "Use unique canonical component names."})
        _require_object(self.validation_evidence, "validation_evidence")
        _require_object(self.verification_evidence, "verification_evidence")
        _require_object(self.compensation_evidence, "compensation_evidence")
        _require_list(self.transition_history, "transition_history")

        stored = self._stored_values([field.attname for field in self._meta.concrete_fields])
        if stored and stored["status"] in self.TERMINAL_STATUSES:
            if any(stored[name] != getattr(self, name) for name in stored if name not in {"id", "updated_at"}):
                raise ValidationError("Terminal restore evidence is immutable.")


class DRStepExecution(DomainModel):
    """Append-only, queryable evidence for one runbook-step attempt."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exercise = models.ForeignKey(DRExercise, on_delete=models.PROTECT, related_name="step_executions")
    runbook_step = models.ForeignKey(RunbookStep, on_delete=models.PROTECT, related_name="executions")
    status = models.CharField(
        max_length=16,
        choices=StepExecutionStatus.choices,
        default=StepExecutionStatus.PENDING,
    )
    attempt = models.PositiveSmallIntegerField(default=1)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    async_job_id = models.UUIDField(null=True, blank=True)
    provider_operation_id = models.CharField(max_length=255, blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    transition_history = models.JSONField(default=list, blank=True)

    _immutable_fields = frozenset({"tenant_id", "exercise_id", "runbook_step_id", "attempt"})
    TERMINAL_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {
            StepExecutionStatus.PASSED,
            StepExecutionStatus.FAILED,
            StepExecutionStatus.DEGRADED,
            StepExecutionStatus.SKIPPED,
        }
    )

    class Meta:
        app_label = "backup_disaster_recovery"
        db_table = "bdr_step_executions"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "exercise", "runbook_step", "attempt"],
                name="bdr_se_attempt_uniq",
            ),
            models.CheckConstraint(condition=models.Q(attempt__gt=0), name="bdr_se_attempt_positive"),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "exercise", "status"], name="bdr_se_tenant_ex_status_idx"),
            models.Index(fields=["tenant_id", "runbook_step", "-created_at"], name="bdr_se_tenant_step_cr_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.attempt is not None and self.attempt < 1:
            raise ValidationError({"attempt": "Attempts are one-based."})
        if self.exercise_id and self.exercise.tenant_id != self.tenant_id:
            raise ValidationError({"exercise": "The exercise must belong to the same tenant."})
        if self.runbook_step_id:
            if self.runbook_step.tenant_id != self.tenant_id:
                raise ValidationError({"runbook_step": "The step must belong to the same tenant."})
            if self.exercise_id and self.runbook_step.runbook_id != self.exercise.runbook_id:
                raise ValidationError({"runbook_step": "The step must belong to the exercise runbook version."})
        _require_object(self.evidence, "evidence")
        _require_list(self.transition_history, "transition_history")

        stored = self._stored_values([field.attname for field in self._meta.concrete_fields])
        if stored and stored["status"] in self.TERMINAL_STATUSES:
            if any(stored[name] != getattr(self, name) for name in stored if name not in {"id", "updated_at"}):
                raise ValidationError("Terminal step-execution evidence is immutable.")


class BDRConfiguration(DomainModel):
    """Tenant-owned, hot-reloadable disaster-recovery policy document."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.CharField(max_length=64, default="default")
    document = models.JSONField(default=dict)
    rollout = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)

    _immutable_fields = frozenset({"tenant_id", "environment"})

    class Meta:
        app_label = "backup_disaster_recovery"
        db_table = "bdr_configurations"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "environment"], name="bdr_cfg_tenant_env_uniq"),
            models.CheckConstraint(condition=models.Q(version__gt=0), name="bdr_cfg_version_positive"),
        ]
        indexes = [models.Index(fields=["tenant_id", "environment"], name="bdr_cfg_tenant_env_idx")]

    def clean(self) -> None:
        super().clean()
        self.environment = _require_non_empty(self.environment, "environment")
        _require_object(self.document, "document")
        _require_object(self.rollout, "rollout")


class BDRConfigurationVersion(DomainModel):
    """Append-only before/after record for every configuration mutation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(BDRConfiguration, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    actor_id = models.UUIDField()
    correlation_id = models.UUIDField(db_index=True)
    prior_value = models.JSONField(default=dict, blank=True)
    new_value = models.JSONField(default=dict)
    rollback_of = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="rollback_versions"
    )

    _immutable_fields = frozenset(
        {
            "tenant_id",
            "configuration_id",
            "version",
            "actor_id",
            "correlation_id",
            "prior_value",
            "new_value",
            "rollback_of_id",
        }
    )

    class Meta:
        app_label = "backup_disaster_recovery"
        db_table = "bdr_configuration_versions"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "configuration", "version"], name="bdr_cfgver_tenant_version_uniq"
            )
        ]
        indexes = [models.Index(fields=["tenant_id", "configuration", "-version"], name="bdr_cfgver_tenant_ver_idx")]

    def clean(self) -> None:
        super().clean()
        if self.configuration_id and self.configuration.tenant_id != self.tenant_id:
            raise ValidationError({"configuration": "Configuration must belong to the same tenant."})
        if self.rollback_of_id and self.rollback_of.tenant_id != self.tenant_id:
            raise ValidationError({"rollback_of": "Rollback target must belong to the same tenant."})
        _require_object(self.prior_value, "prior_value")
        _require_object(self.new_value, "new_value")


class RecoveryPointEvidence(DomainModel):
    """Append-only verification evidence; provider facts are never overwritten."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recovery_point = models.ForeignKey(RecoveryPoint, on_delete=models.PROTECT, related_name="verification_events")
    sequence = models.PositiveIntegerField()
    actor_id = models.UUIDField()
    correlation_id = models.UUIDField(db_index=True)
    evidence = models.JSONField(default=dict)

    _immutable_fields = frozenset(
        {"tenant_id", "recovery_point_id", "sequence", "actor_id", "correlation_id", "evidence"}
    )

    class Meta:
        app_label = "backup_disaster_recovery"
        db_table = "bdr_recovery_point_evidence"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "recovery_point", "sequence"], name="bdr_rpe_tenant_seq_uniq")
        ]
        indexes = [models.Index(fields=["tenant_id", "recovery_point", "-sequence"], name="bdr_rpe_tenant_seq_idx")]

    def clean(self) -> None:
        super().clean()
        if self.recovery_point_id and self.recovery_point.tenant_id != self.tenant_id:
            raise ValidationError({"recovery_point": "Recovery point must belong to the same tenant."})
        _require_object(self.evidence, "evidence")


__all__ = [
    "ActionType",
    "BackupType",
    "BDRConfiguration",
    "BDRConfigurationVersion",
    "DRExercise",
    "DRExerciseStatus",
    "DRRunbook",
    "DRStepExecution",
    "DRStepExecutionStatus",
    "ExerciseEnvironment",
    "ExerciseStatus",
    "ExerciseType",
    "OnFailure",
    "RecoveryPoint",
    "RecoveryPointEvidence",
    "RecoveryPointStatus",
    "RestoreMode",
    "RestoreRun",
    "RestoreRunStatus",
    "RunbookActionType",
    "RunbookStatus",
    "RunbookStep",
    "ScopeType",
    "StepExecutionStatus",
    "StepFailureBehavior",
    "TargetEnvironment",
    "generate_uuid",
    "configured_step_retry_default",
    "configured_step_timeout_default",
]
