"""Persistence models for durable asynchronous work.

The job row and its outbox event are deliberately separate records: the former
is the durable execution state, while the latter is the recoverable request to
publish that work to a broker. Services create both in one database transaction.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from django.db import models
from django.utils import timezone

if TYPE_CHECKING:

    class TenantScopedModel(models.Model):
        """Static shape of the canonical tenant ownership base."""

        tenant_id: models.UUIDField[uuid.UUID, uuid.UUID]
        objects = models.Manager["TenantScopedModel"]()  # type: ignore[django-manager-missing]

        class Meta:
            abstract = True

    class TimestampedModel(models.Model):
        """Static shape of the canonical timestamp mixin."""

        created_at: models.DateTimeField[Any, Any]
        updated_at: models.DateTimeField[Any, Any]

        class Meta:
            abstract = True

else:
    try:
        # Supplied by the parallel foundation-tenancy-base unit in integrated builds.
        from src.core.tenancy import TenantScopedModel, TimestampedModel
    except ModuleNotFoundError as exc:
        if exc.name not in {"src.core.tenancy", "src.core.tenancy.models"}:
            raise

        class TenantQuerySet(models.QuerySet[models.Model]):
            """Standalone equivalent of the canonical tenant query boundary."""

            def for_tenant(self, tenant_id: uuid.UUID) -> "TenantQuerySet":
                """Restrict a query to exactly one tenant."""
                return self.filter(tenant_id=tenant_id)

        class TenantScopedModel(models.Model):
            """Compatibility base used until the parallel tenancy unit is merged."""

            tenant_id = models.UUIDField(db_index=True)
            objects = TenantQuerySet.as_manager()

            class Meta:
                abstract = True

        class TimestampedModel(models.Model):
            """Compatibility timestamp mixin matching the canonical foundation."""

            created_at = models.DateTimeField(auto_now_add=True)
            updated_at = models.DateTimeField(auto_now=True)

            class Meta:
                abstract = True


class JobStatus(models.TextChoices):
    """Lifecycle states for an asynchronous job."""

    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    TIMED_OUT = "timed_out", "Timed out"
    RETRYING = "retrying", "Retrying"


class OutboxStatus(models.TextChoices):
    """Delivery states for an outbox event."""

    PENDING = "pending", "Pending"
    DISPATCHING = "dispatching", "Dispatching"
    DISPATCHED = "dispatched", "Dispatched"


class ImmutableTransitionError(RuntimeError):
    """Raised when append-only transition history is mutated."""


class AppendOnlyTransitionQuerySet(models.QuerySet["JobTransition"]):
    """Prevent bulk mutation of the job transition audit trail."""

    def for_tenant(self, tenant_id: uuid.UUID) -> "AppendOnlyTransitionQuerySet":
        """Retain the canonical explicit tenant boundary on the narrowed manager."""

        return self.filter(tenant_id=tenant_id)

    def update(self, **kwargs: Any) -> int:
        raise ImmutableTransitionError("JobTransition records are append-only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableTransitionError("JobTransition records are append-only")


class AsyncJob(TenantScopedModel, TimestampedModel):
    """A durable, idempotently enqueued command."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_id = models.CharField(max_length=255, db_index=True)
    command = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.QUEUED, db_index=True)
    idempotency_key = models.CharField(max_length=255)
    payload = models.JSONField(default=dict)
    result = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)
    correlation_id = models.CharField(max_length=64, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "async_jobs"
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"),
                name="asyncjob_tenant_idem_uniq",
            )
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "created_at"), name="asyncjob_tenant_status_idx"),
            models.Index(fields=("tenant_id", "command", "created_at"), name="asyncjob_tenant_cmd_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.command} [{self.status}] ({self.id})"


class JobTransition(TenantScopedModel):
    """An immutable record of one guarded job state transition."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(AsyncJob, on_delete=models.PROTECT, related_name="transitions")
    from_status = models.CharField(max_length=20, choices=JobStatus.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=JobStatus.choices)
    actor_id = models.CharField(max_length=255, null=True, blank=True)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Django manager generics are invariant; this deliberate narrowing gives
    # transition history stronger mutation guarantees than the tenant base.
    objects = AppendOnlyTransitionQuerySet.as_manager()  # type: ignore[assignment,misc]

    class Meta:
        db_table = "async_job_transitions"
        ordering = ("created_at", "id")
        indexes = [
            models.Index(fields=("tenant_id", "job", "created_at"), name="jobtrans_tenant_job_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableTransitionError("JobTransition records are append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableTransitionError("JobTransition records are append-only")

    def __str__(self) -> str:
        source = self.from_status or "created"
        return f"{self.job_id}: {source} -> {self.to_status}"


class OutboxEvent(TenantScopedModel, TimestampedModel):
    """A broker publication request stored in the same transaction as its job."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aggregate_type = models.CharField(max_length=100)
    aggregate_id = models.UUIDField(db_index=True)
    event_type = models.CharField(max_length=255, db_index=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20,
        choices=OutboxStatus.choices,
        default=OutboxStatus.PENDING,
        db_index=True,
    )
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    claim_token = models.UUIDField(null=True, blank=True, editable=False)
    claimed_until = models.DateTimeField(null=True, blank=True)
    broker_message_id = models.CharField(max_length=255, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "async_job_outbox_events"
        ordering = ("created_at", "id")
        indexes = [
            models.Index(fields=("status", "available_at", "created_at"), name="outbox_pending_idx"),
            models.Index(fields=("tenant_id", "aggregate_type", "aggregate_id"), name="outbox_tenant_agg_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} [{self.status}] ({self.id})"
