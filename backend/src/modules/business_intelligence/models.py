"""Persistent, tenant-isolated Business Intelligence domain models.

Dataset schemas intentionally are not persisted here: the typed registry is the
cross-module contract.  Persisted definitions refer to a stable ``dataset_key``
and services revalidate that key before publication and execution.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from src.core.async_jobs.models import AsyncJob
from src.core.tenancy import TenantScopedModel, TimestampedModel

from .querysets import BIQuerySet, ExecutionQuerySet, ShareQuerySet


class LifecycleState(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class ReportType(models.TextChoices):
    TABLE = "table", "Table"
    PIVOT = "pivot", "Pivot"
    CHART = "chart", "Chart"
    KPI = "kpi", "KPI"


class WidgetType(models.TextChoices):
    KPI = "kpi", "KPI"
    TABLE = "table", "Table"
    BAR = "bar", "Bar"
    LINE = "line", "Line"
    AREA = "area", "Area"
    PIE = "pie", "Pie"
    FUNNEL = "funnel", "Funnel"


class ShareSubjectType(models.TextChoices):
    USER = "user", "User"
    ROLE = "role", "Role"


class ShareAccessLevel(models.TextChoices):
    VIEW = "view", "View"
    EDIT = "edit", "Edit"


class ExecutionStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    TIMED_OUT = "timed_out", "Timed out"


class CodedDefinitionMixin:
    """Normalize stable user-facing codes at the persistence boundary."""

    code_field: str

    def save(self, *args: Any, **kwargs: Any) -> None:
        value = getattr(self, self.code_field, "")
        if isinstance(value, str):
            setattr(self, self.code_field, value.strip().upper())
        super().save(*args, **kwargs)  # type: ignore[misc]


class QueryDefinition(CodedDefinitionMixin, TenantScopedModel, TimestampedModel):
    """A governed, declarative query against one registered dataset."""

    code_field = "query_code"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query_code = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    dataset_key = models.CharField(max_length=160, db_index=True)
    dataset_version = models.CharField(max_length=64, blank=True)
    dataset_schema_fingerprint = models.CharField(max_length=64, blank=True)
    dimensions = models.JSONField(default=list)
    measures = models.JSONField(default=list)
    filters = models.JSONField(default=list)
    grouping = models.JSONField(default=list)
    ordering = models.JSONField(default=list)
    parameters_schema = models.JSONField(default=dict)
    row_limit = models.PositiveIntegerField(default=500)
    cache_ttl_seconds = models.PositiveIntegerField(default=300)
    state = models.CharField(max_length=16, choices=LifecycleState.choices, default=LifecycleState.DRAFT)
    transition_history = models.JSONField(default=list)
    version = models.PositiveIntegerField(default=1)
    created_by_id = models.CharField(max_length=255)
    updated_by_id = models.CharField(max_length=255)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = BIQuerySet.as_manager()

    class Meta:
        db_table = "bi_query_definitions"
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "id"), name="bi_query_tenant_id_uniq"),
            models.UniqueConstraint(
                fields=("tenant_id", "query_code"),
                condition=Q(deleted_at__isnull=True),
                name="bi_query_live_code_uniq",
            ),
            models.CheckConstraint(
                condition=Q(row_limit__gte=1) & Q(row_limit__lte=10_000),
                name="bi_query_row_limit_ck",
            ),
            models.CheckConstraint(
                condition=Q(cache_ttl_seconds__gte=0) & Q(cache_ttl_seconds__lte=86_400),
                name="bi_query_cache_ttl_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "state", "updated_at"), name="bi_query_tenant_state_idx"),
            models.Index(fields=("tenant_id", "dataset_key", "state"), name="bi_query_tenant_data_idx"),
            models.Index(fields=("tenant_id", "deleted_at", "query_code"), name="bi_query_tenant_del_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.query_code} - {self.name}"


class Report(CodedDefinitionMixin, TenantScopedModel, TimestampedModel):
    """A presentation definition backed by a governed query definition."""

    code_field = "report_code"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_code = models.CharField(max_length=64)
    report_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    report_type = models.CharField(max_length=16, choices=ReportType.choices)
    query_definition = models.ForeignKey(
        QueryDefinition,
        on_delete=models.PROTECT,
        related_name="reports",
        null=True,
        blank=True,
    )
    visualization = models.JSONField(default=dict)
    default_parameters = models.JSONField(default=dict)
    state = models.CharField(max_length=16, choices=LifecycleState.choices, default=LifecycleState.DRAFT)
    transition_history = models.JSONField(default=list)
    version = models.PositiveIntegerField(default=1)
    created_by_id = models.CharField(max_length=255)
    updated_by_id = models.CharField(max_length=255)
    legacy_query = models.TextField(blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = BIQuerySet.as_manager()

    class Meta:
        db_table = "bi_reports"
        ordering = ("report_name", "id")
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "id"), name="bi_report_tenant_id_uniq"),
            models.UniqueConstraint(
                fields=("tenant_id", "report_code"),
                condition=Q(deleted_at__isnull=True),
                name="bi_report_live_code_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(state=LifecycleState.PUBLISHED) | (Q(query_definition__isnull=False) & Q(legacy_query=""))
                ),
                name="bi_report_published_query_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "report_type", "state"), name="bi_report_tenant_type_idx"),
            models.Index(fields=("tenant_id", "query_definition"), name="bi_report_tenant_query_idx"),
            models.Index(fields=("tenant_id", "updated_at"), name="bi_report_tenant_upd_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if (
            self.query_definition_id
            and not QueryDefinition.objects.for_tenant(self.tenant_id).filter(pk=self.query_definition_id).exists()
        ):
            errors["query_definition"] = "Query definition must belong to the report tenant."
        if self.state == LifecycleState.PUBLISHED:
            if not self.query_definition_id:
                errors["query_definition"] = "Published reports require a query definition."
            elif self.query_definition.state != LifecycleState.PUBLISHED:
                errors["query_definition"] = "Published reports require a published query definition."
            if self.legacy_query:
                errors["legacy_query"] = "Legacy query evidence cannot be executable."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.report_code} - {self.report_name}"


class Dashboard(CodedDefinitionMixin, TenantScopedModel, TimestampedModel):
    """A shareable canvas of independently executable BI widgets."""

    code_field = "dashboard_code"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dashboard_code = models.CharField(max_length=64)
    dashboard_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    global_filters = models.JSONField(default=list)
    refresh_interval_seconds = models.PositiveIntegerField(null=True, blank=True)
    state = models.CharField(max_length=16, choices=LifecycleState.choices, default=LifecycleState.DRAFT)
    transition_history = models.JSONField(default=list)
    version = models.PositiveIntegerField(default=1)
    created_by_id = models.CharField(max_length=255)
    updated_by_id = models.CharField(max_length=255)
    legacy_layout = models.JSONField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = BIQuerySet.as_manager()

    class Meta:
        db_table = "bi_dashboards"
        ordering = ("dashboard_name", "id")
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "id"), name="bi_dash_tenant_id_uniq"),
            models.UniqueConstraint(
                fields=("tenant_id", "dashboard_code"),
                condition=Q(deleted_at__isnull=True),
                name="bi_dash_live_code_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(refresh_interval_seconds__isnull=True)
                    | (Q(refresh_interval_seconds__gte=30) & Q(refresh_interval_seconds__lte=86_400))
                ),
                name="bi_dash_refresh_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "state", "updated_at"), name="bi_dash_tenant_state_idx"),
            models.Index(fields=("tenant_id", "deleted_at", "dashboard_code"), name="bi_dash_tenant_del_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.dashboard_code} - {self.dashboard_name}"


class DashboardWidget(TenantScopedModel, TimestampedModel):
    """One bounded layout item sourcing either a query or a report."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="widgets")
    query_definition = models.ForeignKey(
        QueryDefinition,
        on_delete=models.PROTECT,
        related_name="widgets",
        null=True,
        blank=True,
    )
    report = models.ForeignKey(
        Report,
        on_delete=models.PROTECT,
        related_name="widgets",
        null=True,
        blank=True,
    )
    widget_type = models.CharField(max_length=16, choices=WidgetType.choices)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    x = models.PositiveIntegerField(default=0)
    y = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(default=4)
    height = models.PositiveIntegerField(default=4)
    visualization = models.JSONField(default=dict)
    filters = models.JSONField(default=list)
    refresh_interval_seconds = models.PositiveIntegerField(null=True, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    version = models.PositiveIntegerField(default=1)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = BIQuerySet.as_manager()

    class Meta:
        db_table = "bi_dashboard_widgets"
        ordering = ("display_order", "id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(query_definition__isnull=False) & Q(report__isnull=True))
                    | (Q(query_definition__isnull=True) & Q(report__isnull=False))
                ),
                name="bi_widget_source_xor_ck",
            ),
            models.CheckConstraint(condition=Q(width__gte=1) & Q(width__lte=12), name="bi_widget_width_ck"),
            models.CheckConstraint(condition=Q(height__gte=1) & Q(height__lte=24), name="bi_widget_height_ck"),
            models.CheckConstraint(condition=Q(x__gte=0), name="bi_widget_x_ck"),
            models.CheckConstraint(condition=Q(y__gte=0), name="bi_widget_y_ck"),
            models.CheckConstraint(
                condition=(
                    Q(refresh_interval_seconds__isnull=True)
                    | (Q(refresh_interval_seconds__gte=30) & Q(refresh_interval_seconds__lte=86_400))
                ),
                name="bi_widget_refresh_ck",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "dashboard", "display_order"),
                condition=Q(deleted_at__isnull=True),
                name="bi_widget_live_order_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "dashboard", "display_order"), name="bi_widget_tenant_dash_idx"),
            models.Index(fields=("tenant_id", "query_definition"), name="bi_widget_tenant_query_idx"),
            models.Index(fields=("tenant_id", "report"), name="bi_widget_tenant_report_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.dashboard_id and not Dashboard.objects.for_tenant(self.tenant_id).filter(pk=self.dashboard_id).exists():
            errors["dashboard"] = "Dashboard must belong to the widget tenant."
        if (
            self.query_definition_id
            and not QueryDefinition.objects.for_tenant(self.tenant_id).filter(pk=self.query_definition_id).exists()
        ):
            errors["query_definition"] = "Query definition must belong to the widget tenant."
        if self.report_id and not Report.objects.for_tenant(self.tenant_id).filter(pk=self.report_id).exists():
            errors["report"] = "Report must belong to the widget tenant."
        if bool(self.query_definition_id) == bool(self.report_id):
            errors["query_definition"] = "Exactly one query definition or report is required."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.title} ({self.widget_type})"


