"""Transactional domain services for backup capture and catalog ownership."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound

from src.core.api.results import OperationResult
from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue
from src.core.middleware.correlation import get_correlation_id
from src.core.tenancy import tenant_context

from .adapter_registry import capture_adapters
from .adapters.local_filesystem import LocalFilesystemCaptureAdapter
from .metrics import (
    ARTIFACT_EXPIRY,
    BACKUP_DURATION,
    BACKUP_OUTCOMES,
    BACKUP_REQUESTS,
    BACKUP_SIZE,
    PURGE_FAILURES,
    SCHEDULE_LAG,
    VERIFICATION_OUTCOMES,
)
from .models import (
    BackupArchive,
    BackupJob,
    BackupRetentionPolicy,
    BackupSchedule,
    BackupStorageTarget,
    BackupVerification,
)
from .ports import (
    BackupArtifactDescriptor,
    BackupCaptureReceipt,
    BackupCaptureRequest,
    BackupRequestReceipt,
    BackupScheduleSnapshot,
    BackupStatus,
    BackupStatusSnapshot,
    BackupType,
    ProviderPurgeReceipt,
    ScopeType,
)
from .state_machines import JOB_STATE_MACHINE, VERIFICATION_STATE_MACHINE

logger = logging.getLogger("saraise.backup_recovery")


class DomainConflict(APIException):
    status_code = 409
    default_code = "domain_conflict"


@dataclass(frozen=True, slots=True)
class RetentionPreview:
    captured_at: datetime
    archive_at: datetime | None
    expires_at: datetime
    keep_last_successful: int
    retention_days: int
    archive_after_days: int | None


def _uuid(value: uuid.UUID | str, label: str = "identifier") -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValidationError({label: "Must be a valid UUID."}) from exc


def _actor(value: uuid.UUID | str) -> str:
    actor = str(value).strip()
    if not actor or len(actor) > 255:
        raise ValidationError({"actor_id": "Must be a non-empty identifier up to 255 characters."})
    return actor


def _stable_error_code(value: str, fallback: str) -> str:
    candidate = str(value).strip()
    return candidate if re.fullmatch(r"[A-Z0-9][A-Z0-9_.-]{0,63}", candidate) else fallback


def _save(instance: Any) -> Any:
    instance.full_clean()
    instance.save()
    return instance


def _emit_event(tenant_id: uuid.UUID, aggregate_id: uuid.UUID, event_type: str, status: str) -> OutboxEvent:
    """Persist a sanitized versioned domain event in the durable outbox."""

    return OutboxEvent.objects.create(
        tenant_id=tenant_id,
        aggregate_type="backup_recovery",
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload={
            "tenant_id": str(tenant_id),
            "aggregate_id": str(aggregate_id),
            "status": status,
            "correlation_id": get_correlation_id() or str(uuid.uuid4()),
            "event_version": 1,
        },
    )


def _get(model: type[Any], tenant_id: uuid.UUID, object_id: uuid.UUID | str) -> Any:
    try:
        return model.objects.get(tenant_id=tenant_id, pk=_uuid(object_id))
    except model.DoesNotExist as exc:
        raise NotFound() from exc


def _apply_filters(
    queryset: QuerySet[Any], filters: Mapping[str, Any] | None, allowed: Mapping[str, str]
) -> QuerySet[Any]:
    for key, value in (filters or {}).items():
        if key in allowed and value not in (None, ""):
            queryset = queryset.filter(**{allowed[key]: value})
    return queryset


def _adapter_for(target: BackupStorageTarget):
    if target.adapter_key == "local-filesystem":
        return LocalFilesystemCaptureAdapter(target.locator_prefix_ref)
    return capture_adapters.get(target.adapter_key)


class StorageTargetService:
    def create(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, data: Mapping[str, Any]
    ) -> BackupStorageTarget:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            if data.get("is_default"):
                BackupStorageTarget.objects.filter(tenant_id=tenant, is_default=True).update(is_default=False)
            target = BackupStorageTarget(tenant_id=tenant, created_by=_actor(actor_id), **dict(data))
            _save(target)
            return target

    def update(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, target_id: uuid.UUID | str, data: Mapping[str, Any]
    ) -> BackupStorageTarget:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            target = _get(BackupStorageTarget, tenant, target_id)
            if data.get("is_default"):
                BackupStorageTarget.objects.filter(tenant_id=tenant, is_default=True).exclude(pk=target.pk).update(
                    is_default=False
                )
            for field, value in data.items():
                setattr(target, field, value)
            target.updated_by = _actor(actor_id)
            _save(target)
            return target

    def get(self, tenant_id: uuid.UUID | str, target_id: uuid.UUID | str) -> BackupStorageTarget:
        with tenant_context(tenant_id) as tenant:
            return _get(BackupStorageTarget, tenant, target_id)

    def list(
        self, tenant_id: uuid.UUID | str, filters: Mapping[str, Any] | None = None
    ) -> QuerySet[BackupStorageTarget]:
        with tenant_context(tenant_id) as tenant:
            return _apply_filters(
                BackupStorageTarget.objects.filter(tenant_id=tenant),
                filters,
                {"is_active": "is_active", "is_default": "is_default", "adapter_key": "adapter_key"},
            )

    def set_default(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, target_id: uuid.UUID | str
    ) -> BackupStorageTarget:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            target = _get(BackupStorageTarget, tenant, target_id)
            if not target.is_active:
                raise DomainConflict("An inactive storage target cannot be the default.")
            BackupStorageTarget.objects.filter(tenant_id=tenant, is_default=True).update(is_default=False)
            target.is_default = True
            target.updated_by = _actor(actor_id)
            _save(target)
            return target

    def activate(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, target_id: uuid.UUID | str
    ) -> BackupStorageTarget:
        return self.update(tenant_id, actor_id, target_id, {"is_active": True})

    def deactivate(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, target_id: uuid.UUID | str
    ) -> BackupStorageTarget:
        with tenant_context(tenant_id) as tenant:
            target = _get(BackupStorageTarget, tenant, target_id)
            if (
                BackupSchedule.objects.filter(tenant_id=tenant, storage_target=target, is_active=True).exists()
                or BackupJob.objects.filter(
                    tenant_id=tenant, storage_target=target, status__in=("pending", "running")
                ).exists()
            ):
                raise DomainConflict("Storage target is required by active backup work.")
        return self.update(tenant_id, actor_id, target_id, {"is_active": False, "is_default": False})

    def delete(self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, target_id: uuid.UUID | str) -> None:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            target = _get(BackupStorageTarget, tenant, target_id)
            if (
                BackupSchedule.objects.filter(tenant_id=tenant, storage_target=target).exists()
                or BackupJob.objects.filter(
                    tenant_id=tenant, storage_target=target, status__in=("pending", "running")
                ).exists()
            ):
                raise DomainConflict("Storage target is referenced by an active catalog aggregate.")
            target.is_deleted = True
            target.deleted_at = timezone.now()
            target.is_active = False
            target.is_default = False
            target.updated_by = _actor(actor_id)
            target.save(
                update_fields=["is_deleted", "deleted_at", "is_active", "is_default", "updated_by", "updated_at"]
            )

    def probe(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, target_id: uuid.UUID | str
    ) -> OperationResult[Any]:
        del actor_id
        with tenant_context(tenant_id) as tenant:
            target = _get(BackupStorageTarget, tenant, target_id)
            try:
                result = _adapter_for(target).health()
            except Exception:
                logger.warning(
                    "Storage provider probe failed",
                    extra={
                        "tenant_id": str(tenant),
                        "target_id": str(target.id),
                        "adapter_key": target.adapter_key,
                        "operation": "probe",
                    },
                )
                return OperationResult.unavailable(
                    capability=f"backup-capture-adapter:{target.adapter_key}",
                    message="Storage provider probe could not be completed.",
                    evidence={"target_id": str(target.id)},
                    provider=target.adapter_key,
                )
            if not result.healthy:
                return OperationResult.unavailable(
                    capability=f"backup-capture-adapter:{target.adapter_key}",
                    message="Storage provider probe failed.",
                    evidence={"target_id": str(target.id)},
                    provider=target.adapter_key,
                )
            return OperationResult.succeeded(
                result,
                evidence={"target_id": str(target.id), "checked_at": result.checked_at.isoformat()},
                provider=target.adapter_key,
            )


class RetentionPolicyService:
    def create(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, data: Mapping[str, Any]
    ) -> BackupRetentionPolicy:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            return _save(BackupRetentionPolicy(tenant_id=tenant, created_by=_actor(actor_id), **dict(data)))

    def update(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, policy_id: uuid.UUID | str, data: Mapping[str, Any]
    ) -> BackupRetentionPolicy:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            policy = _get(BackupRetentionPolicy, tenant, policy_id)
            for field, value in data.items():
                setattr(policy, field, value)
            policy.updated_by = _actor(actor_id)
            return _save(policy)

    def get(self, tenant_id: uuid.UUID | str, policy_id: uuid.UUID | str) -> BackupRetentionPolicy:
        with tenant_context(tenant_id) as tenant:
            return _get(BackupRetentionPolicy, tenant, policy_id)

    def list(
        self, tenant_id: uuid.UUID | str, filters: Mapping[str, Any] | None = None
    ) -> QuerySet[BackupRetentionPolicy]:
        with tenant_context(tenant_id) as tenant:
            return _apply_filters(
                BackupRetentionPolicy.objects.filter(tenant_id=tenant), filters, {"is_active": "is_active"}
            )

    def activate(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, policy_id: uuid.UUID | str
    ) -> BackupRetentionPolicy:
        return self.update(tenant_id, actor_id, policy_id, {"is_active": True})

    def deactivate(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, policy_id: uuid.UUID | str
    ) -> BackupRetentionPolicy:
        with tenant_context(tenant_id) as tenant:
            policy = _get(BackupRetentionPolicy, tenant, policy_id)
            if (
                BackupSchedule.objects.filter(tenant_id=tenant, retention_policy=policy, is_active=True).exists()
                or BackupJob.objects.filter(
                    tenant_id=tenant, retention_policy=policy, status__in=("pending", "running")
                ).exists()
            ):
                raise DomainConflict("Retention policy is required by active backup work.")
        return self.update(tenant_id, actor_id, policy_id, {"is_active": False})

    def delete(self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, policy_id: uuid.UUID | str) -> None:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            policy = _get(BackupRetentionPolicy, tenant, policy_id)
            if (
                BackupSchedule.objects.filter(tenant_id=tenant, retention_policy=policy).exists()
                or BackupJob.objects.filter(
                    tenant_id=tenant, retention_policy=policy, status__in=("pending", "running")
                ).exists()
            ):
                raise DomainConflict("Retention policy is referenced by an active catalog aggregate.")
            policy.is_deleted = True
            policy.is_active = False
            policy.deleted_at = timezone.now()
            policy.updated_by = _actor(actor_id)
            policy.save(update_fields=["is_deleted", "is_active", "deleted_at", "updated_by", "updated_at"])

    def preview(
        self, tenant_id: uuid.UUID | str, policy_id: uuid.UUID | str, *, captured_at: datetime
    ) -> RetentionPreview:
        policy = self.get(tenant_id, policy_id)
        if timezone.is_naive(captured_at):
            raise ValidationError({"captured_at": "Must include a timezone."})
        return RetentionPreview(
            captured_at=captured_at,
            archive_at=(
                captured_at + timedelta(days=policy.archive_after_days)
                if policy.archive_after_days is not None
                else None
            ),
            expires_at=captured_at + timedelta(days=policy.retention_days),
            keep_last_successful=policy.keep_last_successful,
            retention_days=policy.retention_days,
            archive_after_days=policy.archive_after_days,
        )


class BackupScheduleService:
    def create(self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, data: Mapping[str, Any]) -> BackupSchedule:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            schedule = BackupSchedule(tenant_id=tenant, created_by=_actor(actor_id), **dict(data))
            schedule.next_run_at = self.compute_next_run(schedule, after=timezone.now()) if schedule.is_active else None
            return _save(schedule)

    def update(
        self,
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        schedule_id: uuid.UUID | str,
        data: Mapping[str, Any],
    ) -> BackupSchedule:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            schedule = _get(BackupSchedule, tenant, schedule_id)
            for field, value in data.items():
                setattr(schedule, field, value)
            schedule.updated_by = _actor(actor_id)
            schedule.next_run_at = self.compute_next_run(schedule, after=timezone.now()) if schedule.is_active else None
            return _save(schedule)

    def get(self, tenant_id: uuid.UUID | str, schedule_id: uuid.UUID | str) -> BackupSchedule:
        with tenant_context(tenant_id) as tenant:
            return _get(BackupSchedule, tenant, schedule_id)

    def list(self, tenant_id: uuid.UUID | str, filters: Mapping[str, Any] | None = None) -> QuerySet[BackupSchedule]:
        with tenant_context(tenant_id) as tenant:
            return _apply_filters(
                BackupSchedule.objects.filter(tenant_id=tenant),
                filters,
                {
                    "is_active": "is_active",
                    "frequency": "frequency",
                    "backup_type": "backup_type",
                    "scope_type": "scope_type",
                    "storage_target_id": "storage_target_id",
                },
            )

    def activate(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, schedule_id: uuid.UUID | str
    ) -> BackupSchedule:
        return self.update(tenant_id, actor_id, schedule_id, {"is_active": True})

    def deactivate(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, schedule_id: uuid.UUID | str
    ) -> BackupSchedule:
        return self.update(tenant_id, actor_id, schedule_id, {"is_active": False})

    def delete(self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, schedule_id: uuid.UUID | str) -> None:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            schedule = _get(BackupSchedule, tenant, schedule_id)
            schedule.is_deleted = True
            schedule.is_active = False
            schedule.next_run_at = None
            schedule.deleted_at = timezone.now()
            schedule.updated_by = _actor(actor_id)
            schedule.save(
                update_fields=["is_deleted", "is_active", "next_run_at", "deleted_at", "updated_by", "updated_at"]
            )

    def run_now(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, schedule_id: uuid.UUID | str, idempotency_key: str
    ) -> BackupJob:
        schedule = self.get(tenant_id, schedule_id)
        if not schedule.is_active:
            raise DomainConflict("Inactive schedules cannot run.")
        receipt = BackupRecoveryService().request_backup(
            tenant_id,
            actor_id,
            backup_type=schedule.backup_type,
            scope_type=schedule.scope_type,
            scope_ref=schedule.scope_ref,
            idempotency_key=idempotency_key,
            storage_target_id=schedule.storage_target_id,
            retention_policy_id=schedule.retention_policy_id,
            schedule_id=schedule.id,
            description=f"Run of schedule {schedule.name}",
        )
        return BackupRecoveryService().get_backup_job(tenant_id, receipt.backup_job_id)

    def enqueue_due_schedules(self, tenant_id: uuid.UUID | str, *, now: datetime) -> list[BackupJob]:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            schedules = list(
                BackupSchedule.objects.select_for_update(skip_locked=True)
                .filter(tenant_id=tenant, is_active=True, next_run_at__lte=now)
                .order_by("next_run_at", "id")
            )
            jobs: list[BackupJob] = []
            for schedule in schedules:
                due_at = schedule.next_run_at
                if due_at is None:
                    continue
                SCHEDULE_LAG.observe(max(0.0, (now - due_at).total_seconds()))
                key = f"schedule:{schedule.id}:{due_at.astimezone(datetime_timezone.utc).isoformat()}"
                jobs.append(self.run_now(tenant, "scheduler", schedule.id, key))
                schedule.last_run_at = due_at
                schedule.next_run_at = self.compute_next_run(schedule, after=due_at)
                schedule.updated_by = "scheduler"
                schedule.save(update_fields=["last_run_at", "next_run_at", "updated_by", "updated_at"])
            return jobs

    def compute_next_run(self, schedule: BackupSchedule, *, after: datetime) -> datetime:
        if timezone.is_naive(after):
            raise ValidationError({"after": "Must include a timezone."})
        try:
            zone = ZoneInfo(schedule.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValidationError({"timezone": "Must be a valid IANA timezone."}) from exc
        local_after = after.astimezone(zone)
        if schedule.frequency == "hourly":
            candidate = local_after.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            return candidate.astimezone(datetime_timezone.utc)
        if schedule.schedule_time is None:
            raise ValidationError({"schedule_time": "This frequency requires a time."})
        day = local_after.date()
        for offset in range(0, 400):
            candidate_day = day + timedelta(days=offset)
            if schedule.frequency == "weekly" and candidate_day.weekday() != schedule.day_of_week:
                continue
            if schedule.frequency == "monthly" and candidate_day.day != schedule.day_of_month:
                continue
            candidate = _resolve_local(candidate_day, schedule.schedule_time, zone)
            if candidate > after:
                return candidate.astimezone(datetime_timezone.utc)
        raise ValidationError("Unable to calculate the next scheduled run.")


def _resolve_local(day: Any, local_time: Any, zone: ZoneInfo) -> datetime:
    """Resolve ambiguous time with fold=0; advance through nonexistent minutes."""

    naive = datetime.combine(day, local_time)
    for minute in range(181):
        candidate_naive = naive + timedelta(minutes=minute)
        candidate = candidate_naive.replace(tzinfo=zone, fold=0)
        round_trip = candidate.astimezone(datetime_timezone.utc).astimezone(zone).replace(tzinfo=None)
        if round_trip == candidate_naive:
            return candidate
    raise ValidationError("The local schedule time could not be resolved.")


class BackupRecoveryService:
    def request_backup(
        self,
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        *,
        backup_type: str | BackupType,
        scope_type: str | ScopeType,
        scope_ref: str,
        idempotency_key: str,
        storage_target_id: uuid.UUID | str | None = None,
        retention_policy_id: uuid.UUID | str | None = None,
        schedule_id: uuid.UUID | str | None = None,
        description: str = "",
    ) -> BackupRequestReceipt:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            existing = BackupJob.objects.filter(tenant_id=tenant, idempotency_key=idempotency_key).first()
            normalized_type, normalized_scope = str(getattr(backup_type, "value", backup_type)), str(
                getattr(scope_type, "value", scope_type)
            )
            if existing:
                same_request = (existing.backup_type, existing.scope_type, existing.scope_ref) == (
                    normalized_type,
                    normalized_scope,
                    scope_ref,
                )
                same_request = same_request and (
                    storage_target_id is None or existing.storage_target_id == _uuid(storage_target_id)
                )
                same_request = same_request and existing.retention_policy_id == (
                    _uuid(retention_policy_id) if retention_policy_id is not None else None
                )
                same_request = same_request and existing.schedule_id == (
                    _uuid(schedule_id) if schedule_id is not None else None
                )
                same_request = same_request and existing.description == description
                if not same_request:
                    raise DomainConflict("Idempotency key was already used for a different backup request.")
                return BackupRequestReceipt(existing.id, BackupStatus(existing.status), existing.idempotency_key)
            target = (
                _get(BackupStorageTarget, tenant, storage_target_id)
                if storage_target_id
                else BackupStorageTarget.objects.filter(tenant_id=tenant, is_active=True, is_default=True).first()
            )
            if target is None or not target.is_active:
                raise DomainConflict("An active storage target is required.")
            # Fail before durable acceptance when no provider capability can
            # execute this target. A queued job must never be left pending
            # behind a worker command that cannot be claimed.
            _adapter_for(target)
            policy = _get(BackupRetentionPolicy, tenant, retention_policy_id) if retention_policy_id else None
            schedule = _get(BackupSchedule, tenant, schedule_id) if schedule_id else None
            base_job = None
            if normalized_type in ("incremental", "differential"):
                baselines = BackupJob.objects.filter(
                    tenant_id=tenant,
                    status="completed",
                    scope_type=normalized_scope,
                    scope_ref=scope_ref,
                    storage_target=target,
                    archive__lifecycle="available",
                )
                # Differential backups are always measured against a full
                # baseline. Incrementals may extend a healthy incremental
                # chain, but never an expired/purged or cross-target artifact.
                if normalized_type == "differential":
                    baselines = baselines.filter(backup_type="full")
                else:
                    baselines = baselines.filter(backup_type__in=("full", "incremental"))
                base_job = baselines.order_by("-completed_at", "-requested_at").first()
                if base_job is None:
                    raise DomainConflict("Incremental and differential backups require a completed baseline.")
            job = BackupJob(
                tenant_id=tenant,
                created_by=_actor(actor_id),
                storage_target=target,
                retention_policy=policy,
                schedule=schedule,
                backup_type=normalized_type,
                scope_type=normalized_scope,
                scope_ref=scope_ref,
                idempotency_key=idempotency_key,
                description=description,
                status="pending",
                base_job=base_job,
            )
            _save(job)
            async_job = enqueue(
                tenant,
                actor_id,
                "backup_recovery.capture",
                {"tenant_id": str(tenant), "job_id": str(job.id)},
                f"capture:{idempotency_key}",
            )
            job.async_job_id = async_job.id
            job.save(update_fields=["async_job_id", "updated_at"])
            _emit_event(tenant, job.id, "backup_recovery.job.requested.v1", job.status)
            BACKUP_REQUESTS.labels(backup_type=normalized_type, scope_type=normalized_scope).inc()
            return BackupRequestReceipt(job.id, BackupStatus.PENDING, idempotency_key)

    def get_backup_job(self, tenant_id: uuid.UUID | str, job_id: uuid.UUID | str) -> BackupJob:
        with tenant_context(tenant_id) as tenant:
            return _get(BackupJob, tenant, job_id)

    def list_backup_jobs(
        self, tenant_id: uuid.UUID | str, filters: Mapping[str, Any] | None = None
    ) -> QuerySet[BackupJob]:
        with tenant_context(tenant_id) as tenant:
            return _apply_filters(
                BackupJob.objects.filter(tenant_id=tenant),
                filters,
                {
                    "status": "status",
                    "backup_type": "backup_type",
                    "schedule_id": "schedule_id",
                    "scope_type": "scope_type",
                    "scope_ref": "scope_ref",
                    "requested_after": "requested_at__gte",
                    "requested_before": "requested_at__lte",
                },
            )

    def update_job_description(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, job_id: uuid.UUID | str, description: str
    ) -> BackupJob:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            job = _get(BackupJob, tenant, job_id)
            if job.status != "pending":
                raise DomainConflict("Only pending job descriptions may be edited.")
            job.description, job.updated_by = description, _actor(actor_id)
            job.full_clean()
            job.save(update_fields=["description", "updated_by", "updated_at"])
            return job

    def cancel_backup(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, job_id: uuid.UUID | str, transition_key: str
    ) -> BackupJob:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            job = _get(BackupJob, tenant, job_id)
            if job.status == "running":
                receipt = _adapter_for(job.storage_target).cancel(
                    str(job.async_job_id or job.id), idempotency_key=transition_key
                )
                if not receipt.acknowledged:
                    raise DomainConflict("The provider did not acknowledge cancellation.")
            JOB_STATE_MACHINE.apply(
                job,
                "cancel",
                transition_key=transition_key,
                tenant_id=tenant,
                context={"adapter_acknowledged": True, "before_commit": job.status == "pending"},
                metadata={"actor_id": _actor(actor_id)},
            )
            _emit_event(tenant, job.id, "backup_recovery.job.cancelled.v1", "cancelled")
            BACKUP_OUTCOMES.labels(status="cancelled", adapter_key=job.storage_target.adapter_key, error_code="").inc()
            return job

    def retry_backup(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, job_id: uuid.UUID | str, idempotency_key: str
    ) -> BackupRequestReceipt:
        source = self.get_backup_job(tenant_id, job_id)
        if source.status not in ("failed", "cancelled"):
            raise DomainConflict("Only failed or cancelled jobs can be retried.")
        receipt = self.request_backup(
            tenant_id,
            actor_id,
            backup_type=source.backup_type,
            scope_type=source.scope_type,
            scope_ref=source.scope_ref,
            idempotency_key=idempotency_key,
            storage_target_id=source.storage_target_id,
            retention_policy_id=source.retention_policy_id,
            schedule_id=source.schedule_id,
            description=source.description,
        )
        with tenant_context(tenant_id) as tenant:
            BackupJob.objects.filter(tenant_id=tenant, pk=receipt.backup_job_id).update(retry_of=source)
        return receipt

    def soft_delete_job(self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, job_id: uuid.UUID | str) -> None:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            job = _get(BackupJob, tenant, job_id)
            if job.status in ("pending", "running"):
                job = self.cancel_backup(tenant, actor_id, job.id, f"delete:{job.id}")
            job.is_deleted, job.deleted_at, job.updated_by = True, timezone.now(), _actor(actor_id)
            job.save(update_fields=["is_deleted", "deleted_at", "updated_by", "updated_at"])

    def get_backup_status(self, tenant_id: uuid.UUID | str, backup_job_id: uuid.UUID | str) -> BackupStatusSnapshot:
        job = self.get_backup_job(tenant_id, backup_job_id)
        return BackupStatusSnapshot(job.id, BackupStatus(job.status), job.completed_at, job.error_code)

    def describe_completed_artifact(
        self, tenant_id: uuid.UUID | str, backup_job_id: uuid.UUID | str
    ) -> BackupArtifactDescriptor:
        job = self.get_backup_job(tenant_id, backup_job_id)
        try:
            archive = job.archive
        except BackupArchive.DoesNotExist as exc:
            raise DomainConflict("Completed artifact evidence is unavailable.") from exc
        if job.status != "completed":
            raise DomainConflict("Backup job is not completed.")
        if (
            not archive.adapter_key
            or archive.size_bytes is None
            or archive.checksum_algorithm != "sha256"
            or not archive.checksum_digest
            or len(archive.checksum_digest) != 64
            or any(character not in "0123456789abcdef" for character in archive.checksum_digest)
            or not archive.provider_acknowledgement
            or archive.data_cutoff_at is None
            or archive.captured_at is None
        ):
            raise DomainConflict("Completed artifact lacks provider-verifiable evidence.")
        return BackupArtifactDescriptor(
            job.id,
            archive.id,
            archive.adapter_key,
            archive.artifact_locator_ref,
            archive.encryption_key_ref or None,
            ScopeType(job.scope_type),
            job.scope_ref,
            BackupType(job.backup_type),
            archive.data_cutoff_at,
            archive.captured_at,
            archive.expires_at,
            archive.size_bytes,
            archive.checksum_algorithm,
            archive.checksum_digest,
            archive.provider_acknowledgement,
        )

    def validate_schedule(
        self, tenant_id: uuid.UUID | str, backup_schedule_id: uuid.UUID | str
    ) -> BackupScheduleSnapshot:
        schedule = BackupScheduleService().get(tenant_id, backup_schedule_id)
        schedule.full_clean()
        return BackupScheduleSnapshot(
            schedule.id, schedule.is_active, BackupType(schedule.backup_type), schedule.frequency
        )

    def claim_backup(self, tenant_id: uuid.UUID | str, job_id: uuid.UUID | str, transition_key: str) -> BackupJob:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            job = BackupJob.objects.select_for_update().get(tenant_id=tenant, pk=_uuid(job_id))
            if job.status == "running":
                return job
            _adapter_for(job.storage_target)
            JOB_STATE_MACHINE.apply(
                job,
                "start",
                transition_key=transition_key,
                tenant_id=tenant,
                context={"async_job_claimed": True, "adapter_available": True},
            )
            job.started_at = timezone.now()
            job.save(update_fields=["started_at", "updated_at"])
            _emit_event(tenant, job.id, "backup_recovery.job.started.v1", "running")
            return job

    def execute_backup(self, tenant_id: uuid.UUID | str, job_id: uuid.UUID | str) -> BackupJob:
        job = self.get_backup_job(tenant_id, job_id)
        if job.status in ("completed", "failed", "cancelled"):
            return job
        self.claim_backup(tenant_id, job_id, f"worker:start:{job.async_job_id or job.id}")
        job = self.get_backup_job(tenant_id, job_id)
        request = BackupCaptureRequest(
            operation_id=job.async_job_id or job.id,
            tenant_id=job.tenant_id,
            backup_job_id=job.id,
            backup_type=BackupType(job.backup_type),
            scope_type=ScopeType(job.scope_type),
            scope_ref=job.scope_ref,
            locator_prefix_ref=job.storage_target.locator_prefix_ref,
            encryption_key_ref=job.storage_target.encryption_key_ref,
        )
        try:
            receipt = _adapter_for(job.storage_target).capture(request)
            return self.record_backup_completed(tenant_id, job_id, receipt)
        except Exception as exc:
            logger.error(
                "Backup provider execution failed",
                extra={
                    "tenant_id": str(job.tenant_id),
                    "job_id": str(job.id),
                    "operation": "capture",
                    "error_code": "PROVIDER_FAILURE",
                },
            )
            return self.record_backup_failed(tenant_id, job_id, "PROVIDER_FAILURE", type(exc).__name__)

    def record_backup_completed(
        self, tenant_id: uuid.UUID | str, job_id: uuid.UUID | str, provider_receipt: BackupCaptureReceipt
    ) -> BackupJob:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            job = BackupJob.objects.select_for_update().get(tenant_id=tenant, pk=_uuid(job_id))
            if job.status == "completed":
                return job
            if (
                not provider_receipt.accepted
                or not provider_receipt.completed
                or str(provider_receipt.operation_id) != str(job.async_job_id or job.id)
                or provider_receipt.size_bytes < 0
                or provider_receipt.checksum_algorithm != "sha256"
                or len(provider_receipt.checksum_digest) != 64
                or any(character not in "0123456789abcdef" for character in provider_receipt.checksum_digest)
                or not provider_receipt.artifact_locator_ref
                or not provider_receipt.provider_acknowledgement
                or timezone.is_naive(provider_receipt.data_cutoff_at)
                or timezone.is_naive(provider_receipt.captured_at)
                or provider_receipt.data_cutoff_at > provider_receipt.captured_at
            ):
                raise DomainConflict("Provider receipt does not prove durable completion.")
            expires_at = (
                provider_receipt.captured_at + timedelta(days=job.retention_policy.retention_days)
                if job.retention_policy
                else None
            )
            # Persist the provider's durable evidence before the archive.  The
            # archive model deliberately refuses to reference a job that has no
            # completion evidence, while the state transition deliberately
            # refuses to complete a job until its archive exists.
            job.data_cutoff_at, job.size_bytes, job.completed_at = (
                provider_receipt.data_cutoff_at,
                provider_receipt.size_bytes,
                timezone.now(),
            )
            job.save(update_fields=["data_cutoff_at", "size_bytes", "completed_at", "updated_at"])
            archive = BackupArchive(
                tenant_id=tenant,
                created_by="worker",
                backup_job=job,
                lifecycle="available",
                adapter_key=job.storage_target.adapter_key,
                artifact_locator_ref=provider_receipt.artifact_locator_ref,
                encryption_key_ref=job.storage_target.encryption_key_ref,
                size_bytes=provider_receipt.size_bytes,
                checksum_algorithm=provider_receipt.checksum_algorithm,
                checksum_digest=provider_receipt.checksum_digest,
                provider_acknowledgement=provider_receipt.provider_acknowledgement,
                data_cutoff_at=provider_receipt.data_cutoff_at,
                captured_at=provider_receipt.captured_at,
                expires_at=expires_at,
            )
            _save(archive)
            JOB_STATE_MACHINE.apply(
                job,
                "complete",
                transition_key=f"provider:{provider_receipt.operation_id}",
                tenant_id=tenant,
                context={"provider_receipt_valid": True, "artifact_persisted": True},
                metadata={"archive_id": str(archive.id)},
            )
            _emit_event(tenant, job.id, "backup_recovery.job.completed.v1", "completed")
            BACKUP_OUTCOMES.labels(status="completed", adapter_key=job.storage_target.adapter_key, error_code="").inc()
            BACKUP_SIZE.labels(adapter_key=job.storage_target.adapter_key, backup_type=job.backup_type).observe(
                job.size_bytes
            )
            if job.started_at and job.completed_at:
                BACKUP_DURATION.labels(adapter_key=job.storage_target.adapter_key, backup_type=job.backup_type).observe(
                    max(0.0, (job.completed_at - job.started_at).total_seconds())
                )
            return job

    def record_backup_failed(
        self, tenant_id: uuid.UUID | str, job_id: uuid.UUID | str, error_code: str, error_message: str
    ) -> BackupJob:
        if not error_code.strip():
            raise ValidationError({"error_code": "A stable error code is required."})
        stable_code = _stable_error_code(error_code, "PROVIDER_FAILURE")
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            job = BackupJob.objects.select_for_update().get(tenant_id=tenant, pk=_uuid(job_id))
            if job.status == "failed":
                return job
            job.error_code, job.error_message, job.completed_at = stable_code, error_message[:2000], timezone.now()
            job.save(update_fields=["error_code", "error_message", "completed_at", "updated_at"])
            JOB_STATE_MACHINE.apply(
                job,
                "fail",
                transition_key=f"failure:{job.async_job_id or job.id}",
                tenant_id=tenant,
                context={"error_code": stable_code},
            )
            _emit_event(tenant, job.id, "backup_recovery.job.failed.v1", "failed")
            BACKUP_OUTCOMES.labels(
                status="failed", adapter_key=job.storage_target.adapter_key, error_code=stable_code
            ).inc()
            return job


class BackupArtifactService:
    def get(self, tenant_id: uuid.UUID | str, archive_id: uuid.UUID | str) -> BackupArchive:
        with tenant_context(tenant_id) as tenant:
            return _get(BackupArchive, tenant, archive_id)

    def list(self, tenant_id: uuid.UUID | str, filters: Mapping[str, Any] | None = None) -> QuerySet[BackupArchive]:
        with tenant_context(tenant_id) as tenant:
            return _apply_filters(
                BackupArchive.objects.filter(tenant_id=tenant),
                filters,
                {
                    "lifecycle": "lifecycle",
                    "integrity_status": "integrity_status",
                    "backup_job_id": "backup_job_id",
                    "expires_before": "expires_at__lte",
                    "captured_after": "captured_at__gte",
                },
            )

    def request_verification(
        self, tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, archive_id: uuid.UUID | str, idempotency_key: str
    ) -> BackupVerification:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            existing = BackupVerification.objects.filter(tenant_id=tenant, idempotency_key=idempotency_key).first()
            if existing:
                if existing.archive_id != _uuid(archive_id):
                    raise DomainConflict("Idempotency key was already used for a different artifact.")
                return existing
            archive = _get(BackupArchive, tenant, archive_id)
            if archive.lifecycle != "available":
                raise DomainConflict("Only available artifacts can be verified.")
            verification = _save(
                BackupVerification(
                    tenant_id=tenant, created_by=_actor(actor_id), archive=archive, idempotency_key=idempotency_key
                )
            )
            async_job = enqueue(
                tenant,
                actor_id,
                "backup_recovery.verify",
                {"tenant_id": str(tenant), "verification_id": str(verification.id)},
                f"verify:{idempotency_key}",
            )
            verification.async_job_id = async_job.id
            verification.save(update_fields=["async_job_id", "updated_at"])
            return verification

    def execute_verification(self, tenant_id: uuid.UUID | str, verification_id: uuid.UUID | str) -> BackupVerification:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            verification = (
                BackupVerification.objects.select_for_update()
                .select_related("archive__backup_job")
                .get(tenant_id=tenant, pk=_uuid(verification_id))
            )
            if verification.status in ("passed", "failed", "cancelled"):
                return verification
            VERIFICATION_STATE_MACHINE.apply(
                verification, "start", transition_key=f"worker:start:{verification.id}", tenant_id=tenant
            )
            verification.started_at = timezone.now()
            verification.save(update_fields=["started_at", "updated_at"])
            archive = verification.archive
            archive.integrity_status = "verifying"
            archive.save(update_fields=["integrity_status", "updated_at"])
        descriptor = BackupRecoveryService().describe_completed_artifact(tenant_id, verification.archive.backup_job_id)
        try:
            receipt = _adapter_for(verification.archive.backup_job.storage_target).verify(
                descriptor, idempotency_key=str(verification.id)
            )
        except Exception as exc:
            with tenant_context(tenant_id) as tenant, transaction.atomic():
                verification = (
                    BackupVerification.objects.select_for_update()
                    .select_related("archive")
                    .get(tenant_id=tenant, pk=verification.id)
                )
                verification.completed_at = timezone.now()
                verification.error_code = "PROVIDER_FAILURE"
                verification.error_message = type(exc).__name__
                verification.save(update_fields=["completed_at", "error_code", "error_message", "updated_at"])
                VERIFICATION_STATE_MACHINE.apply(
                    verification,
                    "fail",
                    transition_key=f"provider-failure:{verification.id}",
                    tenant_id=tenant,
                )
                archive = verification.archive
                archive.integrity_status = "unknown"
                archive.save(update_fields=["integrity_status", "updated_at"])
                _emit_event(
                    tenant,
                    verification.id,
                    "backup_recovery.verification.completed.v1",
                    verification.status,
                )
                VERIFICATION_OUTCOMES.labels(status="failed", adapter_key=archive.adapter_key).inc()
                return verification
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            verification = BackupVerification.objects.select_for_update().get(tenant_id=tenant, pk=verification.id)
            verification.checksum_matches = receipt.checksum_matches
            verification.artifact_available = receipt.artifact_available
            verification.encryption_metadata_valid = receipt.encryption_metadata_valid
            verification.provider_acknowledged = receipt.provider_acknowledged
            verification.evidence = dict(receipt.evidence)
            verification.completed_at = timezone.now()
            operation_matches = str(receipt.operation_id) == str(verification.id)
            passed = operation_matches and all(
                (
                    receipt.checksum_matches,
                    receipt.artifact_available,
                    receipt.encryption_metadata_valid,
                    receipt.provider_acknowledged,
                )
            )
            if not passed:
                verification.error_code = _stable_error_code(
                    (
                        "RECEIPT_OPERATION_MISMATCH"
                        if not operation_matches
                        else receipt.error_code or "VERIFICATION_FAILED"
                    ),
                    "VERIFICATION_FAILED",
                )
                verification.error_message = "Artifact integrity verification failed."
            verification.save()
            VERIFICATION_STATE_MACHINE.apply(
                verification,
                "pass" if passed else "fail",
                transition_key=(
                    f"provider:{receipt.operation_id}" if operation_matches else f"receipt-mismatch:{verification.id}"
                ),
                tenant_id=tenant,
            )
            archive = verification.archive
            archive.integrity_status = "verified" if passed else "corrupt"
            archive.last_verified_at = verification.completed_at
            archive.save(update_fields=["integrity_status", "last_verified_at", "updated_at"])
            _emit_event(tenant, verification.id, "backup_recovery.verification.completed.v1", verification.status)
            VERIFICATION_OUTCOMES.labels(status=verification.status, adapter_key=archive.adapter_key).inc()
            return verification

    def cancel_verification(
        self,
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        verification_id: uuid.UUID | str,
        transition_key: str,
    ) -> BackupVerification:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            verification = _get(BackupVerification, tenant, verification_id)
            VERIFICATION_STATE_MACHINE.apply(
                verification,
                "cancel",
                transition_key=transition_key,
                tenant_id=tenant,
                metadata={"actor_id": _actor(actor_id)},
            )
            archive = verification.archive
            if (
                not BackupVerification.objects.filter(
                    tenant_id=tenant,
                    archive=archive,
                    status__in=("pending", "running"),
                )
                .exclude(pk=verification.pk)
                .exists()
            ):
                archive.integrity_status = "verified" if archive.last_verified_at else "unknown"
                archive.save(update_fields=["integrity_status", "updated_at"])
            return verification

    def expire_due_artifacts(self, tenant_id: uuid.UUID | str, *, now: datetime) -> list[BackupArchive]:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            due_archives = list(
                BackupArchive.objects.select_for_update(skip_locked=True)
                .filter(tenant_id=tenant, lifecycle="available", expires_at__lte=now)
                .select_related("backup_job__retention_policy")
            )
            protected_ids: set[uuid.UUID] = set()
            policy_ids = {
                archive.backup_job.retention_policy_id
                for archive in due_archives
                if archive.backup_job.retention_policy_id is not None
            }
            for policy_id in policy_ids:
                policy = BackupRetentionPolicy.all_with_deleted.get(tenant_id=tenant, pk=policy_id)
                protected_ids.update(
                    BackupArchive.objects.filter(
                        tenant_id=tenant,
                        lifecycle="available",
                        backup_job__retention_policy_id=policy_id,
                        backup_job__status="completed",
                    )
                    .order_by("-captured_at", "-id")
                    .values_list("id", flat=True)[: policy.keep_last_successful]
                )
            archives = [archive for archive in due_archives if archive.id not in protected_ids]
            for archive in archives:
                archive.lifecycle = "expired"
                archive.save(update_fields=["lifecycle", "updated_at"])
                _emit_event(tenant, archive.id, "backup_recovery.artifact.expired.v1", "expired")
                ARTIFACT_EXPIRY.inc()
            return archives

    def request_purge(self, tenant_id: uuid.UUID | str, archive_id: uuid.UUID | str, idempotency_key: str) -> AsyncJob:
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            archive = BackupArchive.objects.select_for_update().get(tenant_id=tenant, pk=_uuid(archive_id))
            if archive.lifecycle != "expired":
                raise DomainConflict("Only expired artifacts can be purged.")
            if archive.purge_async_job_id:
                if archive.purge_idempotency_key != idempotency_key:
                    raise DomainConflict("An artifact purge is already registered with another idempotency key.")
                return AsyncJob.objects.get(tenant_id=tenant, pk=archive.purge_async_job_id)
            async_job = enqueue(
                tenant,
                "retention-worker",
                "backup_recovery.retention",
                {"tenant_id": str(tenant), "archive_id": str(archive.id)},
                f"purge:{idempotency_key}",
            )
            archive.purge_async_job_id = async_job.id
            archive.purge_idempotency_key = idempotency_key
            archive.purge_attempt_count += 1
            archive.last_purge_attempt_at = timezone.now()
            archive.purge_error_code = ""
            archive.save(
                update_fields=[
                    "purge_async_job_id",
                    "purge_idempotency_key",
                    "purge_attempt_count",
                    "last_purge_attempt_at",
                    "purge_error_code",
                    "updated_at",
                ]
            )
            return async_job

    def record_purge_completed(
        self, tenant_id: uuid.UUID | str, archive_id: uuid.UUID | str, provider_receipt: ProviderPurgeReceipt
    ) -> BackupArchive:
        if (
            not provider_receipt.acknowledged
            or provider_receipt.purged_at is None
            or timezone.is_naive(provider_receipt.purged_at)
        ):
            raise DomainConflict("Provider receipt does not acknowledge purge.")
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            archive = BackupArchive.objects.select_for_update().get(tenant_id=tenant, pk=_uuid(archive_id))
            if archive.lifecycle == "purged" and archive.purged_at is not None:
                return archive
            if archive.purge_async_job_id and str(provider_receipt.operation_id) != str(archive.purge_async_job_id):
                raise DomainConflict("Provider purge receipt belongs to another operation.")
            archive.lifecycle, archive.purged_at, archive.purge_error_code = (
                "purged",
                provider_receipt.purged_at,
                "",
            )
            archive.save(update_fields=["lifecycle", "purged_at", "purge_error_code", "updated_at"])
            _emit_event(tenant, archive.id, "backup_recovery.artifact.purged.v1", "purged")
            return archive

    def record_purge_failed(
        self, tenant_id: uuid.UUID | str, archive_id: uuid.UUID | str, error_code: str
    ) -> BackupArchive:
        if not error_code:
            raise ValidationError({"error_code": "A stable error code is required."})
        stable_code = _stable_error_code(error_code, "PROVIDER_PURGE_FAILED")
        with tenant_context(tenant_id) as tenant, transaction.atomic():
            archive = BackupArchive.objects.select_for_update().get(tenant_id=tenant, pk=_uuid(archive_id))
            archive.purge_error_code = stable_code
            archive.last_purge_attempt_at = timezone.now()
            archive.save(update_fields=["purge_error_code", "last_purge_attempt_at", "updated_at"])
            _emit_event(tenant, archive.id, "backup_recovery.artifact.purge_failed.v1", "expired")
            PURGE_FAILURES.labels(adapter_key=archive.adapter_key, error_code=stable_code).inc()
            logger.error(
                "Artifact purge failed",
                extra={
                    "tenant_id": str(archive.tenant_id),
                    "archive_id": str(archive.id),
                    "error_code": stable_code,
                    "operation": "purge",
                },
            )
            return archive
