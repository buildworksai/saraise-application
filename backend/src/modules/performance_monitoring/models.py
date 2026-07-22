"""Tenant-safe operational telemetry, alerting, and service-level evidence.

The module productizes SARAISE's observability primitives; it does not replace
the runtime log/correlation/Prometheus stack.  Provider identifiers are opaque
and credentials are deliberately not persisted here.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone as django_timezone

from src.core.tenancy import TenantScopedModel, TimestampedModel


def generate_uuid() -> str:
    """Compatibility callable retained for historical migration imports."""

    return str(uuid.uuid4())


class MetricType(models.TextChoices):
    GAUGE = "gauge", "Gauge"
    COUNTER = "counter", "Counter"
    HISTOGRAM = "histogram", "Histogram"
    SUMMARY = "summary", "Summary"


class SourceType(models.TextChoices):
    OTLP = "otlp", "OpenTelemetry/OTLP"
    PROMETHEUS = "prometheus", "Prometheus"
    APPLICATION = "application", "Application SDK"
    WEBHOOK = "webhook", "Webhook"
    IMPORT = "import", "File import"


class HealthState(models.TextChoices):
    HEALTHY = "healthy", "Healthy"
    STALE = "stale", "Stale"
    DEGRADED = "degraded", "Degraded"
    NO_TELEMETRY = "no_telemetry", "No telemetry"
    DISABLED = "disabled", "Disabled"


class Comparison(models.TextChoices):
    GT = "gt", ">"
    GTE = "gte", ">="
    LT = "lt", "<"
    LTE = "lte", "<="
    EQ = "eq", "="
    NE = "ne", "!="
    ABSENT = "absent", "Absent"


class AlertCondition(models.TextChoices):
    ABOVE = "above_threshold", "Above threshold"
    BELOW = "below_threshold", "Below threshold"
    RATE = "rate_of_change", "Rate of change"
    ABSENCE = "absence", "Absence"


ALERT_CONDITION_ALIASES = {
    "above": AlertCondition.ABOVE,
    "below": AlertCondition.BELOW,
}


def normalize_alert_condition(value: str) -> str:
    """Return the canonical persisted value for a public alert condition."""

    return ALERT_CONDITION_ALIASES.get(value, value)


class SLAWindow(models.TextChoices):
    ROLLING_1H = "rolling_1h", "Rolling hour"
    ROLLING_24H = "rolling_24h", "Rolling 24 hours"
    CALENDAR_MONTH = "calendar_month", "Calendar month"


class Severity(models.TextChoices):
    INFO = "info", "Info"
    WARNING = "warning", "Warning"
    CRITICAL = "critical", "Critical"


class AlertState(models.TextChoices):
    FIRING = "firing", "Firing"
    ACKNOWLEDGED = "acknowledged", "Acknowledged"
    RESOLVED = "resolved", "Resolved"


class DeliveryState(models.TextChoices):
    PENDING = "pending", "Pending"
    SENT = "sent", "Sent"
    DELIVERED = "delivered", "Delivered"
    FAILED = "failed", "Failed"
    SUPPRESSED = "suppressed", "Suppressed"


class ComplianceState(models.TextChoices):
    COMPLIANT = "compliant", "Compliant"
    BREACHED = "breached", "Breached"
    INSUFFICIENT_DATA = "insufficient_data", "Insufficient data"


class ReportState(models.TextChoices):
    PENDING = "pending", "Pending"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"


class DomainModel(TenantScopedModel, TimestampedModel):
    """Ownership/audit/soft-delete contract for mutable domain aggregates."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.UUIDField(default=uuid.UUID(int=0), db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    _immutable_fields: ClassVar[tuple[str, ...]] = ("tenant_id", "created_by")

    class Meta:
        abstract = True

    def clean(self) -> None:
        super().clean()
        if not self._state.adding and self.pk:
            stored = type(self).objects.filter(pk=self.pk).values(*self._immutable_fields).first()
            if stored:
                changed = [field for field in self._immutable_fields if stored[field] != getattr(self, field)]
                if changed:
                    raise ValidationError({field: "This field is immutable." for field in changed})
        if self.is_deleted and self.deleted_at is None:
            raise ValidationError({"deleted_at": "Soft-deleted rows require a deletion timestamp."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, using: str | None = None, keep_parents: bool = False) -> tuple[int, dict[str, int]]:
        del keep_parents
        if self.is_deleted:
            return 0, {}
        self.is_deleted = True
        self.deleted_at = django_timezone.now()
        self.save(using=using, update_fields=["is_deleted", "deleted_at", "updated_at"])
        return 1, {self._meta.label: 1}


class ImmutableEvidenceError(ValidationError):
    """Raised whenever append-only monitoring evidence is mutated."""


class ImmutableEvidenceQuerySet(models.QuerySet[models.Model]):
    """Tenant-aware queryset that rejects every bulk mutation path."""

    def for_tenant(self, tenant_id: uuid.UUID) -> "ImmutableEvidenceQuerySet":
        return self.filter(tenant_id=tenant_id)

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ImmutableEvidenceError("Monitoring evidence is append-only.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableEvidenceError("Monitoring evidence is append-only.")


class ImmutableEvidenceModel(TenantScopedModel):
    """Append-only evidence protected at instance, queryset, and database layers."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    created_by = models.UUIDField(default=uuid.UUID(int=0), db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ImmutableEvidenceQuerySet.as_manager()

    class Meta:
        abstract = True
        base_manager_name = "objects"
        default_manager_name = "objects"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Monitoring evidence is append-only.")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ImmutableEvidenceError("Monitoring evidence is append-only.")


class TelemetrySource(DomainModel):
    name = models.CharField(max_length=160)
    source_type = models.CharField(max_length=24, choices=SourceType.choices)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=24, choices=HealthState.choices, default=HealthState.NO_TELEMETRY)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    sampling_rate = models.DecimalField(max_digits=5, decimal_places=4, default=1)
    retention_days = models.PositiveSmallIntegerField(default=90)
    daily_event_quota = models.PositiveBigIntegerField(default=1_000_000)
    redaction_fields = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "performance_telemetry_sources"
        constraints = [
            models.UniqueConstraint(Lower("name"), "tenant_id", name="pm_source_name_ci_uq"),
            models.CheckConstraint(
                condition=Q(daily_event_quota__gte=1, daily_event_quota__lte=100_000_000),
                name="pm_source_daily_quota_safe",
            ),
        ]
        indexes = [models.Index(fields=["tenant_id", "status"]), models.Index(fields=["tenant_id", "last_seen_at"])]

    def clean(self) -> None:
        super().clean()
        if not 0 < self.sampling_rate <= 1:
            raise ValidationError({"sampling_rate": "Must be greater than 0 and at most 1."})
        if not isinstance(self.redaction_fields, list):
            raise ValidationError({"redaction_fields": "Must be a list of attribute names."})


class MonitoringEnvironment(DomainModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80)
    kind = models.CharField(max_length=24, default="production")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "performance_environments"
        constraints = [models.UniqueConstraint(fields=["tenant_id", "slug"], name="pm_environment_slug_uq")]
        indexes = [models.Index(fields=["tenant_id", "kind", "is_active"])]


class MonitoredService(DomainModel):
    environment = models.ForeignKey(MonitoringEnvironment, on_delete=models.PROTECT, related_name="services")
    source = models.ForeignKey(
        TelemetrySource, on_delete=models.PROTECT, null=True, blank=True, related_name="services"
    )
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=100)
    namespace = models.CharField(max_length=120, default="saraise")
    version = models.CharField(max_length=80, blank=True)
    owner = models.CharField(max_length=160, blank=True)
    language = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=24, choices=HealthState.choices, default=HealthState.NO_TELEMETRY)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "performance_monitored_services"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "environment", "slug"], name="pm_service_env_slug_uq")
        ]
        indexes = [models.Index(fields=["tenant_id", "status"]), models.Index(fields=["tenant_id", "namespace"])]

    def clean(self) -> None:
        super().clean()
        for field in ("environment", "source"):
            related = getattr(self, field, None)
            if related and related.tenant_id != self.tenant_id:
                raise ValidationError({field: "Related record must belong to the same tenant."})


class Metric(DomainModel):
    source = models.ForeignKey(TelemetrySource, on_delete=models.PROTECT, null=True, blank=True, related_name="metrics")
    service = models.ForeignKey(
        MonitoredService, on_delete=models.PROTECT, null=True, blank=True, related_name="metrics"
    )
    environment = models.ForeignKey(
        MonitoringEnvironment, on_delete=models.PROTECT, null=True, blank=True, related_name="metrics"
    )
    metric_name = models.CharField(max_length=255, db_index=True)
    display_name = models.CharField(max_length=255, blank=True)
    namespace = models.CharField(max_length=120, default="custom")
    description = models.TextField(blank=True)
    metric_type = models.CharField(max_length=16, choices=MetricType.choices)
    unit = models.CharField(max_length=40, default="1")
    default_tags = models.JSONField(default=dict, blank=True)
    expected_interval_seconds = models.PositiveIntegerField(default=60)
    retention_days = models.PositiveSmallIntegerField(default=90)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "performance_metrics"
        constraints = [models.UniqueConstraint(Lower("metric_name"), "tenant_id", name="pm_metric_name_ci_uq")]
        indexes = [
            models.Index(fields=["tenant_id", "metric_type", "is_active"]),
            models.Index(fields=["tenant_id", "namespace", "metric_name"]),
            models.Index(fields=["tenant_id", "service"]),
        ]

    def clean(self) -> None:
        super().clean()
        if not self.metric_name or not re.fullmatch(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$", self.metric_name):
            raise ValidationError({"metric_name": "Metric names must use lowercase dot notation."})
        if not isinstance(self.default_tags, dict):
            raise ValidationError({"default_tags": "Must be an object."})
        for field in ("source", "service", "environment"):
            related = getattr(self, field, None)
            if related and related.tenant_id != self.tenant_id:
                raise ValidationError({field: "Related record must belong to the same tenant."})


class MetricDataPoint(ImmutableEvidenceModel):
    metric = models.ForeignKey(Metric, on_delete=models.PROTECT, related_name="data_points")
    timestamp = models.DateTimeField(db_index=True)
    value = models.DecimalField(max_digits=20, decimal_places=6)
    tags = models.JSONField(default=dict, blank=True)
    session_id = models.CharField(max_length=128, blank=True)
    source_module = models.CharField(max_length=100, blank=True)
    idempotency_key = models.CharField(max_length=160, blank=True)
    trace_id = models.CharField(max_length=32, blank=True)
    span_id = models.CharField(max_length=16, blank=True)

    class Meta:
        db_table = "performance_metric_data_points"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "metric", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="pm_metric_idempotency_uq",
            )
        ]
        indexes = [
            models.Index(fields=["tenant_id", "metric", "timestamp"]),
            models.Index(fields=["tenant_id", "trace_id"]),
        ]

    def clean(self) -> None:
        super().clean()
        if self.metric_id and self.metric.tenant_id != self.tenant_id:
            raise ValidationError({"metric": "Metric must belong to the same tenant."})
        if not isinstance(self.tags, dict):
            raise ValidationError({"tags": "Must be an object."})


class LogEntry(ImmutableEvidenceModel):
    source = models.ForeignKey(TelemetrySource, on_delete=models.PROTECT, related_name="logs")
    service = models.ForeignKey(MonitoredService, on_delete=models.PROTECT, null=True, blank=True, related_name="logs")
    environment = models.ForeignKey(
        MonitoringEnvironment, on_delete=models.PROTECT, null=True, blank=True, related_name="logs"
    )
    timestamp = models.DateTimeField(db_index=True)
    observed_at = models.DateTimeField(default=django_timezone.now)
    level = models.CharField(max_length=20, db_index=True)
    message = models.TextField()
    attributes = models.JSONField(default=dict, blank=True)
    trace_id = models.CharField(max_length=32, blank=True, db_index=True)
    span_id = models.CharField(max_length=16, blank=True)
    correlation_id = models.CharField(max_length=128, blank=True, db_index=True)
    idempotency_key = models.CharField(max_length=160, blank=True)

    class Meta:
        db_table = "performance_log_entries"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "source", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="pm_log_idempotency_uq",
            )
        ]
        indexes = [
            models.Index(fields=["tenant_id", "service", "timestamp"]),
            models.Index(fields=["tenant_id", "level", "timestamp"]),
        ]


class Trace(ImmutableEvidenceModel):
    source = models.ForeignKey(TelemetrySource, on_delete=models.PROTECT, related_name="traces")
    service = models.ForeignKey(MonitoredService, on_delete=models.PROTECT, related_name="traces")
    environment = models.ForeignKey(
        MonitoringEnvironment, on_delete=models.PROTECT, null=True, blank=True, related_name="traces"
    )
    trace_id = models.CharField(max_length=32)
    name = models.CharField(max_length=240)
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField()
    duration_ms = models.FloatField()
    status = models.CharField(max_length=20, default="unset", db_index=True)
    attributes = models.JSONField(default=dict, blank=True)
    sampled = models.BooleanField(default=True)
    span_count = models.PositiveIntegerField(default=0)
    error_span_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "performance_traces"
        constraints = [models.UniqueConstraint(fields=["tenant_id", "trace_id"], name="pm_trace_id_uq")]
        indexes = [
            models.Index(fields=["tenant_id", "service", "started_at"]),
            models.Index(fields=["tenant_id", "status", "started_at"]),
        ]

    def clean(self) -> None:
        super().clean()
        if self.ended_at < self.started_at:
            raise ValidationError({"ended_at": "Must be after started_at."})
        if self.duration_ms < 0:
            raise ValidationError({"duration_ms": "Must not be negative."})


class Span(ImmutableEvidenceModel):
    trace = models.ForeignKey(Trace, on_delete=models.PROTECT, related_name="spans")
    service = models.ForeignKey(MonitoredService, on_delete=models.PROTECT, related_name="spans")
    span_id = models.CharField(max_length=16)
    parent_span_id = models.CharField(max_length=16, blank=True)
    name = models.CharField(max_length=240)
    kind = models.CharField(max_length=24, default="internal")
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    duration_ms = models.FloatField()
    status = models.CharField(max_length=20, default="unset")
    attributes = models.JSONField(default=dict, blank=True)
    events = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "performance_spans"
        constraints = [models.UniqueConstraint(fields=["tenant_id", "trace", "span_id"], name="pm_span_id_uq")]
        indexes = [
            models.Index(fields=["tenant_id", "trace", "started_at"]),
            models.Index(fields=["tenant_id", "service", "started_at"]),
        ]

    def clean(self) -> None:
        super().clean()
        if self.trace_id and self.trace.tenant_id != self.tenant_id:
            raise ValidationError({"trace": "Trace must belong to the same tenant."})
        if self.service_id and self.service.tenant_id != self.tenant_id:
            raise ValidationError({"service": "Service must belong to the same tenant."})


class Dashboard(DomainModel):
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    layout = models.JSONField(default=list)
    variables = models.JSONField(default=list, blank=True)
    refresh_interval_seconds = models.PositiveIntegerField(default=60)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "performance_dashboards"
        constraints = [models.UniqueConstraint(Lower("name"), "tenant_id", name="pm_dashboard_name_ci_uq")]
        indexes = [models.Index(fields=["tenant_id", "is_active"])]


class AlertRule(DomainModel):
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    metric = models.ForeignKey(Metric, on_delete=models.PROTECT, null=True, blank=True, related_name="alert_rules")
    metric_name = models.CharField(
        max_length=200, blank=True, help_text="Forward reference for metrics not ingested yet."
    )
    condition = models.CharField(max_length=30, choices=AlertCondition.choices)
    threshold = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    aggregation = models.CharField(max_length=20, default="avg")
    evaluation_window_minutes = models.PositiveIntegerField(default=5)
    evaluation_interval_seconds = models.PositiveIntegerField(default=60)
    cooldown_minutes = models.PositiveIntegerField(default=15)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.WARNING)
    action = models.JSONField(default=dict)
    group_by_tags = models.JSONField(default=list, blank=True)
    auto_resolve = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True, db_index=True)
    last_evaluated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "performance_alert_rules"
        constraints = [models.UniqueConstraint(Lower("name"), "tenant_id", name="pm_alert_rule_name_ci_uq")]
        indexes = [
            models.Index(fields=["tenant_id", "is_active", "last_evaluated_at"]),
            models.Index(fields=["tenant_id", "metric"]),
        ]

    def clean(self) -> None:
        super().clean()
        if self.metric_id and self.metric.tenant_id != self.tenant_id:
            raise ValidationError({"metric": "Metric must belong to the same tenant."})
        if not self.metric_id and not self.metric_name:
            raise ValidationError({"metric_name": "Select a metric or provide a forward metric name."})
        if not isinstance(self.action, dict):
            raise ValidationError({"action": "Must be an object."})


class Alert(DomainModel):
    alert_rule = models.ForeignKey(AlertRule, on_delete=models.PROTECT, related_name="alerts")
    metric = models.ForeignKey(Metric, on_delete=models.PROTECT, null=True, blank=True, related_name="alerts")
    metric_name = models.CharField(max_length=255)
    condition = models.CharField(max_length=30, choices=AlertCondition.choices)
    status = models.CharField(max_length=20, choices=AlertState.choices, default=AlertState.FIRING, db_index=True)
    severity = models.CharField(max_length=16, choices=Severity.choices)
    deduplication_key = models.CharField(max_length=255)
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    triggered_value = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    threshold = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    triggered_at = models.DateTimeField(default=django_timezone.now)
    last_observed_at = models.DateTimeField(default=django_timezone.now)
    occurrence_count = models.PositiveIntegerField(default=1)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.UUIDField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.UUIDField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "performance_alerts"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "deduplication_key"],
                condition=Q(status__in=[AlertState.FIRING, AlertState.ACKNOWLEDGED], is_deleted=False),
                name="pm_alert_open_dedup_uq",
            )
        ]
        indexes = [
            models.Index(fields=["tenant_id", "status", "severity", "triggered_at"]),
            models.Index(fields=["tenant_id", "alert_rule", "triggered_at"]),
        ]


class AlertNotificationOutcome(ImmutableEvidenceModel):
    alert = models.ForeignKey(Alert, on_delete=models.PROTECT, related_name="notification_outcomes")
    channel = models.CharField(max_length=30)
    destination_ref = models.CharField(max_length=200, help_text="Opaque notification destination reference.")
    state = models.CharField(max_length=20, choices=DeliveryState.choices)
    attempt = models.PositiveSmallIntegerField(default=1)
    idempotency_key = models.CharField(max_length=200)
    provider_message_id = models.CharField(max_length=200, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    correlation_id = models.CharField(max_length=128, db_index=True)
    attempted_at = models.DateTimeField(default=django_timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "performance_alert_notification_outcomes"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "idempotency_key", "attempt"], name="pm_notify_attempt_uq"),
            models.CheckConstraint(condition=~Q(correlation_id=""), name="pm_notify_correlation_present"),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "alert", "attempted_at"]),
            models.Index(fields=["tenant_id", "state"]),
        ]


class SLADefinition(DomainModel):
    name = models.CharField(max_length=180, blank=True)
    description = models.TextField(blank=True)
    service = models.ForeignKey(MonitoredService, on_delete=models.PROTECT, null=True, blank=True, related_name="slas")
    metric = models.ForeignKey(Metric, on_delete=models.PROTECT, null=True, blank=True, related_name="slas")
    service_name = models.CharField(max_length=255)
    metric_name = models.CharField(max_length=255)
    comparison = models.CharField(max_length=10, choices=Comparison.choices)
    target = models.DecimalField(max_digits=10, decimal_places=4)
    window = models.CharField(max_length=30, choices=SLAWindow.choices)
    expected_interval_seconds = models.PositiveIntegerField(default=60)
    timezone = models.CharField(max_length=64, default="UTC")
    version = models.PositiveIntegerField(default=1)
    previous_version = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="next_versions"
    )
    effective_from = models.DateTimeField(default=django_timezone.now)
    effective_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "performance_sla_definitions"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "service_name", "metric_name", "window", "version"], name="pm_sla_key_version_uq"
            ),
            models.CheckConstraint(condition=Q(target__gt=0), name="pm_sla_target_positive"),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "is_active", "effective_from"]),
            models.Index(fields=["tenant_id", "metric"]),
        ]

    def clean(self) -> None:
        super().clean()
        for field in ("service", "metric", "previous_version"):
            related = getattr(self, field, None)
            if related and related.tenant_id != self.tenant_id:
                raise ValidationError({field: "Related record must belong to the same tenant."})


class ServiceLevelObjective(DomainModel):
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    service = models.ForeignKey(MonitoredService, on_delete=models.PROTECT, related_name="slos")
    indicator_metric = models.ForeignKey(Metric, on_delete=models.PROTECT, related_name="slos")
    comparison = models.CharField(max_length=10, choices=Comparison.choices)
    threshold = models.FloatField()
    objective_percentage = models.DecimalField(max_digits=6, decimal_places=3)
    window_days = models.PositiveSmallIntegerField(default=30)
    expected_interval_seconds = models.PositiveIntegerField(default=60)
    error_budget_minutes = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "performance_slos"
        constraints = [models.UniqueConstraint(Lower("name"), "tenant_id", name="pm_slo_name_ci_uq")]
        indexes = [models.Index(fields=["tenant_id", "service", "is_active"])]


class SLAComplianceRecord(ImmutableEvidenceModel):
    sla = models.ForeignKey(SLADefinition, on_delete=models.PROTECT, related_name="compliance_records")
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    expected_samples = models.PositiveIntegerField()
    observed_samples = models.PositiveIntegerField()
    compliant_samples = models.PositiveIntegerField()
    missing_samples = models.PositiveIntegerField()
    actual_value = models.DecimalField(max_digits=10, decimal_places=4)
    target_value = models.DecimalField(max_digits=10, decimal_places=4)
    is_compliant = models.BooleanField()
    breach_duration_minutes = models.PositiveIntegerField(default=0)
    compliance_percentage = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    breach_duration_seconds = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=24, choices=ComplianceState.choices)
    evidence = models.JSONField(default=dict)

    class Meta:
        db_table = "performance_sla_compliance"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "sla", "period_start", "period_end"], name="pm_sla_period_uq")
        ]
        indexes = [
            models.Index(fields=["tenant_id", "sla", "period_end"]),
            models.Index(fields=["tenant_id", "status"]),
        ]


class SLABreach(ImmutableEvidenceModel):
    sla = models.ForeignKey(SLADefinition, on_delete=models.PROTECT, related_name="breaches")
    compliance_record = models.ForeignKey(SLAComplianceRecord, on_delete=models.PROTECT, related_name="breaches")
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    duration_seconds = models.PositiveBigIntegerField()
    worst_value = models.FloatField(null=True, blank=True)
    evidence = models.JSONField(default=dict)

    class Meta:
        db_table = "performance_sla_breaches"
        indexes = [models.Index(fields=["tenant_id", "sla", "started_at"])]


class ErrorBudgetSnapshot(ImmutableEvidenceModel):
    slo = models.ForeignKey(ServiceLevelObjective, on_delete=models.PROTECT, related_name="budget_snapshots")
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    budget_minutes = models.PositiveIntegerField()
    consumed_minutes = models.PositiveIntegerField()
    remaining_minutes = models.IntegerField()
    burn_rate = models.FloatField()
    status = models.CharField(max_length=24, choices=ComplianceState.choices)

    class Meta:
        db_table = "performance_error_budget_snapshots"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "slo", "period_start", "period_end"], name="pm_slo_budget_period_uq"
            )
        ]
        indexes = [models.Index(fields=["tenant_id", "slo", "period_end"])]


class SLAReport(ImmutableEvidenceModel):
    sla = models.ForeignKey(SLADefinition, on_delete=models.PROTECT, null=True, blank=True, related_name="reports")
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    status = models.CharField(max_length=20, choices=ReportState.choices)
    summary = models.JSONField(default=dict)
    artifact_ref = models.CharField(
        max_length=300, blank=True, help_text="Opaque reference to durable artifact storage."
    )
    artifact_sha256 = models.CharField(max_length=64, blank=True)
    generated_by = models.UUIDField(null=True, blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=80, blank=True)

    class Meta:
        db_table = "performance_sla_reports"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "sla", "period_start", "period_end"], name="pm_sla_report_period_uq"
            )
        ]
        indexes = [models.Index(fields=["tenant_id", "status", "created_at"])]


class MonitoringExtension(DomainModel):
    """Versioned OSS extension point for paid metric/dashboard/SLO packs."""

    extension_key = models.CharField(max_length=160)
    provider = models.CharField(max_length=160)
    schema_version = models.CharField(max_length=24, default="1.0")
    metric_namespaces = models.JSONField(default=list)
    semantic_attributes = models.JSONField(default=dict)
    dashboard_templates = models.JSONField(default=list)
    slo_packs = models.JSONField(default=list)
    alert_rule_templates = models.JSONField(default=list)
    drill_down_links = models.JSONField(default=list)
    event_consumers = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "performance_monitoring_extensions"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "extension_key", "schema_version"], name="pm_extension_version_uq"
            )
        ]
        indexes = [models.Index(fields=["tenant_id", "provider", "is_active"])]


class AppendOnlyConfigurationQuerySet(models.QuerySet):
    """Prevent bulk mutation from bypassing append-only configuration history."""

    def for_tenant(self, tenant_id: uuid.UUID) -> "AppendOnlyConfigurationQuerySet":
        return self.filter(tenant_id=tenant_id)

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ValidationError("Configuration history is append-only.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Configuration history is append-only.")


class PerformanceMonitoringConfiguration(TenantScopedModel, TimestampedModel):
    """The current validated configuration document for one tenant/environment."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.SlugField(max_length=64, default="default")
    document = models.JSONField()
    version = models.PositiveIntegerField(default=1)
    created_by = models.UUIDField(db_index=True)
    updated_by = models.UUIDField(db_index=True)
    correlation_id = models.CharField(max_length=128, db_index=True)

    class Meta:
        db_table = "performance_monitoring_configurations"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "environment"], name="pm_config_tenant_env_uq"),
            models.CheckConstraint(condition=Q(version__gte=1), name="pm_config_version_positive"),
            models.CheckConstraint(condition=~Q(correlation_id=""), name="pm_config_correlation_present"),
        ]
        indexes = [models.Index(fields=["tenant_id", "environment", "version"], name="pm_cfg_tenant_env_ver_idx")]

    def clean(self) -> None:
        super().clean()
        if not self._state.adding and self.pk:
            stored = type(self).objects.filter(pk=self.pk).values("tenant_id", "environment", "created_by").first()
            if stored:
                immutable = {
                    field: "This field is immutable."
                    for field in ("tenant_id", "environment", "created_by")
                    if stored[field] != getattr(self, field)
                }
                if immutable:
                    raise ValidationError(immutable)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class ImmutableConfigurationRecord(TenantScopedModel):
    """Shared hard append-only behavior for versions and audit records."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_id = models.UUIDField(db_index=True)
    correlation_id = models.CharField(max_length=128, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyConfigurationQuerySet.as_manager()

    class Meta:
        abstract = True
        base_manager_name = "objects"
        default_manager_name = "objects"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Configuration history is append-only.")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Configuration history is append-only.")


class PerformanceMonitoringConfigurationVersion(ImmutableConfigurationRecord):
    """Immutable snapshot enabling exact rollback to every prior version."""

    configuration = models.ForeignKey(
        PerformanceMonitoringConfiguration,
        on_delete=models.PROTECT,
        related_name="versions",
    )
    environment = models.SlugField(max_length=64)
    version = models.PositiveIntegerField()
    document = models.JSONField()
    change_reason = models.CharField(max_length=240)

    class Meta:
        db_table = "performance_monitoring_configuration_versions"
        base_manager_name = "objects"
        default_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(fields=["configuration", "version"], name="pm_config_version_uq"),
            models.CheckConstraint(condition=Q(version__gte=1), name="pm_config_snapshot_version_positive"),
            models.CheckConstraint(condition=~Q(correlation_id=""), name="pm_config_version_correlation_present"),
        ]
        indexes = [models.Index(fields=["tenant_id", "environment", "-version"], name="pm_cfg_tenant_version_idx")]

    def clean(self) -> None:
        super().clean()
        if self.configuration_id and self.configuration.tenant_id != self.tenant_id:
            raise ValidationError({"configuration": "Configuration must belong to the same tenant."})
        if self.configuration_id and self.configuration.environment != self.environment:
            raise ValidationError({"environment": "Environment must match the configuration."})


class PerformanceMonitoringConfigurationAudit(ImmutableConfigurationRecord):
    """Immutable who/what/when ledger for every configuration mutation."""

    configuration = models.ForeignKey(
        PerformanceMonitoringConfiguration,
        on_delete=models.PROTECT,
        related_name="audit_records",
    )
    environment = models.SlugField(max_length=64)
    action = models.CharField(max_length=24)
    from_version = models.PositiveIntegerField(null=True, blank=True)
    to_version = models.PositiveIntegerField()
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField()
    change_reason = models.CharField(max_length=240)

    class Meta:
        db_table = "performance_monitoring_configuration_audit"
        base_manager_name = "objects"
        default_manager_name = "objects"
        constraints = [
            models.CheckConstraint(condition=Q(to_version__gte=1), name="pm_config_audit_version_positive"),
            models.CheckConstraint(condition=~Q(correlation_id=""), name="pm_config_audit_correlation_present"),
            models.CheckConstraint(
                condition=Q(action__in=("create", "update", "import", "rollback")),
                name="pm_config_audit_action_allowed",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "environment", "-created_at"], name="pm_cfg_audit_tenant_time_idx"),
            models.Index(fields=["tenant_id", "correlation_id"], name="pm_cfg_audit_corr_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.configuration_id and self.configuration.tenant_id != self.tenant_id:
            raise ValidationError({"configuration": "Configuration must belong to the same tenant."})


class PerformanceMonitoringResource(TelemetrySource):
    """Deprecated proxy kept only for the central tenancy registry transition."""

    class Meta:
        proxy = True
        app_label = "performance_monitoring"
