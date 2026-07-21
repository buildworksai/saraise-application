"""Operation-specific API serializers for performance monitoring."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import (
    Alert,
    AlertCondition,
    AlertRule,
    Comparison,
    Dashboard,
    ErrorBudgetSnapshot,
    LogEntry,
    Metric,
    MetricDataPoint,
    MetricType,
    MonitoredService,
    MonitoringEnvironment,
    MonitoringExtension,
    ServiceLevelObjective,
    Severity,
    SLAComplianceRecord,
    SLADefinition,
    SLAReport,
    SLAWindow,
    SourceType,
    Span,
    TelemetrySource,
    Trace,
    normalize_alert_condition,
)


class TenantReadOnlySerializer(serializers.ModelSerializer):
    class Meta:
        read_only_fields = ("id", "tenant_id", "created_by", "created_at", "updated_at", "is_deleted", "deleted_at")


class AlertConditionField(serializers.ChoiceField):
    """Accept compatibility aliases while exposing canonical API choices."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(choices=AlertCondition.choices, **kwargs)

    def to_internal_value(self, data: Any) -> str:
        if isinstance(data, str):
            data = normalize_alert_condition(data)
        return super().to_internal_value(data)


class TelemetrySourceListSerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = TelemetrySource
        fields = ("id", "name", "source_type", "status", "last_seen_at", "sampling_rate", "is_active", "created_at")
        read_only_fields = TenantReadOnlySerializer.Meta.read_only_fields + ("status", "last_seen_at")


class TelemetrySourceDetailSerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = TelemetrySource
        fields = TelemetrySourceListSerializer.Meta.fields + (
            "description",
            "retention_days",
            "daily_event_quota",
            "redaction_fields",
            "updated_at",
        )
        read_only_fields = TenantReadOnlySerializer.Meta.read_only_fields + ("status", "last_seen_at")


class TelemetrySourceCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160, trim_whitespace=True)
    source_type = serializers.ChoiceField(choices=SourceType.choices)
    description = serializers.CharField(required=False, allow_blank=True)
    sampling_rate = serializers.DecimalField(max_digits=5, decimal_places=4, required=False, default=1)
    retention_days = serializers.IntegerField(min_value=1, max_value=3650, required=False, default=90)
    daily_event_quota = serializers.IntegerField(min_value=1, required=False, default=1_000_000)
    redaction_fields = serializers.ListField(child=serializers.CharField(max_length=120), required=False, default=list)


class TelemetrySourceUpdateSerializer(TelemetrySourceCreateSerializer):
    name = serializers.CharField(max_length=160, trim_whitespace=True, required=False)
    source_type = serializers.ChoiceField(choices=SourceType.choices, required=False)
    is_active = serializers.BooleanField(required=False)


class EnvironmentSerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = MonitoringEnvironment
        fields = ("id", "name", "slug", "kind", "description", "is_active", "created_at", "updated_at")
        read_only_fields = TenantReadOnlySerializer.Meta.read_only_fields


class ServiceSerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = MonitoredService
        fields = (
            "id",
            "environment",
            "source",
            "name",
            "slug",
            "namespace",
            "version",
            "owner",
            "language",
            "status",
            "last_seen_at",
            "attributes",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = TenantReadOnlySerializer.Meta.read_only_fields + ("status", "last_seen_at")


class MetricDefinitionListSerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = Metric
        fields = (
            "id",
            "metric_name",
            "display_name",
            "metric_type",
            "namespace",
            "unit",
            "service",
            "environment",
            "expected_interval_seconds",
            "retention_days",
            "is_active",
            "created_at",
        )
        read_only_fields = TenantReadOnlySerializer.Meta.read_only_fields


class MetricDefinitionDetailSerializer(MetricDefinitionListSerializer):
    class Meta(MetricDefinitionListSerializer.Meta):
        fields = MetricDefinitionListSerializer.Meta.fields + ("source", "description", "default_tags", "updated_at")


class MetricDefinitionCreateSerializer(serializers.Serializer):
    metric_name = serializers.RegexField(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$", max_length=255)
    metric_type = serializers.ChoiceField(choices=MetricType.choices)
    description = serializers.CharField(required=False, allow_blank=True)
    unit = serializers.CharField(required=False, default="1", max_length=40)
    source_id = serializers.UUIDField(required=False, allow_null=True)
    service_id = serializers.UUIDField(required=False, allow_null=True)
    environment_id = serializers.UUIDField(required=False, allow_null=True)
    namespace = serializers.CharField(required=False, default="custom", max_length=120)
    expected_interval_seconds = serializers.IntegerField(required=False, default=60, min_value=1)
    retention_days = serializers.IntegerField(required=False, default=90, min_value=1, max_value=3650)
    default_tags = serializers.DictField(child=serializers.CharField(max_length=255), required=False, default=dict)


class MetricRecordSerializer(serializers.Serializer):
    metric_name = serializers.CharField(max_length=255)
    value = serializers.DecimalField(max_digits=20, decimal_places=6)
    metric_type = serializers.ChoiceField(choices=MetricType.choices, required=False, default=MetricType.GAUGE)
    tags = serializers.DictField(child=serializers.CharField(max_length=255), required=False, default=dict)
    timestamp = serializers.DateTimeField(required=False)
    source = serializers.CharField(max_length=100, required=False, allow_blank=True)
    source_module = serializers.CharField(max_length=100, required=False, allow_blank=True)
    source_id = serializers.UUIDField(required=False, allow_null=True)
    session_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    idempotency_key = serializers.CharField(max_length=160, required=False, allow_blank=True)
    trace_id = serializers.RegexField(r"^[0-9a-f]{32}$", required=False, allow_blank=True)
    span_id = serializers.RegexField(r"^[0-9a-f]{16}$", required=False, allow_blank=True)


class MetricDataPointSerializer(TenantReadOnlySerializer):
    metric_name = serializers.CharField(source="metric.metric_name", read_only=True)

    class Meta(TenantReadOnlySerializer.Meta):
        model = MetricDataPoint
        fields = (
            "id",
            "metric_name",
            "value",
            "tags",
            "timestamp",
            "source_module",
            "session_id",
            "trace_id",
            "span_id",
            "created_at",
        )
        read_only_fields = fields


class MetricBatchSerializer(serializers.Serializer):
    data_points = MetricRecordSerializer(many=True, max_length=1000)
    atomic = serializers.BooleanField(required=False, default=False)


class MetricQuerySerializer(serializers.Serializer):
    metric_name = serializers.CharField(max_length=255)
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    aggregation = serializers.ChoiceField(
        choices=("avg", "sum", "min", "max", "count", "p50", "p95", "p99"), required=False, default="avg"
    )
    interval = serializers.ChoiceField(choices=("auto", "1m", "5m", "15m", "1h", "1d"), required=False, default="auto")
    tags = serializers.CharField(required=False, allow_blank=True)

    def validate_tags(self, value: str) -> dict[str, str]:
        if not value:
            return {}
        result: dict[str, str] = {}
        for pair in value.split(","):
            key, separator, item = pair.partition("=")
            if not separator or not key.strip():
                raise serializers.ValidationError("Use comma-separated key=value tags.")
            result[key.strip()] = item.strip()
        return result


class MetricSummaryQuerySerializer(serializers.Serializer):
    metric_names = serializers.CharField()
    period = serializers.ChoiceField(choices=("1h", "24h", "7d", "30d"))


class LogIngestSerializer(serializers.Serializer):
    source_id = serializers.UUIDField()
    service_id = serializers.UUIDField(required=False, allow_null=True)
    environment_id = serializers.UUIDField(required=False, allow_null=True)
    timestamp = serializers.DateTimeField(required=False)
    level = serializers.ChoiceField(
        choices=("trace", "debug", "info", "warn", "warning", "error", "fatal"), default="info"
    )
    message = serializers.CharField(max_length=32_000)
    attributes = serializers.DictField(required=False, default=dict)
    trace_id = serializers.RegexField(r"^[0-9a-f]{32}$", required=False, allow_blank=True)
    span_id = serializers.RegexField(r"^[0-9a-f]{16}$", required=False, allow_blank=True)
    correlation_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    idempotency_key = serializers.CharField(max_length=160, required=False, allow_blank=True)


class LogEntrySerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = LogEntry
        fields = (
            "id",
            "source",
            "service",
            "environment",
            "timestamp",
            "observed_at",
            "level",
            "message",
            "attributes",
            "trace_id",
            "span_id",
            "correlation_id",
            "created_at",
        )
        read_only_fields = fields


class SpanIngestSerializer(serializers.Serializer):
    service_id = serializers.UUIDField(required=False, allow_null=True)
    span_id = serializers.RegexField(r"^[0-9a-f]{16}$")
    parent_span_id = serializers.RegexField(r"^[0-9a-f]{16}$", required=False, allow_blank=True)
    name = serializers.CharField(max_length=240)
    kind = serializers.CharField(max_length=24, required=False, default="internal")
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField()
    duration_ms = serializers.FloatField(min_value=0)
    status = serializers.ChoiceField(choices=("unset", "ok", "error"), default="unset")
    attributes = serializers.DictField(required=False, default=dict)
    events = serializers.ListField(required=False, default=list)


class TraceIngestSerializer(serializers.Serializer):
    source_id = serializers.UUIDField()
    service_id = serializers.UUIDField()
    environment_id = serializers.UUIDField(required=False, allow_null=True)
    trace_id = serializers.RegexField(r"^[0-9a-f]{32}$")
    name = serializers.CharField(max_length=240)
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField()
    duration_ms = serializers.FloatField(min_value=0)
    status = serializers.ChoiceField(choices=("unset", "ok", "error"), default="unset")
    attributes = serializers.DictField(required=False, default=dict)
    sampled = serializers.BooleanField(required=False, default=True)
    spans = SpanIngestSerializer(many=True, max_length=10_000)


class SpanSerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = Span
        fields = (
            "id",
            "span_id",
            "parent_span_id",
            "service",
            "name",
            "kind",
            "started_at",
            "ended_at",
            "duration_ms",
            "status",
            "attributes",
            "events",
        )
        read_only_fields = fields


class TraceSerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = Trace
        fields = (
            "id",
            "trace_id",
            "source",
            "service",
            "environment",
            "name",
            "started_at",
            "ended_at",
            "duration_ms",
            "status",
            "attributes",
            "sampled",
            "span_count",
            "error_span_count",
            "created_at",
        )
        read_only_fields = fields


class DashboardSerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = Dashboard
        fields = (
            "id",
            "name",
            "description",
            "layout",
            "variables",
            "refresh_interval_seconds",
            "is_default",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = TenantReadOnlySerializer.Meta.read_only_fields


class AlertRuleListSerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = AlertRule
        fields = (
            "id",
            "name",
            "metric_name",
            "condition",
            "threshold",
            "evaluation_window_minutes",
            "cooldown_minutes",
            "severity",
            "action",
            "is_active",
            "last_evaluated_at",
            "created_at",
        )
        read_only_fields = TenantReadOnlySerializer.Meta.read_only_fields + ("last_evaluated_at",)


class AlertRuleDetailSerializer(AlertRuleListSerializer):
    class Meta(AlertRuleListSerializer.Meta):
        fields = AlertRuleListSerializer.Meta.fields + (
            "description",
            "metric",
            "aggregation",
            "evaluation_interval_seconds",
            "group_by_tags",
            "auto_resolve",
            "updated_at",
        )


class AlertRuleCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=180)
    metric_name = serializers.CharField(max_length=255)
    condition = AlertConditionField()
    threshold = serializers.DecimalField(max_digits=20, decimal_places=6, required=False, allow_null=True)
    evaluation_window_minutes = serializers.IntegerField(min_value=1, max_value=1440, default=5, required=False)
    cooldown_minutes = serializers.IntegerField(min_value=1, max_value=10080, default=15, required=False)
    severity = serializers.ChoiceField(choices=Severity.choices, default=Severity.WARNING, required=False)
    action = serializers.DictField()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        condition = attrs.get("condition", getattr(self.instance, "condition", None))
        threshold = attrs.get("threshold", getattr(self.instance, "threshold", None))
        if condition == AlertCondition.ABSENCE and threshold is not None:
            raise serializers.ValidationError({"threshold": "Absence alerts do not use a threshold."})
        if condition is not None and condition != AlertCondition.ABSENCE and threshold is None:
            raise serializers.ValidationError({"threshold": "Threshold is required."})
        return attrs


class AlertRuleUpdateSerializer(AlertRuleCreateSerializer):
    name = serializers.CharField(max_length=180, required=False)
    metric_name = serializers.CharField(read_only=True)
    condition = AlertConditionField(required=False)
    action = serializers.DictField(required=False)


class AlertSerializer(TenantReadOnlySerializer):
    notification_outcomes = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta(TenantReadOnlySerializer.Meta):
        model = Alert
        fields = (
            "id",
            "alert_rule",
            "metric_name",
            "triggered_value",
            "threshold",
            "condition",
            "severity",
            "status",
            "triggered_at",
            "last_observed_at",
            "occurrence_count",
            "acknowledged_at",
            "acknowledged_by",
            "resolved_at",
            "resolved_by",
            "resolution_note",
            "title",
            "description",
            "context",
            "notification_outcomes",
        )
        read_only_fields = fields


class AlertAcknowledgeSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class AlertResolveSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class SLADefinitionSerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = SLADefinition
        fields = (
            "id",
            "name",
            "description",
            "service_name",
            "metric_name",
            "target",
            "window",
            "comparison",
            "expected_interval_seconds",
            "version",
            "previous_version",
            "effective_from",
            "effective_until",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = TenantReadOnlySerializer.Meta.read_only_fields + (
            "version",
            "previous_version",
            "effective_from",
            "effective_until",
        )


class SLADefinitionCreateSerializer(serializers.Serializer):
    service_name = serializers.CharField(max_length=255)
    metric_name = serializers.CharField(max_length=255)
    target = serializers.DecimalField(max_digits=10, decimal_places=4, min_value=0)
    window = serializers.ChoiceField(choices=SLAWindow.choices)
    comparison = serializers.ChoiceField(choices=((Comparison.GTE, "gte"), (Comparison.LTE, "lte")))
    expected_interval_seconds = serializers.IntegerField(min_value=1, max_value=86400, required=False, default=60)


class SLADefinitionUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=180, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    target = serializers.DecimalField(max_digits=10, decimal_places=4, min_value=0, required=False)
    window = serializers.ChoiceField(choices=SLAWindow.choices, required=False)
    comparison = serializers.ChoiceField(choices=((Comparison.GTE, "gte"), (Comparison.LTE, "lte")), required=False)
    expected_interval_seconds = serializers.IntegerField(min_value=1, max_value=86400, required=False)


class ComplianceQuerySerializer(serializers.Serializer):
    period = serializers.ChoiceField(choices=("current", "previous", "custom"), required=False, default="current")
    start = serializers.DateTimeField(required=False)
    end = serializers.DateTimeField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("period") == "custom" and (not attrs.get("start") or not attrs.get("end")):
            raise serializers.ValidationError("Custom compliance requires start and end.")
        return attrs


class ComplianceSerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = SLAComplianceRecord
        fields = (
            "id",
            "sla",
            "period_start",
            "period_end",
            "actual_value",
            "target_value",
            "is_compliant",
            "breach_duration_minutes",
            "expected_samples",
            "observed_samples",
            "compliant_samples",
            "missing_samples",
            "compliance_percentage",
            "status",
            "evidence",
            "created_at",
        )
        read_only_fields = fields


class SLAReportCreateSerializer(serializers.Serializer):
    period = serializers.ChoiceField(choices=("rolling_24h", "7d", "calendar_month"))
    format = serializers.ChoiceField(choices=("json", "csv", "pdf"), default="json", required=False)


class SLAReportSerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = SLAReport
        fields = (
            "id",
            "period_start",
            "period_end",
            "status",
            "summary",
            "artifact_ref",
            "artifact_sha256",
            "generated_by",
            "generated_at",
            "error_code",
            "created_at",
        )
        read_only_fields = fields


class SLOSerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = ServiceLevelObjective
        fields = (
            "id",
            "name",
            "description",
            "service",
            "indicator_metric",
            "comparison",
            "threshold",
            "objective_percentage",
            "window_days",
            "expected_interval_seconds",
            "error_budget_minutes",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = TenantReadOnlySerializer.Meta.read_only_fields


class ErrorBudgetSerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = ErrorBudgetSnapshot
        fields = (
            "id",
            "slo",
            "period_start",
            "period_end",
            "budget_minutes",
            "consumed_minutes",
            "remaining_minutes",
            "burn_rate",
            "status",
            "created_at",
        )
        read_only_fields = fields


class ExtensionSerializer(TenantReadOnlySerializer):
    class Meta(TenantReadOnlySerializer.Meta):
        model = MonitoringExtension
        fields = (
            "id",
            "extension_key",
            "provider",
            "schema_version",
            "metric_namespaces",
            "semantic_attributes",
            "dashboard_templates",
            "slo_packs",
            "alert_rule_templates",
            "drill_down_links",
            "event_consumers",
            "is_active",
            "created_at",
        )
        read_only_fields = fields