class DashboardShare(TenantScopedModel, TimestampedModel):
    """Durable grant of dashboard access to a same-tenant user or role."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="shares")
    subject_type = models.CharField(max_length=16, choices=ShareSubjectType.choices)
    subject_id = models.CharField(max_length=255)
    access_level = models.CharField(max_length=8, choices=ShareAccessLevel.choices)
    shared_by_id = models.CharField(max_length=255)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = ShareQuerySet.as_manager()

    class Meta:
        db_table = "bi_dashboard_shares"
        ordering = ("-created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "dashboard", "subject_type", "subject_id"),
                condition=Q(revoked_at__isnull=True),
                name="bi_share_active_subject_uniq",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True) | Q(expires_at__gt=models.F("created_at")),
                name="bi_share_expiry_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "subject_type", "subject_id", "revoked_at"),
                name="bi_share_tenant_subj_idx",
            ),
            models.Index(fields=("tenant_id", "dashboard", "revoked_at"), name="bi_share_tenant_dash_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.dashboard_id and not Dashboard.objects.for_tenant(self.tenant_id).filter(pk=self.dashboard_id).exists():
            raise ValidationError({"dashboard": "Dashboard must belong to the share tenant."})

    def __str__(self) -> str:
        return f"{self.dashboard_id}: {self.subject_type}:{self.subject_id} ({self.access_level})"


class QueryExecution(TenantScopedModel, TimestampedModel):
    """Immutable evidence and bounded results for one durable query run."""

    TERMINAL_STATUSES = frozenset(
        {ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED, ExecutionStatus.TIMED_OUT}
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query_definition = models.ForeignKey(QueryDefinition, on_delete=models.PROTECT, related_name="executions")
    report = models.ForeignKey(
        Report,
        on_delete=models.PROTECT,
        related_name="executions",
        null=True,
        blank=True,
    )
    dashboard = models.ForeignKey(
        Dashboard,
        on_delete=models.PROTECT,
        related_name="executions",
        null=True,
        blank=True,
    )
    async_job = models.ForeignKey(AsyncJob, on_delete=models.PROTECT, related_name="bi_executions", unique=True)
    actor_id = models.CharField(max_length=255)
    idempotency_key = models.CharField(max_length=255)
    definition_version = models.PositiveIntegerField()
    dataset_key = models.CharField(max_length=160)
    dataset_version = models.CharField(max_length=64, blank=True)
    dataset_schema_fingerprint = models.CharField(max_length=64, blank=True)
    effective_query_fingerprint = models.CharField(max_length=64, blank=True)
    freshness_token = models.CharField(max_length=255, blank=True)
    data_as_of = models.DateTimeField(null=True, blank=True)
    result_purged_at = models.DateTimeField(null=True, blank=True)
    parameters = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=ExecutionStatus.choices, default=ExecutionStatus.QUEUED)
    transition_history = models.JSONField(default=list)
    result_columns = models.JSONField(default=list)
    result_rows = models.JSONField(default=list)
    row_count = models.PositiveIntegerField(null=True, blank=True)
    truncated = models.BooleanField(default=False)
    cache_hit = models.BooleanField(default=False)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = ExecutionQuerySet.as_manager()

    class Meta:
        db_table = "bi_query_executions"
        ordering = ("-created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"),
                name="bi_execution_tenant_idem_uniq",
            ),
            models.CheckConstraint(
                condition=~Q(status=ExecutionStatus.FAILED) | Q(result_rows=[]),
                name="bi_execution_failed_empty_ck",
            ),
            models.CheckConstraint(
                condition=(~Q(status=ExecutionStatus.SUCCEEDED) | Q(row_count__isnull=False)),
                name="bi_execution_success_count_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "created_at"), name="bi_exec_tenant_status_idx"),
            models.Index(fields=("tenant_id", "query_definition", "created_at"), name="bi_exec_tenant_query_idx"),
            models.Index(fields=("tenant_id", "report", "created_at"), name="bi_exec_tenant_report_idx"),
            models.Index(fields=("tenant_id", "dashboard", "created_at"), name="bi_exec_tenant_dash_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        relationships = (
            ("query_definition", QueryDefinition, self.query_definition_id),
            ("report", Report, self.report_id),
            ("dashboard", Dashboard, self.dashboard_id),
            ("async_job", AsyncJob, self.async_job_id),
        )
        for field, model, object_id in relationships:
            if object_id and not model.objects.for_tenant(self.tenant_id).filter(pk=object_id).exists():
                errors[field] = f"{field.replace('_', ' ').capitalize()} must belong to the execution tenant."
        if len(self.result_rows) > 1_000:
            errors["result_rows"] = "Stored execution results cannot exceed 1,000 rows."
        elif len(json.dumps(self.result_rows, default=str, separators=(",", ":")).encode("utf-8")) > 2 * 1024 * 1024:
            errors["result_rows"] = "Stored execution results cannot exceed 2 MiB."
        if self.status == ExecutionStatus.FAILED and self.result_rows:
            errors["result_rows"] = "Failed executions cannot contain result rows."
        if self.status == ExecutionStatus.SUCCEEDED and self.row_count is None:
            errors["row_count"] = "Succeeded executions require a row count."
        if self.status == ExecutionStatus.SUCCEEDED and not self.result_columns:
            errors["result_columns"] = "Succeeded executions require result column metadata."
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            prior = type(self).objects.for_tenant(self.tenant_id).filter(pk=self.pk).first()
            if prior and prior.status in self.TERMINAL_STATUSES:
                mutable_fields = (
                    "status",
                    "transition_history",
                    "result_columns",
                    "row_count",
                    "truncated",
                    "cache_hit",
                    "duration_ms",
                    "error_code",
                    "error_message",
                    "started_at",
                    "completed_at",
                    "dataset_version",
                    "dataset_schema_fingerprint",
                    "effective_query_fingerprint",
                    "freshness_token",
                    "data_as_of",
                    "parameters",
                )
                changed = [field for field in mutable_fields if getattr(prior, field) != getattr(self, field)]
                rows_are_redacted = bool(prior.result_rows) and self.result_rows == []
                if changed or (prior.result_rows != self.result_rows and not rows_are_redacted):
                    raise ValidationError("Terminal query executions are immutable.")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.dataset_key} [{self.status}] ({self.id})"
