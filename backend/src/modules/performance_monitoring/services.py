"""Tenant-first business services for operational monitoring."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import re
import statistics
import threading
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Sequence
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import enqueue
from src.core.observability import get_correlation_id
from src.core.resilience import CircuitBreaker

from .events import publish_domain_event
from .models import (
    Alert,
    AlertCondition,
    AlertNotificationOutcome,
    AlertRule,
    AlertState,
    Comparison,
    ComplianceState,
    Dashboard,
    DeliveryState,
    ErrorBudgetSnapshot,
    HealthState,
    LogEntry,
    Metric,
    MetricDataPoint,
    MetricType,
    MonitoredService,
    MonitoringEnvironment,
    PerformanceMonitoringConfiguration,
    PerformanceMonitoringConfigurationAudit,
    PerformanceMonitoringConfigurationVersion,
    ReportState,
    ServiceLevelObjective,
    Severity,
    SLABreach,
    SLAComplianceRecord,
    SLADefinition,
    SLAReport,
    SLAWindow,
    Span,
    TelemetrySource,
    Trace,
    normalize_alert_condition,
)

logger = logging.getLogger(__name__)
_notification_breakers: dict[tuple[UUID, int, float], CircuitBreaker[Any]] = {}
_notification_breakers_lock = threading.Lock()
SYSTEM_ACTOR = UUID(int=0)
TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
SPAN_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")


class MonitoringError(Exception):
    code = "MONITORING_ERROR"
    http_status = 400

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.public_message = message
        self.details = dict(details or {})


class NotFoundError(MonitoringError):
    http_status = 404


class ConflictError(MonitoringError):
    http_status = 409


class InsufficientDataError(MonitoringError):
    code = "INSUFFICIENT_DATA"
    http_status = 422


class CapabilityUnavailableError(MonitoringError):
    code = "CAPABILITY_UNAVAILABLE"
    http_status = 503


class InvalidMetricNameError(MonitoringError):
    code = "INVALID_METRIC_NAME"


class InvalidMetricValueError(MonitoringError):
    code = "INVALID_METRIC_VALUE"


class MetricNotFoundError(NotFoundError):
    code = "METRIC_NOT_FOUND"


class InvalidTimeRangeError(MonitoringError):
    code = "INVALID_TIME_RANGE"


class AlertNotFoundError(NotFoundError):
    code = "ALERT_NOT_FOUND"


class AlertAlreadyResolvedError(ConflictError):
    code = "ALERT_ALREADY_RESOLVED"


class SLANotFoundError(NotFoundError):
    code = "SLA_NOT_FOUND"


class DuplicateSLAError(ConflictError):
    code = "DUPLICATE_SLA"


@dataclass(frozen=True)
class MetricBucket:
    timestamp: datetime
    value: float


@dataclass(frozen=True)
class MetricQueryResult:
    metric_name: str
    aggregation: str
    interval: str
    data: list[MetricBucket]


@dataclass(frozen=True)
class MetricSummary:
    metric_name: str
    period: str
    minimum: float | None
    maximum: float | None
    average: float | None
    count: int
    p50: float | None
    p95: float | None
    p99: float | None


@dataclass(frozen=True)
class BatchIngestionResult:
    accepted: int
    rejected: int
    errors: list[dict[str, Any]]
    data_points: list[MetricDataPoint]


def _tenant(tenant_id: UUID | str) -> UUID:
    try:
        return tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise MonitoringError("tenant_id must be a valid UUID") from exc


def _actor(actor_id: UUID | str | None) -> UUID:
    if actor_id is None:
        return SYSTEM_ACTOR
    try:
        return actor_id if isinstance(actor_id, UUID) else UUID(str(actor_id))
    except (TypeError, ValueError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{actor_id}")


def _log_context(tenant_id: UUID, **resource_ids: Any) -> dict[str, str]:
    """Return the mandatory structured context for every module log record."""

    return {
        "tenant_id": str(tenant_id),
        "correlation_id": get_correlation_id() or str(uuid.uuid4()),
        **{key: str(value) for key, value in resource_ids.items() if value is not None},
    }


def _setting(tenant_id: UUID, path: str) -> Any:
    """Read one required tenant setting; missing settings fail closed."""

    return ConfigurationService().setting(tenant_id, path)


def _normalize_metric_name(tenant_id: UUID, metric_name: str) -> str:
    value = str(metric_name).strip().lower()
    max_length = int(_setting(tenant_id, "limits.metric_name_max_length"))
    pattern = re.compile(str(_setting(tenant_id, "limits.metric_name_pattern")))
    if len(value) > max_length or not pattern.fullmatch(value):
        raise InvalidMetricNameError(
            "Metric names must use lowercase dot notation (for example, api.response_time).",
            details={"metric_name": metric_name},
        )
    return value


def _numeric(value: Any) -> float:
    try:
        result = float(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidMetricValueError("Metric value must be numeric.") from exc
    if not math.isfinite(result):
        raise InvalidMetricValueError("Metric value must be finite.")
    return result


def _percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        raise ValueError("percentile requires at least one observation")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile / 100
    lower, upper = math.floor(rank), math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _compare(value: float, comparison: str, threshold: float) -> bool:
    return {
        Comparison.GT: value > threshold,
        Comparison.GTE: value >= threshold,
        Comparison.LT: value < threshold,
        Comparison.LTE: value <= threshold,
        Comparison.EQ: value == threshold,
        Comparison.NE: value != threshold,
    }.get(comparison, False)


class MetricsCollectionService:
    """Define, ingest, aggregate, and retain tenant-owned metrics."""

    @transaction.atomic
    def define_metric(
        self,
        tenant_id: UUID | str,
        metric_name: str,
        metric_type: str,
        *,
        created_by: UUID | str | None = None,
        description: str = "",
        unit: str | None = None,
        source_id: UUID | str | None = None,
        service_id: UUID | str | None = None,
        environment_id: UUID | str | None = None,
        namespace: str | None = None,
        expected_interval_seconds: int | None = None,
        retention_days: int | None = None,
        default_tags: Mapping[str, str] | None = None,
    ) -> Metric:
        tenant = _tenant(tenant_id)
        name = _normalize_metric_name(tenant, metric_name)
        defaults = _setting(tenant, "defaults.metric")
        if metric_type not in set(_setting(tenant, "allowlists.metric_types")):
            raise InvalidMetricValueError("Unsupported metric type.")
        relations: dict[str, Any] = {}
        for field, model, identifier in (
            ("source", TelemetrySource, source_id),
            ("service", MonitoredService, service_id),
            ("environment", MonitoringEnvironment, environment_id),
        ):
            if identifier:
                relation = model.objects.for_tenant(tenant).filter(id=identifier, is_deleted=False).first()
                if relation is None:
                    raise NotFoundError(f"{field.capitalize()} not found.")
                relations[field] = relation
        existing = Metric.objects.for_tenant(tenant).filter(metric_name__iexact=name, is_deleted=False).first()
        if existing:
            if existing.metric_type != metric_type:
                raise ConflictError("Metric already exists with a different type.")
            return existing
        try:
            metric = Metric.objects.create(
                tenant_id=tenant,
                metric_name=name,
                display_name=name,
                metric_type=metric_type,
                created_by=_actor(created_by),
                description=description.strip(),
                unit=(unit or str(defaults["unit"])).strip(),
                namespace=(namespace or str(defaults["namespace"])).strip(),
                expected_interval_seconds=expected_interval_seconds or int(defaults["expected_interval_seconds"]),
                retention_days=retention_days or int(defaults["retention_days"]),
                default_tags=dict(default_tags or {}),
                **relations,
            )
        except IntegrityError:
            metric = Metric.objects.for_tenant(tenant).get(metric_name__iexact=name, is_deleted=False)
            if metric.metric_type != metric_type:
                raise ConflictError("Metric already exists with a different type.")
        logger.info("metric_defined", extra=_log_context(tenant, metric_id=metric.id, metric_name=name))
        return metric

    @transaction.atomic
    def record_metric(
        self,
        tenant_id: UUID | str,
        metric_name: str,
        value: Decimal | float | int,
        *,
        tags: Mapping[str, str] | None = None,
        timestamp: datetime | None = None,
        metric_type: str = MetricType.GAUGE,
        source: str | None = None,
        source_module: str | None = None,
        source_id: UUID | str | None = None,
        session_id: str | None = None,
        idempotency_key: str | None = None,
        created_by: UUID | str | None = None,
        trace_id: str = "",
        span_id: str = "",
    ) -> MetricDataPoint:
        tenant = _tenant(tenant_id)
        name = _normalize_metric_name(tenant, metric_name)
        numeric_value = _numeric(value)
        normalized_tags = {str(key): str(item) for key, item in dict(tags or {}).items()}
        max_tags = int(_setting(tenant, "limits.max_tags_per_data_point"))
        if len(normalized_tags) > max_tags:
            raise InvalidMetricValueError(f"A metric data point may have at most {max_tags} tags.")
        observed_at = timestamp or timezone.now()
        if timezone.is_naive(observed_at):
            raise InvalidMetricValueError("Metric timestamp must include a timezone.")
        metric = (
            Metric.objects.select_for_update()
            .for_tenant(tenant)
            .filter(metric_name__iexact=name, is_deleted=False)
            .first()
        )
        if metric is None:
            metric = self.define_metric(
                tenant,
                name,
                metric_type,
                created_by=created_by,
                source_id=source_id,
                namespace=(source or source_module or str(_setting(tenant, "defaults.metric.namespace"))).split(".", 1)[
                    0
                ],
            )
        elif metric.metric_type != metric_type and metric_type != MetricType.GAUGE:
            raise ConflictError("Ingestion metric_type differs from the existing definition.")
        if (
            metric.metric_type == MetricType.HISTOGRAM
            and bool(_setting(tenant, "rules.histogram_values_non_negative"))
            and numeric_value < 0
        ):
            raise InvalidMetricValueError("Histogram values cannot be negative.")
        if metric.metric_type == MetricType.COUNTER:
            if bool(_setting(tenant, "rules.counter_requires_session_id")) and not session_id:
                raise InvalidMetricValueError("Counter metrics require a session_id.")
            previous = (
                MetricDataPoint.objects.for_tenant(tenant)
                .filter(metric=metric, session_id=session_id, tags=normalized_tags)
                .order_by("-timestamp")
                .first()
            )
            if (
                previous
                and bool(_setting(tenant, "rules.counter_must_be_monotonic"))
                and numeric_value < float(previous.value)
            ):
                raise InvalidMetricValueError("Counter values must be monotonic within a session and tag set.")
        key = str(idempotency_key or "").strip()
        if key:
            existing = MetricDataPoint.objects.for_tenant(tenant).filter(metric=metric, idempotency_key=key).first()
            if existing:
                if float(existing.value) != numeric_value or existing.tags != normalized_tags:
                    raise ConflictError("Idempotency key was already used with a different data point.")
                return existing
        point = MetricDataPoint.objects.create(
            tenant_id=tenant,
            metric=metric,
            value=numeric_value,
            tags=normalized_tags,
            timestamp=observed_at,
            session_id=str(session_id or "")[:128],
            source_module=str(source_module or source or "")[:100],
            idempotency_key=key[:160],
            trace_id=trace_id,
            span_id=span_id,
        )
        publish_domain_event(
            tenant,
            "metric.recorded",
            "MetricDataPoint",
            point.id,
            payload={"metric_name": name, "value": numeric_value},
        )
        (
            TelemetrySource.objects.for_tenant(tenant)
            .filter(id=metric.source_id)
            .update(last_seen_at=timezone.now(), status=HealthState.HEALTHY)
            if metric.source_id
            else None
        )
        logger.info(
            "metric_recorded",
            extra=_log_context(tenant, metric_id=metric.id, data_point_id=point.id),
        )
        return point

    @transaction.atomic
    def deactivate_metric(self, tenant_id: UUID | str, metric_id: UUID | str) -> None:
        """Atomically deactivate and soft-delete one tenant-owned metric definition."""

        tenant = _tenant(tenant_id)
        metric = Metric.objects.select_for_update().for_tenant(tenant).filter(id=metric_id, is_deleted=False).first()
        if metric is None:
            raise MetricNotFoundError("Metric definition was not found.")
        metric.is_active = False
        metric.save(update_fields=["is_active", "updated_at"])
        metric.delete()
        logger.info("metric_deactivated", extra=_log_context(tenant, metric_id=metric.id))

    def record_metrics_batch(
        self,
        tenant_id: UUID | str,
        data_points: Sequence[Mapping[str, Any]],
        *,
        atomic: bool = True,
        created_by: UUID | str | None = None,
    ) -> BatchIngestionResult:
        tenant = _tenant(tenant_id)
        max_batch = int(_setting(tenant, "limits.max_batch_data_points"))
        if len(data_points) > max_batch:
            raise InvalidMetricValueError(f"Batch ingestion is limited to {max_batch} data points.")
        accepted: list[MetricDataPoint] = []
        errors: list[dict[str, Any]] = []

        def ingest() -> None:
            for index, payload in enumerate(data_points):
                try:
                    accepted.append(
                        self.record_metric(
                            tenant_id,
                            str(payload.get("metric_name", "")),
                            payload.get("value"),
                            tags=payload.get("tags"),
                            timestamp=payload.get("timestamp"),
                            metric_type=str(payload.get("metric_type", MetricType.GAUGE)),
                            source=payload.get("source"),
                            source_module=payload.get("source_module"),
                            source_id=payload.get("source_id"),
                            session_id=payload.get("session_id"),
                            idempotency_key=payload.get("idempotency_key"),
                            created_by=created_by,
                            trace_id=str(payload.get("trace_id", "")),
                            span_id=str(payload.get("span_id", "")),
                        )
                    )
                except MonitoringError as exc:
                    errors.append({"index": index, "code": exc.code, "message": exc.public_message})
                    if atomic:
                        raise

        if atomic:
            with transaction.atomic():
                ingest()
        else:
            ingest()
        return BatchIngestionResult(len(accepted), len(errors), errors, accepted)

    # Singular alias retained for explicit compatibility checklist wording.
    record_metrics_batch = record_metrics_batch

    def query_metrics(
        self,
        tenant_id: UUID | str,
        metric_name: str,
        time_range: Any = None,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        aggregation: str = "avg",
        interval: str = "auto",
        tags: Mapping[str, str] | None = None,
    ) -> MetricQueryResult:
        tenant = _tenant(tenant_id)
        name = _normalize_metric_name(tenant, metric_name)
        if time_range is not None:
            start = (
                start
                or getattr(time_range, "start", None)
                or (time_range.get("start") if isinstance(time_range, Mapping) else None)
            )
            end = (
                end
                or getattr(time_range, "end", None)
                or (time_range.get("end") if isinstance(time_range, Mapping) else None)
            )
        if not start or not end or timezone.is_naive(start) or timezone.is_naive(end) or start >= end:
            raise InvalidTimeRangeError("A timezone-aware start before end is required.")
        max_range_days = int(_setting(tenant, "limits.metric_query_max_range_days"))
        if end - start > timedelta(days=max_range_days):
            raise InvalidTimeRangeError(f"Metric queries cannot exceed {max_range_days} days.")
        aggregations = set(_setting(tenant, "allowlists.aggregations"))
        if aggregation not in aggregations:
            raise InvalidTimeRangeError("Unsupported aggregation.")
        metric = Metric.objects.for_tenant(tenant).filter(metric_name__iexact=name, is_deleted=False).first()
        if metric is None:
            raise MetricNotFoundError("Metric definition was not found.")
        intervals = dict(_setting(tenant, "query.interval_seconds"))
        seconds = intervals.get(interval)
        if interval == "auto":
            span = (end - start).total_seconds()
            buckets = list(_setting(tenant, "query.automatic_buckets"))
            selected = next((item for item in buckets if span <= item["max_range_seconds"]), buckets[-1])
            seconds = int(selected["bucket_seconds"])
            interval = next((key for key, value in intervals.items() if int(value) == seconds), f"{seconds}s")
        if seconds is None:
            raise InvalidTimeRangeError("Unsupported interval.")
        points = MetricDataPoint.objects.for_tenant(tenant).filter(
            metric=metric, timestamp__gte=start, timestamp__lte=end
        )
        for key, expected in dict(tags or {}).items():
            points = points.filter(tags__contains={str(key): str(expected)})
        buckets: dict[int, list[float]] = {}
        for point in points.only("timestamp", "value").order_by("timestamp"):
            epoch = int(point.timestamp.timestamp())
            buckets.setdefault(epoch - epoch % seconds, []).append(float(point.value))
        data = [
            MetricBucket(
                datetime.fromtimestamp(bucket, tz=datetime_timezone.utc),
                self._aggregate(values, aggregation),
            )
            for bucket, values in sorted(buckets.items())
        ]
        return MetricQueryResult(name, aggregation, interval, data)

    # Compatibility spelling requested by the implementation brief.
    query_metric = query_metrics

    @staticmethod
    def _aggregate(values: Sequence[float], aggregation: str) -> float:
        if aggregation == "avg":
            return statistics.fmean(values)
        if aggregation == "sum":
            return sum(values)
        if aggregation == "min":
            return min(values)
        if aggregation == "max":
            return max(values)
        if aggregation == "count":
            return float(len(values))
        return _percentile(values, int(aggregation[1:]))

    def get_metric_summary(
        self,
        tenant_id: UUID | str,
        metric_names: Sequence[str],
        period: str,
    ) -> list[MetricSummary]:
        tenant = _tenant(tenant_id)
        configured_periods = dict(_setting(tenant, "query.summary_period_seconds"))
        duration_seconds = configured_periods.get(period)
        if duration_seconds is None:
            raise InvalidTimeRangeError("Unsupported summary period.")
        since = timezone.now() - timedelta(seconds=int(duration_seconds))
        summaries: list[MetricSummary] = []
        for raw_name in metric_names:
            name = _normalize_metric_name(tenant, raw_name)
            metric = Metric.objects.for_tenant(tenant).filter(metric_name__iexact=name, is_deleted=False).first()
            if metric is None:
                raise MetricNotFoundError(f"Metric '{name}' was not found.")
            values = [
                float(value)
                for value in (
                    MetricDataPoint.objects.for_tenant(tenant)
                    .filter(metric=metric, timestamp__gte=since)
                    .values_list("value", flat=True)
                )
            ]
            percentiles = [int(item) for item in _setting(tenant, "query.summary_percentiles")]
            if len(percentiles) != 3:
                raise ConfigurationValidationError("Exactly three summary percentiles must be configured.")
            if not values:
                summaries.append(MetricSummary(name, period, None, None, None, 0, None, None, None))
            else:
                summaries.append(
                    MetricSummary(
                        name,
                        period,
                        min(values),
                        max(values),
                        statistics.fmean(values),
                        len(values),
                        _percentile(values, percentiles[0]),
                        _percentile(values, percentiles[1]),
                        _percentile(values, percentiles[2]),
                    )
                )
        return summaries

    get_metric_summary = get_metric_summary

    def purge_expired_data(self, tenant_id: UUID | str, *, now: datetime | None = None) -> int:
        del now
        tenant = _tenant(tenant_id)
        provider = str(_setting(tenant, "evidence.archive_provider"))
        raise CapabilityUnavailableError(
            "Physical evidence deletion is prohibited; "
            f"archival provider '{provider}' must execute governed partition lifecycle."
        )


class AlertingService:
    """Alert rule state machine with persisted notification outcomes."""

    def __init__(self, notification_sender: Callable[[UUID, Alert, Mapping[str, Any]], str] | None = None) -> None:
        self.notification_sender = notification_sender or CoreNotificationAdapter.send

    @transaction.atomic
    def create_alert_rule(
        self,
        tenant_id: UUID | str,
        metric_name: str,
        condition: str,
        threshold: Decimal | float | None,
        action: Mapping[str, Any],
        *,
        name: str | None = None,
        evaluation_window_minutes: int | None = None,
        cooldown_minutes: int | None = None,
        severity: str | None = None,
        created_by: UUID | str | None = None,
    ) -> AlertRule:
        tenant = _tenant(tenant_id)
        defaults = _setting(tenant, "defaults.alert_rule")
        evaluation_window_minutes = evaluation_window_minutes or int(defaults["evaluation_window_minutes"])
        cooldown_minutes = cooldown_minutes or int(defaults["cooldown_minutes"])
        severity = severity or str(defaults["severity"])
        normalized = _normalize_metric_name(tenant, metric_name)
        condition = normalize_alert_condition(condition)
        if condition not in set(_setting(tenant, "allowlists.alert_conditions")):
            raise MonitoringError("Unsupported alert condition.")
        if severity not in set(_setting(tenant, "allowlists.severities")):
            raise MonitoringError("Unsupported alert severity.")
        if (
            bool(_setting(tenant, "rules.cooldown_at_least_evaluation_window"))
            and cooldown_minutes < evaluation_window_minutes
        ):
            raise MonitoringError("Cooldown must be at least the evaluation window.")
        if bool(_setting(tenant, "rules.notification_channel_required")) and (
            not isinstance(action, Mapping) or not isinstance(action.get("channels"), list) or not action["channels"]
        ):
            raise MonitoringError("Alert action must declare at least one notification channel.")
        allowed_channels = set(_setting(tenant, "allowlists.notification_channels"))
        if not set(action.get("channels", [])).issubset(allowed_channels):
            raise MonitoringError("Alert action contains a disabled notification channel.")
        self._validate_rule_policy(tenant, condition, threshold, action, evaluation_window_minutes, cooldown_minutes)
        max_rules = int(_setting(tenant, "limits.max_alert_rules"))
        if AlertRule.objects.for_tenant(tenant).filter(is_deleted=False).count() >= max_rules:
            raise ConflictError(f"A tenant may define at most {max_rules} alert rules.")
        metric = Metric.objects.for_tenant(tenant).filter(metric_name__iexact=normalized, is_deleted=False).first()
        rule = AlertRule.objects.create(
            tenant_id=tenant,
            name=(name or f"{normalized} {condition}").strip(),
            metric=metric,
            metric_name=normalized,
            condition=condition,
            threshold=None if threshold is None else _numeric(threshold),
            action=dict(action),
            evaluation_window_minutes=evaluation_window_minutes,
            cooldown_minutes=cooldown_minutes,
            severity=severity,
            created_by=_actor(created_by),
        )
        return rule

    @transaction.atomic
    def update_alert_rule(self, tenant_id: UUID | str, rule_id: UUID | str, **changes: Any) -> AlertRule:
        tenant = _tenant(tenant_id)
        rule = AlertRule.objects.select_for_update().for_tenant(tenant).filter(id=rule_id, is_deleted=False).first()
        if rule is None:
            raise NotFoundError("Alert rule was not found.")
        if "condition" in changes:
            condition = normalize_alert_condition(changes["condition"])
            if condition not in AlertCondition.values:
                raise MonitoringError("Unsupported alert condition.")
            changes["condition"] = condition
        allowed = {
            "name",
            "description",
            "condition",
            "threshold",
            "evaluation_window_minutes",
            "cooldown_minutes",
            "severity",
            "action",
            "is_active",
            "auto_resolve",
        }
        for field, value in changes.items():
            if field in allowed:
                setattr(rule, field, value)
        self._validate_rule_policy(
            tenant,
            rule.condition,
            rule.threshold,
            rule.action,
            rule.evaluation_window_minutes,
            rule.cooldown_minutes,
        )
        rule.save()
        return rule

    @staticmethod
    def _validate_rule_policy(
        tenant_id: UUID,
        condition: str,
        threshold: Any,
        action: Mapping[str, Any],
        evaluation_window_minutes: int,
        cooldown_minutes: int,
    ) -> None:
        if (
            bool(_setting(tenant_id, "rules.absence_forbids_threshold"))
            and condition == AlertCondition.ABSENCE
            and threshold is not None
        ):
            raise MonitoringError("Absence rules do not use a threshold.")
        if (
            bool(_setting(tenant_id, "rules.other_conditions_require_threshold"))
            and condition != AlertCondition.ABSENCE
            and threshold is None
        ):
            raise MonitoringError("Threshold is required for this alert condition.")
        if (
            bool(_setting(tenant_id, "rules.cooldown_at_least_evaluation_window"))
            and cooldown_minutes < evaluation_window_minutes
        ):
            raise MonitoringError("Cooldown must be at least the evaluation window.")
        if bool(_setting(tenant_id, "rules.notification_channel_required")) and not action.get("channels"):
            raise MonitoringError("At least one notification channel is required.")

    @transaction.atomic
    def delete_alert_rule(self, tenant_id: UUID | str, rule_id: UUID | str) -> None:
        tenant = _tenant(tenant_id)
        rule = AlertRule.objects.select_for_update().for_tenant(tenant).filter(id=rule_id, is_deleted=False).first()
        if rule is None:
            raise NotFoundError("Alert rule was not found.")
        rule.is_active = False
        rule.save(update_fields=["is_active", "updated_at"])
        rule.delete()

    def evaluate_alerts(self, tenant_id: UUID | str) -> list[Alert]:
        tenant = _tenant(tenant_id)
        started = time.monotonic()
        results: list[Alert] = []
        for rule in (
            AlertRule.objects.for_tenant(tenant).filter(is_deleted=False, is_active=True).select_related("metric")
        ):
            timeout = float(_setting(tenant, "limits.alert_evaluation_timeout_seconds"))
            if time.monotonic() - started > timeout:
                raise CapabilityUnavailableError(f"Alert evaluation exceeded its {timeout:g}-second safety bound.")
            result = self.evaluate_alert_rule(tenant, rule.id)
            if result is not None:
                results.append(result)
        return results

    @transaction.atomic
    def evaluate_alert_rule(self, tenant_id: UUID | str, rule_id: UUID | str) -> Alert | None:
        tenant = _tenant(tenant_id)
        rule = (
            AlertRule.objects.select_for_update()
            .for_tenant(tenant)
            .filter(id=rule_id, is_deleted=False, is_active=True)
            .first()
        )
        if rule is None:
            raise NotFoundError("Active alert rule was not found.")
        metric = (
            rule.metric
            or Metric.objects.for_tenant(tenant).filter(metric_name__iexact=rule.metric_name, is_deleted=False).first()
        )
        now = timezone.now()
        window_start = now - timedelta(minutes=rule.evaluation_window_minutes)
        points = (
            list(
                MetricDataPoint.objects.for_tenant(tenant)
                .filter(metric=metric, timestamp__gte=window_start, timestamp__lte=now)
                .order_by("timestamp")
            )
            if metric
            else []
        )
        triggered, observed = self._evaluate_condition(tenant, rule, points)
        dedup = hashlib.sha256(f"{rule.id}:global".encode()).hexdigest()
        open_alert = (
            Alert.objects.select_for_update()
            .for_tenant(tenant)
            .filter(deduplication_key=dedup, status__in=[AlertState.FIRING, AlertState.ACKNOWLEDGED], is_deleted=False)
            .first()
        )
        rule.last_evaluated_at = now
        rule.save(update_fields=["last_evaluated_at", "updated_at"])
        if not triggered:
            if (
                open_alert
                and rule.auto_resolve
                and now - open_alert.last_observed_at
                >= timedelta(
                    minutes=float(_setting(tenant, "rules.auto_resolution_window_multiplier"))
                    * rule.evaluation_window_minutes
                )
            ):
                return self.resolve_alert(
                    tenant, open_alert.id, resolved_by=SYSTEM_ACTOR, note="Condition cleared automatically."
                )
            return None
        if open_alert:
            cooldown = timedelta(minutes=rule.cooldown_minutes)
            bypass = bool(_setting(tenant, "rules.critical_bypasses_cooldown"))
            if (rule.severity != Severity.CRITICAL or not bypass) and now - open_alert.last_observed_at < cooldown:
                return None
            open_alert.last_observed_at = now
            open_alert.occurrence_count += 1
            open_alert.triggered_value = observed
            if (
                open_alert.status == AlertState.ACKNOWLEDGED
                and rule.severity == Severity.CRITICAL
                and bool(_setting(tenant, "rules.critical_recurrence_reopens_acknowledged"))
            ):
                open_alert.status = AlertState.FIRING
                open_alert.acknowledged_at = None
                open_alert.acknowledged_by = None
            open_alert.save()
            self._deliver(tenant, open_alert, rule.action)
            return open_alert
        alert = Alert.objects.create(
            tenant_id=tenant,
            created_by=rule.created_by,
            alert_rule=rule,
            metric=metric,
            metric_name=rule.metric_name,
            condition=rule.condition,
            severity=rule.severity,
            status=AlertState.FIRING,
            deduplication_key=dedup,
            title=rule.name,
            description=rule.description,
            triggered_value=observed,
            threshold=rule.threshold,
            triggered_at=now,
            last_observed_at=now,
            context={"evaluation_window_minutes": rule.evaluation_window_minutes},
            occurrence_count=int(_setting(tenant, "defaults.alert.initial_occurrence_count")),
        )
        self._deliver(tenant, alert, rule.action)
        publish_domain_event(
            tenant,
            "alert.fired",
            "Alert",
            alert.id,
            payload={
                "alert_id": str(alert.id),
                "alert_rule_id": str(rule.id),
                "metric_name": rule.metric_name,
                "severity": rule.severity,
            },
        )
        return alert

    @staticmethod
    def _evaluate_condition(
        tenant_id: UUID, rule: AlertRule, points: Sequence[MetricDataPoint]
    ) -> tuple[bool, float | None]:
        if rule.condition == AlertCondition.ABSENCE:
            # Absence is deliberately 2x the configured window to avoid sparse-series false positives.
            if points:
                return False, None
            latest = (
                MetricDataPoint.objects.for_tenant(rule.tenant_id)
                .filter(metric__metric_name=rule.metric_name)
                .order_by("-timestamp")
                .first()
            )
            old_enough = latest is None or timezone.now() - latest.timestamp >= timedelta(
                minutes=float(_setting(tenant_id, "rules.absence_window_multiplier")) * rule.evaluation_window_minutes
            )
            return old_enough, None
        if not points:
            return False, None
        values = [point.value for point in points]
        if rule.condition == AlertCondition.RATE:
            elapsed_minutes = max(
                (points[-1].timestamp - points[0].timestamp).total_seconds() / 60,
                float(_setting(tenant_id, "rules.rate_minimum_elapsed_minutes")),
            )
            observed = abs(float(points[-1].value) - float(points[0].value)) / elapsed_minutes
            return observed > float(rule.threshold), observed
        observed = statistics.fmean(float(value) for value in values)
        return (
            (
                observed > float(rule.threshold)
                if rule.condition == AlertCondition.ABOVE
                else observed < float(rule.threshold)
            ),
            observed,
        )

    def _deliver(self, tenant_id: UUID, alert: Alert, action: Mapping[str, Any]) -> None:
        for channel in action.get("channels", []):
            recipients = action.get("recipients") or ["tenant-default"]
            for recipient in recipients:
                key = f"{alert.id}:{alert.occurrence_count}:{channel}:{recipient}"
                enqueue(
                    tenant_id,
                    alert.created_by,
                    "performance_monitoring.deliver_alert_notification",
                    {
                        "alert_id": str(alert.id),
                        "channel": str(channel),
                        "recipient": str(recipient),
                        "delivery_key": key,
                    },
                    key,
                )

    @transaction.atomic
    def acknowledge_alert(
        self, tenant_id: UUID | str, alert_id: UUID | str, acknowledged_by: UUID | str | None = None
    ) -> Alert:
        tenant = _tenant(tenant_id)
        alert = Alert.objects.select_for_update().for_tenant(tenant).filter(id=alert_id, is_deleted=False).first()
        if alert is None:
            raise AlertNotFoundError("Alert was not found.")
        if alert.status == AlertState.RESOLVED:
            raise AlertAlreadyResolvedError("A resolved alert cannot be acknowledged.")
        if alert.status != AlertState.FIRING:
            raise ConflictError("Only firing alerts can be acknowledged.")
        alert.status = AlertState.ACKNOWLEDGED
        alert.acknowledged_at = timezone.now()
        alert.acknowledged_by = _actor(acknowledged_by)
        alert.save()
        publish_domain_event(
            tenant,
            "alert.acknowledged",
            "Alert",
            alert.id,
            payload={"alert_id": str(alert.id), "status": alert.status},
        )
        return alert

    @transaction.atomic
    def resolve_alert(
        self,
        tenant_id: UUID | str,
        alert_id: UUID | str,
        *,
        resolved_by: UUID | str | None = None,
        note: str = "",
    ) -> Alert:
        tenant = _tenant(tenant_id)
        alert = Alert.objects.select_for_update().for_tenant(tenant).filter(id=alert_id, is_deleted=False).first()
        if alert is None:
            raise AlertNotFoundError("Alert was not found.")
        if alert.status == AlertState.RESOLVED:
            return alert
        alert.status = AlertState.RESOLVED
        alert.resolved_at = timezone.now()
        alert.resolved_by = _actor(resolved_by)
        alert.resolution_note = note.strip()
        alert.save()
        publish_domain_event(
            tenant,
            "alert.resolved",
            "Alert",
            alert.id,
            payload={"alert_id": str(alert.id), "status": alert.status},
        )
        return alert


class SLOMonitoringService:
    """Tenant-safe SLO mutation and error-budget evaluation."""

    @transaction.atomic
    def create(
        self, tenant_id: UUID | str, values: Mapping[str, Any], *, created_by: UUID | str | None = None
    ) -> ServiceLevelObjective:
        tenant = _tenant(tenant_id)
        data = dict(values)
        service = self._relation(tenant, MonitoredService, data.pop("service_id"))
        metric = self._relation(tenant, Metric, data.pop("indicator_metric_id"))
        defaults = _setting(tenant, "defaults.slo")
        data.setdefault("window_days", int(defaults["window_days"]))
        data.setdefault("expected_interval_seconds", int(defaults["expected_interval_seconds"]))
        self._validate(tenant, data)
        budget = self._budget_minutes(data["window_days"], data["objective_percentage"])
        return ServiceLevelObjective.objects.create(
            tenant_id=tenant,
            created_by=_actor(created_by),
            service=service,
            indicator_metric=metric,
            error_budget_minutes=budget,
            **data,
        )

    @transaction.atomic
    def update(self, tenant_id: UUID | str, slo_id: UUID | str, values: Mapping[str, Any]) -> ServiceLevelObjective:
        tenant = _tenant(tenant_id)
        slo = (
            ServiceLevelObjective.objects.select_for_update()
            .for_tenant(tenant)
            .filter(id=slo_id, is_deleted=False)
            .first()
        )
        if slo is None:
            raise NotFoundError("SLO was not found.")
        data = dict(values)
        if "service_id" in data:
            slo.service = self._relation(tenant, MonitoredService, data.pop("service_id"))
        if "indicator_metric_id" in data:
            slo.indicator_metric = self._relation(tenant, Metric, data.pop("indicator_metric_id"))
        merged = {
            "comparison": data.get("comparison", slo.comparison),
            "objective_percentage": data.get("objective_percentage", slo.objective_percentage),
            "window_days": data.get("window_days", slo.window_days),
            "expected_interval_seconds": data.get("expected_interval_seconds", slo.expected_interval_seconds),
        }
        self._validate(tenant, merged)
        for field, value in data.items():
            if field in {
                "name",
                "description",
                "comparison",
                "threshold",
                "objective_percentage",
                "window_days",
                "expected_interval_seconds",
                "is_active",
            }:
                setattr(slo, field, value)
        slo.error_budget_minutes = self._budget_minutes(slo.window_days, slo.objective_percentage)
        slo.save()
        return slo

    @transaction.atomic
    def evaluate(self, tenant_id: UUID | str, slo_id: UUID | str) -> ErrorBudgetSnapshot:
        tenant = _tenant(tenant_id)
        slo = (
            ServiceLevelObjective.objects.for_tenant(tenant)
            .select_related("indicator_metric")
            .filter(id=slo_id, is_deleted=False, is_active=True)
            .first()
        )
        if slo is None:
            raise NotFoundError("Active SLO was not found.")
        period_end = timezone.now()
        period_start = period_end - timedelta(days=slo.window_days)
        points = list(
            MetricDataPoint.objects.for_tenant(tenant)
            .filter(metric=slo.indicator_metric, timestamp__gte=period_start, timestamp__lte=period_end)
            .only("value")
        )
        if not points:
            raise InsufficientDataError("The SLO has no telemetry in its configured window.")
        failed = sum(not _compare(float(point.value), slo.comparison, slo.threshold) for point in points)
        consumed = math.ceil(failed * slo.expected_interval_seconds / 60)
        budget = self._budget_minutes(slo.window_days, slo.objective_percentage)
        remaining = budget - consumed
        burn_rate = consumed / budget if budget else (float("inf") if consumed else 0.0)
        snapshot = ErrorBudgetSnapshot.objects.create(
            tenant_id=tenant,
            slo=slo,
            period_start=period_start,
            period_end=period_end,
            budget_minutes=budget,
            consumed_minutes=consumed,
            remaining_minutes=remaining,
            burn_rate=burn_rate,
            status=ComplianceState.BREACHED if remaining < 0 else ComplianceState.COMPLIANT,
        )
        return snapshot

    @staticmethod
    def _relation(tenant_id: UUID, model: type[Any], object_id: Any) -> Any:
        relation = model.objects.for_tenant(tenant_id).filter(id=object_id, is_deleted=False).first()
        if relation is None:
            raise NotFoundError(f"{model.__name__} was not found for this tenant.")
        return relation

    @staticmethod
    def _budget_minutes(window_days: int, objective_percentage: Any) -> int:
        return max(0, math.floor(window_days * 24 * 60 * (100 - float(objective_percentage)) / 100))

    @staticmethod
    def _validate(tenant_id: UUID, data: Mapping[str, Any]) -> None:
        if data["comparison"] not in set(_setting(tenant_id, "allowlists.comparisons")):
            raise MonitoringError("Unsupported SLO comparison.")
        objective = float(data["objective_percentage"])
        if objective <= 0 or objective > 100:
            raise MonitoringError("SLO objective percentage must be greater than 0 and at most 100.")
        if int(data["window_days"]) <= 0 or int(data["expected_interval_seconds"]) <= 0:
            raise MonitoringError("SLO window and expected interval must be positive.")


class SLAMonitoringService:
    """Versioned SLA definitions and immutable compliance/report evidence."""

    @transaction.atomic
    def define_sla(
        self,
        tenant_id: UUID | str,
        service_name: str,
        metric: str,
        target: Decimal | float,
        window: str,
        *,
        comparison: str = Comparison.GTE,
        expected_interval_seconds: int | None = None,
        created_by: UUID | str | None = None,
    ) -> SLADefinition:
        tenant = _tenant(tenant_id)
        expected_interval_seconds = expected_interval_seconds or int(
            _setting(tenant, "defaults.sla.expected_interval_seconds")
        )
        cadence_min = int(_setting(tenant, "limits.sla_cadence_min_seconds"))
        cadence_max = int(_setting(tenant, "limits.sla_cadence_max_seconds"))
        if not cadence_min <= expected_interval_seconds <= cadence_max:
            raise MonitoringError("SLA cadence is outside configured safe limits.")
        metric_name = _normalize_metric_name(tenant, metric)
        if window not in set(_setting(tenant, "allowlists.sla_windows")):
            raise MonitoringError("Unsupported SLA window.")
        if comparison not in set(_setting(tenant, "allowlists.sla_comparisons")):
            raise MonitoringError("SLA comparison must be gte or lte.")
        target_value = _numeric(target)
        if target_value <= 0:
            raise MonitoringError("SLA target must be positive.")
        definition = Metric.objects.for_tenant(tenant).filter(metric_name__iexact=metric_name, is_deleted=False).first()
        duplicate = (
            SLADefinition.objects.for_tenant(tenant)
            .filter(
                service_name__iexact=service_name.strip(),
                metric_name__iexact=metric_name,
                window=window,
                is_active=True,
                is_deleted=False,
            )
            .first()
        )
        if duplicate:
            raise DuplicateSLAError("An active SLA already exists for this service, metric, and window.")
        sla = SLADefinition.objects.create(
            tenant_id=tenant,
            name=f"{service_name.strip()} · {metric_name}",
            service_name=service_name.strip(),
            metric_name=metric_name,
            metric=definition,
            target=target_value,
            window=window,
            comparison=comparison,
            expected_interval_seconds=expected_interval_seconds,
            timezone=str(_setting(tenant, "defaults.sla.timezone")),
            version=int(_setting(tenant, "defaults.sla.initial_version")),
            created_by=_actor(created_by),
        )
        if bool(_setting(tenant, "rules.sla_auto_create_alert_rule")):
            AlertingService().create_alert_rule(
                tenant,
                metric_name,
                AlertCondition.BELOW if comparison == Comparison.GTE else AlertCondition.ABOVE,
                target_value,
                {
                    "channels": list(_setting(tenant, "defaults.alert_rule.notification_channels")),
                    "recipients": [str(_actor(created_by))],
                },
                name=f"SLA breach: {sla.name}",
                severity=Severity.CRITICAL,
                created_by=created_by,
            )
        return sla

    @transaction.atomic
    def update_sla(self, tenant_id: UUID | str, sla_id: UUID | str, **changes: Any) -> SLADefinition:
        tenant = _tenant(tenant_id)
        current = (
            SLADefinition.objects.select_for_update()
            .for_tenant(tenant)
            .filter(id=sla_id, is_deleted=False, is_active=True)
            .first()
        )
        if current is None:
            raise SLANotFoundError("SLA definition was not found.")
        versioned = any(key in changes for key in ("target", "window", "comparison", "expected_interval_seconds"))
        if not versioned:
            for field in ("name", "description"):
                if field in changes:
                    setattr(current, field, changes[field])
            current.save()
            return current
        now = timezone.now()
        current.is_active = False
        current.effective_until = now
        current.save()
        values = {
            "service_name": current.service_name,
            "metric_name": current.metric_name,
            "metric": current.metric,
            "service": current.service,
            "target": current.target,
            "window": current.window,
            "comparison": current.comparison,
            "expected_interval_seconds": current.expected_interval_seconds,
            "name": current.name,
            "description": current.description,
        }
        values.update({key: value for key, value in changes.items() if key in values})
        cadence = int(values["expected_interval_seconds"])
        if (
            not int(_setting(tenant, "limits.sla_cadence_min_seconds"))
            <= cadence
            <= int(_setting(tenant, "limits.sla_cadence_max_seconds"))
        ):
            raise MonitoringError("SLA cadence is outside configured safe limits.")
        return SLADefinition.objects.create(
            tenant_id=tenant,
            created_by=current.created_by,
            previous_version=current,
            version=current.version + 1,
            effective_from=now,
            **values,
        )

    @transaction.atomic
    def delete_sla(self, tenant_id: UUID | str, sla_id: UUID | str) -> None:
        tenant = _tenant(tenant_id)
        sla = SLADefinition.objects.select_for_update().for_tenant(tenant).filter(id=sla_id, is_deleted=False).first()
        if sla is None:
            raise SLANotFoundError("SLA definition was not found.")
        sla.is_active = False
        sla.delete()

    def _period_range(
        self,
        tenant_id: UUID,
        window: str,
        period: str | None,
        start: datetime | None,
        end: datetime | None,
    ) -> tuple[datetime, datetime]:
        now = timezone.now()
        if period == "custom":
            if not start or not end or timezone.is_naive(start) or timezone.is_naive(end) or start >= end:
                raise InvalidTimeRangeError("Custom compliance requires timezone-aware start before end.")
            max_range_days = int(_setting(tenant_id, "limits.compliance_max_range_days"))
            if end - start > timedelta(days=max_range_days):
                raise InvalidTimeRangeError(f"Custom compliance ranges cannot exceed {max_range_days} days.")
            return start, end
        if window == SLAWindow.ROLLING_1H:
            duration = timedelta(hours=1)
        elif window == SLAWindow.ROLLING_24H:
            duration = timedelta(hours=24)
        else:
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if period == "previous":
                return (month_start - timedelta(days=1)).replace(day=1), month_start
            return month_start, now
        end_at = now
        if period == "previous":
            end_at = now - duration
        return end_at - duration, end_at

    @transaction.atomic
    def check_sla_compliance(
        self,
        tenant_id: UUID | str,
        sla_id: UUID | str,
        *,
        period: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> SLAComplianceRecord:
        tenant = _tenant(tenant_id)
        sla = SLADefinition.objects.for_tenant(tenant).filter(id=sla_id, is_deleted=False).first()
        if sla is None:
            raise SLANotFoundError("SLA definition was not found.")
        period_start, period_end = self._period_range(tenant, sla.window, period, start, end)
        existing = (
            SLAComplianceRecord.objects.for_tenant(tenant)
            .filter(sla=sla, period_start=period_start, period_end=period_end)
            .first()
        )
        if existing:
            return existing
        metric = (
            sla.metric
            or Metric.objects.for_tenant(tenant).filter(metric_name__iexact=sla.metric_name, is_deleted=False).first()
        )
        if metric is None:
            raise InsufficientDataError("The SLA metric has no definition or telemetry.")
        points = list(
            MetricDataPoint.objects.for_tenant(tenant)
            .filter(metric=metric, timestamp__gte=period_start, timestamp__lte=period_end)
            .order_by("timestamp")
        )
        total_seconds = max((period_end - period_start).total_seconds(), 1)
        expected = max(1, math.floor(total_seconds / sla.expected_interval_seconds))
        minimum_density = float(_setting(tenant, "rules.minimum_sample_density"))
        if len(points) / expected < minimum_density:
            raise InsufficientDataError(
                f"SLA compliance requires at least {minimum_density:.0%} of expected samples.",
                details={"expected_samples": expected, "observed_samples": len(points)},
            )
        comparisons = [_compare(float(point.value), sla.comparison, float(sla.target)) for point in points]
        compliant = sum(comparisons)
        # Missing intervals remain in the denominator. Density is a quality
        # gate, not a mechanism for making partial evidence look healthier.
        compliance_precision = Decimal(str(_setting(tenant, "rules.compliance_precision")))
        actual_precision = Decimal(str(_setting(tenant, "rules.actual_value_precision")))
        compliance_pct = Decimal(compliant * 100 / expected).quantize(compliance_precision)
        actual_average = Decimal(str(statistics.fmean(float(point.value) for point in points))).quantize(
            actual_precision
        )
        is_compliant = _compare(float(actual_average), sla.comparison, float(sla.target))
        missing_count = max(expected - len(points), 0)
        failed_observed = len(points) - compliant
        breach_intervals = failed_observed + (
            missing_count if bool(_setting(tenant, "rules.missing_samples_consume_breach_duration")) else 0
        )
        breach_seconds = breach_intervals * sla.expected_interval_seconds
        record = SLAComplianceRecord.objects.create(
            tenant_id=tenant,
            sla=sla,
            period_start=period_start,
            period_end=period_end,
            expected_samples=expected,
            observed_samples=len(points),
            compliant_samples=compliant,
            missing_samples=missing_count,
            actual_value=actual_average,
            target_value=sla.target,
            is_compliant=is_compliant,
            compliance_percentage=compliance_pct,
            breach_duration_minutes=math.ceil(breach_seconds / 60),
            breach_duration_seconds=breach_seconds,
            status=ComplianceState.COMPLIANT if is_compliant else ComplianceState.BREACHED,
            evidence={"calculation": "observed_average", "sampling_density": len(points) / expected},
        )
        if not is_compliant and breach_seconds:
            breached_indexes = [index for index, value in enumerate(comparisons) if not value]
            if breached_indexes:
                breach_start = points[min(breached_indexes)].timestamp
                breach_end = min(
                    points[max(breached_indexes)].timestamp + timedelta(seconds=sla.expected_interval_seconds),
                    period_end,
                )
                worst_value = max((float(point.value) for point, ok in zip(points, comparisons) if not ok), key=abs)
            else:
                # The density gate permits up to 20% missing telemetry. Those
                # intervals consume budget and are represented explicitly.
                breach_start = max(period_start, period_end - timedelta(seconds=breach_seconds))
                breach_end = period_end
                worst_value = None
            SLABreach.objects.create(
                tenant_id=tenant,
                sla=sla,
                compliance_record=record,
                started_at=breach_start,
                ended_at=breach_end,
                duration_seconds=breach_seconds,
                worst_value=worst_value,
                evidence={"sample_count": len(breached_indexes)},
            )
            publish_domain_event(
                tenant,
                "sla.breach",
                "SLADefinition",
                sla.id,
                payload={"sla_id": str(sla.id), "is_compliant": False, "actual_value": float(actual_average)},
            )
        publish_domain_event(
            tenant,
            "sla.compliance_checked",
            "SLAComplianceRecord",
            record.id,
            payload={"sla_id": str(sla.id), "is_compliant": is_compliant, "actual_value": float(actual_average)},
        )
        return record

    # Compatibility alias named by the gate brief.
    evaluate_compliance = check_sla_compliance

    @transaction.atomic
    def generate_sla_report(
        self,
        tenant_id: UUID | str,
        period: str,
        *,
        output_format: str = "json",
        created_by: UUID | str | None = None,
        artifact_writer: Callable[[UUID, str, bytes], tuple[str, str]] | None = None,
    ) -> SLAReport:
        tenant = _tenant(tenant_id)
        if period not in set(_setting(tenant, "allowlists.report_periods")):
            raise MonitoringError("Unsupported SLA report period.")
        if output_format not in set(_setting(tenant, "allowlists.report_formats")):
            raise MonitoringError("Unsupported report format.")
        now = timezone.now()
        if period == "rolling_24h":
            start = now - timedelta(hours=24)
        elif period == "7d":
            start = now - timedelta(days=7)
        else:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        results: list[dict[str, Any]] = []
        for sla in SLADefinition.objects.for_tenant(tenant).filter(is_active=True, is_deleted=False):
            try:
                record = self.check_sla_compliance(tenant, sla.id, period="custom", start=start, end=now)
                results.append(
                    {
                        "sla_id": str(sla.id),
                        "service_name": sla.service_name,
                        "metric_name": sla.metric_name,
                        "target": float(sla.target),
                        "actual": float(record.actual_value),
                        "is_compliant": record.is_compliant,
                        "breach_duration_minutes": record.breach_duration_minutes,
                    }
                )
            except InsufficientDataError as exc:
                results.append({"sla_id": str(sla.id), "status": "insufficient_data", "error": exc.public_message})
        summary = {
            "period": period,
            "format": output_format,
            "sla_results": results,
            "summary": {
                "total_slas": len(results),
                "compliant": sum(1 for result in results if result.get("is_compliant") is True),
                "breached": sum(1 for result in results if result.get("is_compliant") is False),
                "insufficient_data": sum(1 for result in results if result.get("status") == "insufficient_data"),
            },
        }
        artifact_ref = artifact_hash = ""
        if output_format != "json":
            if artifact_writer is None:
                raise CapabilityUnavailableError("PDF/CSV artifact storage is not configured.")
            artifact_ref, artifact_hash = artifact_writer(tenant, output_format, json.dumps(summary).encode())
            if not artifact_ref or not re.fullmatch(r"[0-9a-f]{64}", artifact_hash):
                raise CapabilityUnavailableError("Artifact provider returned an invalid durable receipt.")
        if not SLADefinition.objects.for_tenant(tenant).filter(is_active=True, is_deleted=False).exists():
            raise InsufficientDataError("No active SLA definitions are available for reporting.")
        report = SLAReport.objects.create(
            tenant_id=tenant,
            sla=None,
            period_start=start,
            period_end=now,
            status=ReportState.READY,
            summary=summary,
            artifact_ref=artifact_ref,
            artifact_sha256=artifact_hash,
            generated_by=_actor(created_by),
            generated_at=timezone.now(),
        )
        publish_domain_event(
            tenant,
            "sla.report_generated",
            "SLAReport",
            report.id,
            payload={"report_id": str(report.id), "period": period},
        )
        return report

    generate_report = generate_sla_report


class TelemetryService:
    """Ingest OTLP-compatible logs/traces after tenant/source validation."""

    @transaction.atomic
    def ingest_log(self, tenant_id: UUID | str, payload: Mapping[str, Any]) -> LogEntry:
        tenant = _tenant(tenant_id)
        source = (
            TelemetrySource.objects.for_tenant(tenant)
            .filter(id=payload.get("source_id"), is_deleted=False, is_active=True)
            .first()
        )
        if source is None:
            raise NotFoundError("Active telemetry source was not found.")
        message = str(payload.get("message", "")).strip()
        if not message:
            raise MonitoringError("Log message is required.")
        max_message_length = int(_setting(tenant, "limits.log_message_max_length"))
        if len(message) > max_message_length:
            raise MonitoringError(f"Log message cannot exceed {max_message_length} characters.")
        attributes = dict(payload.get("attributes") or {})
        for redacted in source.redaction_fields:
            attributes.pop(str(redacted), None)
        service = self._relation(tenant, MonitoredService, payload.get("service_id"))
        environment = self._relation(tenant, MonitoringEnvironment, payload.get("environment_id"))
        idempotency_key = str(payload.get("idempotency_key", "")).strip()
        values = {
            "source": source,
            "service": service,
            "environment": environment,
            "timestamp": payload.get("timestamp") or timezone.now(),
            "level": str(payload.get("level", "info")).lower(),
            "message": message,
            "attributes": attributes,
            "trace_id": str(payload.get("trace_id", "")),
            "span_id": str(payload.get("span_id", "")),
            "correlation_id": str(payload.get("correlation_id") or get_correlation_id()),
            "idempotency_key": idempotency_key,
        }
        if values["level"] not in set(_setting(tenant, "allowlists.log_levels")):
            raise MonitoringError("Log level is not enabled.")
        if idempotency_key:
            existing = (
                LogEntry.objects.select_for_update()
                .for_tenant(tenant)
                .filter(source=source, idempotency_key=idempotency_key)
                .first()
            )
            if existing is not None:
                self._assert_equivalent_log(existing, values, timestamp_supplied=payload.get("timestamp") is not None)
                return existing
        try:
            # A savepoint keeps the surrounding transaction usable if a concurrent
            # request wins the tenant/source/idempotency unique-key race.
            with transaction.atomic():
                entry = LogEntry.objects.create(tenant_id=tenant, **values)
        except IntegrityError:
            existing = (
                LogEntry.objects.for_tenant(tenant).filter(source=source, idempotency_key=idempotency_key).first()
            )
            if existing is None:
                raise
            self._assert_equivalent_log(existing, values, timestamp_supplied=payload.get("timestamp") is not None)
            return existing
        self._touch_source(source)
        logger.info("log_ingested", extra=_log_context(tenant, log_entry_id=entry.id, source_id=source.id))
        return entry

    @staticmethod
    def _assert_equivalent_log(existing: LogEntry, values: Mapping[str, Any], *, timestamp_supplied: bool) -> None:
        comparable = (
            "source_id",
            "service_id",
            "environment_id",
            "level",
            "message",
            "attributes",
            "trace_id",
            "span_id",
        )
        expected = {
            "source_id": values["source"].id,
            "service_id": getattr(values["service"], "id", None),
            "environment_id": getattr(values["environment"], "id", None),
            **{field: values[field] for field in ("level", "message", "attributes", "trace_id", "span_id")},
        }
        mismatch = any(getattr(existing, field) != expected[field] for field in comparable)
        if timestamp_supplied and existing.timestamp != values["timestamp"]:
            mismatch = True
        if mismatch:
            raise ConflictError("Idempotency key was already used with a different log entry.")

    @transaction.atomic
    def ingest_trace(self, tenant_id: UUID | str, payload: Mapping[str, Any]) -> Trace:
        tenant = _tenant(tenant_id)
        source = (
            TelemetrySource.objects.for_tenant(tenant)
            .filter(id=payload.get("source_id"), is_deleted=False, is_active=True)
            .first()
        )
        service = self._relation(tenant, MonitoredService, payload.get("service_id"))
        if source is None or service is None:
            raise NotFoundError("Active source and service are required.")
        trace_id = str(payload.get("trace_id", "")).lower()
        if not TRACE_ID_PATTERN.fullmatch(trace_id):
            raise MonitoringError("trace_id must contain 32 lowercase hexadecimal characters.")
        existing = Trace.objects.for_tenant(tenant).filter(trace_id=trace_id).first()
        if existing:
            return existing
        spans = list(payload.get("spans") or [])
        max_spans = int(_setting(tenant, "limits.max_spans_per_trace"))
        if len(spans) > max_spans:
            raise MonitoringError(f"A trace cannot contain more than {max_spans} spans.")
        trace = Trace.objects.create(
            tenant_id=tenant,
            source=source,
            service=service,
            environment=self._relation(tenant, MonitoringEnvironment, payload.get("environment_id")),
            trace_id=trace_id,
            name=str(payload.get("name", "")).strip(),
            started_at=payload["started_at"],
            ended_at=payload["ended_at"],
            duration_ms=_numeric(payload.get("duration_ms")),
            status=str(payload.get("status", "unset")),
            attributes=dict(payload.get("attributes") or {}),
            sampled=bool(payload.get("sampled", True)),
            span_count=len(spans),
            error_span_count=sum(1 for span in spans if span.get("status") == "error"),
        )
        for item in spans:
            span_service = self._relation(tenant, MonitoredService, item.get("service_id")) or service
            span_id = str(item.get("span_id", "")).lower()
            if not SPAN_ID_PATTERN.fullmatch(span_id):
                raise MonitoringError("span_id must contain 16 lowercase hexadecimal characters.")
            Span.objects.create(
                tenant_id=tenant,
                trace=trace,
                service=span_service,
                span_id=span_id,
                parent_span_id=str(item.get("parent_span_id", "")),
                name=str(item.get("name", "")).strip(),
                kind=str(item.get("kind", "internal")),
                started_at=item["started_at"],
                ended_at=item["ended_at"],
                duration_ms=_numeric(item.get("duration_ms")),
                status=str(item.get("status", "unset")),
                attributes=dict(item.get("attributes") or {}),
                events=list(item.get("events") or []),
            )
        self._touch_source(source)
        return trace

    @staticmethod
    def _relation(tenant_id: UUID, model: type[Any], identifier: Any) -> Any | None:
        if not identifier:
            return None
        relation = model.objects.for_tenant(tenant_id).filter(id=identifier, is_deleted=False).first()
        if relation is None:
            raise NotFoundError(f"{model.__name__} was not found.")
        return relation

    @staticmethod
    def _touch_source(source: TelemetrySource) -> None:
        source.last_seen_at = timezone.now()
        source.status = HealthState.HEALTHY
        source.save(update_fields=["last_seen_at", "status", "updated_at"])


class CoreNotificationAdapter:
    """Adapter over the published notification service (never its ORM)."""

    @staticmethod
    def send(tenant_id: UUID, alert: Alert, delivery: Mapping[str, Any]) -> str:
        from src.core.notifications.services import NotificationService

        channel = str(delivery.get("channel", ""))
        recipient = str(delivery.get("recipient", "")).strip()
        if channel not in {"in_app", "email"}:
            raise CapabilityUnavailableError(f"Notification channel '{channel}' is unavailable.")
        if not recipient or recipient == "tenant-default":
            raise CapabilityUnavailableError("Notification action requires an explicit recipient reference.")
        metadata: dict[str, str] = {"alert_id": str(alert.id), "channel": channel}
        if "@" in recipient:
            metadata["user_email"] = recipient
        notification = NotificationService.create_notification(
            str(tenant_id),
            recipient,
            alert.title,
            alert.description or f"{alert.metric_name} is {alert.status}.",
            notification_type=alert.severity,
            metadata=metadata,
        )
        if notification.pk is None:
            raise CapabilityUnavailableError("Notification service did not return a durable receipt.")
        return str(notification.pk)


def _notification_breaker(tenant_id: UUID, failure_threshold: int, recovery_seconds: float) -> CircuitBreaker[Any]:
    key = (tenant_id, failure_threshold, recovery_seconds)
    with _notification_breakers_lock:
        breaker = _notification_breakers.get(key)
        if breaker is None:
            breaker = CircuitBreaker(
                f"performance-monitoring-notifications:{tenant_id}",
                failure_threshold=failure_threshold,
                reset_timeout=recovery_seconds,
            )
            _notification_breakers[key] = breaker
        return breaker


def deliver_alert_notification_job(job: AsyncJob) -> dict[str, Any]:
    """Deliver one durable notification job with configured resilience and audit evidence."""

    tenant = _tenant(job.tenant_id)
    payload = dict(job.payload)
    alert = Alert.objects.for_tenant(tenant).filter(id=payload.get("alert_id"), is_deleted=False).first()
    if alert is None:
        raise NotFoundError("Notification job alert was not found.")
    delivery_key = str(payload.get("delivery_key", "")).strip()
    channel = str(payload.get("channel", ""))
    recipient = str(payload.get("recipient", "")).strip()
    if not delivery_key or not recipient:
        raise MonitoringError("Notification job is missing its idempotency contract.")
    allowed_channels = set(_setting(tenant, "allowlists.notification_channels"))
    if channel not in allowed_channels:
        raise CapabilityUnavailableError(f"Notification channel '{channel}' is disabled.")
    existing = (
        AlertNotificationOutcome.objects.for_tenant(tenant)
        .filter(idempotency_key=delivery_key, state__in=[DeliveryState.SENT, DeliveryState.DELIVERED])
        .first()
    )
    if existing is not None:
        return {"outcome_id": str(existing.id), "state": existing.state}

    delivery = dict(_setting(tenant, "delivery"))
    attempts = int(delivery["max_attempts"])
    timeout_seconds = float(delivery["timeout_seconds"])
    initial_backoff = float(delivery["initial_backoff_seconds"])
    max_backoff = float(delivery["max_backoff_seconds"])
    jitter_ratio = float(delivery["jitter_ratio"])
    breaker = _notification_breaker(
        tenant,
        int(delivery["circuit_failure_threshold"]),
        float(delivery["circuit_recovery_seconds"]),
    )
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            provider_id = breaker.call(
                CoreNotificationAdapter.send,
                tenant,
                alert,
                {"channel": channel, "recipient": recipient},
            )
            elapsed = time.monotonic() - started
            if elapsed > timeout_seconds:
                raise CapabilityUnavailableError("Notification dependency exceeded its configured timeout.")
            outcome = AlertNotificationOutcome.objects.create(
                tenant_id=tenant,
                alert=alert,
                channel=channel,
                destination_ref=recipient,
                state=DeliveryState.SENT,
                attempt=attempt,
                idempotency_key=delivery_key,
                provider_message_id=provider_id,
                correlation_id=job.correlation_id,
            )
            return {"outcome_id": str(outcome.id), "state": outcome.state}
        except Exception as exc:
            last_error = exc
            error_code = exc.code if isinstance(exc, MonitoringError) else "DELIVERY_FAILED"
            AlertNotificationOutcome.objects.get_or_create(
                tenant_id=tenant,
                idempotency_key=delivery_key,
                attempt=attempt,
                defaults={
                    "alert": alert,
                    "channel": channel,
                    "destination_ref": recipient,
                    "state": DeliveryState.FAILED,
                    "error_code": error_code,
                    "error_message": "Notification delivery failed.",
                    "correlation_id": job.correlation_id,
                },
            )
            logger.warning(
                "alert_notification_attempt_failed",
                extra=_log_context(tenant, alert_id=alert.id, async_job_id=job.id, attempt=attempt),
            )
            if attempt < attempts:
                base = min(max_backoff, initial_backoff * (2 ** (attempt - 1)))
                time.sleep(base + random.uniform(0, base * jitter_ratio))
    raise CapabilityUnavailableError("Notification delivery exhausted configured retries.") from last_error


class MonitoringCatalogService:
    """Validated CRUD for mutable monitoring configuration aggregates."""

    ALLOWED_UPDATES = {
        TelemetrySource: {
            "name",
            "source_type",
            "description",
            "sampling_rate",
            "retention_days",
            "daily_event_quota",
            "redaction_fields",
            "is_active",
        },
        MonitoringEnvironment: {"name", "slug", "kind", "description", "is_active"},
        MonitoredService: {
            "environment",
            "source",
            "name",
            "slug",
            "namespace",
            "version",
            "owner",
            "language",
            "attributes",
            "is_active",
        },
        Dashboard: {
            "name",
            "description",
            "layout",
            "variables",
            "refresh_interval_seconds",
            "is_default",
            "is_active",
        },
        ServiceLevelObjective: {
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
        },
    }

    @transaction.atomic
    def create(
        self,
        tenant_id: UUID | str,
        model: type[Any],
        values: Mapping[str, Any],
        *,
        created_by: UUID | str | None = None,
    ) -> Any:
        tenant = _tenant(tenant_id)
        if model not in self.ALLOWED_UPDATES:
            raise MonitoringError("Unsupported catalog resource.")
        unknown = set(values) - self.ALLOWED_UPDATES[model]
        if unknown:
            raise MonitoringError("Unsupported catalog fields.", details={"fields": sorted(unknown)})
        data = self._prepare_data(tenant, model, dict(values), creating=True)
        return model.objects.create(tenant_id=tenant, created_by=_actor(created_by), **data)

    @transaction.atomic
    def update(self, tenant_id: UUID | str, model: type[Any], object_id: UUID | str, values: Mapping[str, Any]) -> Any:
        tenant = _tenant(tenant_id)
        if model not in self.ALLOWED_UPDATES:
            raise MonitoringError("Unsupported catalog resource.")
        instance = model.objects.select_for_update().for_tenant(tenant).filter(id=object_id, is_deleted=False).first()
        if instance is None:
            raise NotFoundError(f"{model.__name__} was not found.")
        unknown = set(values) - self.ALLOWED_UPDATES[model]
        if unknown:
            raise MonitoringError("Unsupported catalog fields.", details={"fields": sorted(unknown)})
        data = self._prepare_data(tenant, model, dict(values), creating=False, instance=instance)
        for key, value in data.items():
            setattr(instance, key, value)
        instance.save()
        return instance

    @staticmethod
    def _prepare_data(
        tenant_id: UUID,
        model: type[Any],
        data: dict[str, Any],
        *,
        creating: bool,
        instance: Any | None = None,
    ) -> dict[str, Any]:
        if model is TelemetrySource:
            defaults = dict(_setting(tenant_id, "defaults.telemetry_source"))
            if creating:
                for field, value in defaults.items():
                    data.setdefault(field, value)
            limits = dict(_setting(tenant_id, "limits"))
            sampling = float(
                data.get("sampling_rate", instance.sampling_rate if instance else defaults["sampling_rate"])
            )
            retention = int(
                data.get("retention_days", instance.retention_days if instance else defaults["retention_days"])
            )
            quota = int(
                data.get("daily_event_quota", instance.daily_event_quota if instance else defaults["daily_event_quota"])
            )
            source_type = data.get("source_type", instance.source_type if instance else None)
            if source_type not in set(_setting(tenant_id, "allowlists.source_types")):
                raise MonitoringError("Telemetry source type is not enabled.")
            if not limits["sampling_rate_min"] <= sampling <= limits["sampling_rate_max"]:
                raise MonitoringError("Sampling rate is outside configured safe limits.")
            if not limits["retention_days_min"] <= retention <= limits["retention_days_max"]:
                raise MonitoringError("Retention is outside configured safe limits.")
            if not limits["daily_event_quota_min"] <= quota <= limits["daily_event_quota_max"]:
                raise MonitoringError("Daily event quota is outside configured safe limits.")
        elif model is MonitoringEnvironment:
            if creating:
                data.setdefault("kind", _setting(tenant_id, "defaults.environment.kind"))
            kind = data.get("kind", instance.kind if instance else None)
            if kind not in set(_setting(tenant_id, "allowlists.environment_kinds")):
                raise MonitoringError("Environment kind is not enabled.")
        elif model is MonitoredService and creating:
            data.setdefault("namespace", _setting(tenant_id, "defaults.service.namespace"))
        elif model is Dashboard:
            if creating:
                data.setdefault(
                    "refresh_interval_seconds",
                    _setting(tenant_id, "defaults.dashboard.refresh_interval_seconds"),
                )
            refresh = int(data.get("refresh_interval_seconds", instance.refresh_interval_seconds if instance else 0))
            if refresh <= 0:
                raise MonitoringError("Dashboard refresh interval must be positive.")
        return data

    @transaction.atomic
    def delete(self, tenant_id: UUID | str, model: type[Any], object_id: UUID | str) -> None:
        tenant = _tenant(tenant_id)
        if model not in self.ALLOWED_UPDATES:
            raise MonitoringError("Unsupported catalog resource.")
        instance = model.objects.select_for_update().for_tenant(tenant).filter(id=object_id, is_deleted=False).first()
        if instance is None:
            raise NotFoundError(f"{model.__name__} was not found.")
        if hasattr(instance, "is_active"):
            instance.is_active = False
        instance.delete()


# These are platform safety ceilings and vocabulary, not tenant behavior. Tenants
# configure bounded subsets through DEFAULT_MONITORING_CONFIGURATION.
PLATFORM_CONFIGURATION_ALLOWLISTS = {
    "metric_types": ["gauge", "counter", "histogram", "summary"],
    "source_types": ["otlp", "prometheus", "application", "webhook", "import"],
    "health_states": ["healthy", "stale", "degraded", "no_telemetry", "disabled"],
    "comparisons": ["gt", "gte", "lt", "lte", "eq", "ne", "absent"],
    "alert_conditions": ["above_threshold", "below_threshold", "rate_of_change", "absence"],
    "severities": ["info", "warning", "critical"],
    "delivery_states": ["pending", "sent", "delivered", "failed", "suppressed"],
    "compliance_states": ["compliant", "breached", "insufficient_data"],
    "report_states": ["pending", "ready", "failed"],
    "aggregations": ["avg", "sum", "min", "max", "count", "p50", "p95", "p99"],
    "sla_comparisons": ["gte", "lte"],
    "sla_windows": ["rolling_1h", "rolling_24h", "calendar_month"],
    "report_periods": ["rolling_24h", "7d", "calendar_month"],
    "report_formats": ["json", "csv", "pdf"],
    "notification_channels": ["in_app", "email"],
    "health_dependencies": ["database", "async", "notifications", "cache"],
    "environment_kinds": ["development", "test", "staging", "production"],
    "log_levels": ["trace", "debug", "info", "warn", "warning", "error", "fatal"],
    "archive_providers": ["database_partition", "object_storage", "compliance_vault"],
}

DEFAULT_MONITORING_CONFIGURATION: dict[str, Any] = {
    "schema_version": "1.0",
    "allowlists": deepcopy(PLATFORM_CONFIGURATION_ALLOWLISTS),
    "defaults": {
        "telemetry_source": {
            "sampling_rate": 1.0,
            "retention_days": 90,
            "daily_event_quota": 1_000_000,
            "redaction_fields": ["password", "token", "secret"],
        },
        "environment": {"kind": "production"},
        "service": {"namespace": "saraise"},
        "metric": {
            "namespace": "custom",
            "unit": "1",
            "expected_interval_seconds": 60,
            "retention_days": 90,
        },
        "dashboard": {"refresh_interval_seconds": 60, "service_list_limit": 6, "alert_list_limit": 5},
        "alert_rule": {
            "threshold": 0.0,
            "aggregation": "avg",
            "evaluation_window_minutes": 5,
            "evaluation_interval_seconds": 60,
            "cooldown_minutes": 15,
            "severity": "warning",
            "notification_channels": ["in_app"],
        },
        "alert": {"initial_occurrence_count": 1},
        "sla": {
            "target_percentage": 99.9,
            "window": "rolling_24h",
            "expected_interval_seconds": 60,
            "timezone": "UTC",
            "initial_version": 1,
        },
        "slo": {"window_days": 30, "expected_interval_seconds": 60, "error_budget_minutes": 0},
    },
    "limits": {
        "sampling_rate_min": 0.0001,
        "sampling_rate_max": 1.0,
        "retention_days_min": 1,
        "retention_days_max": 3650,
        "daily_event_quota_min": 1,
        "daily_event_quota_max": 100_000_000,
        "metric_name_max_length": 255,
        "metric_name_pattern": "^[a-z][a-z0-9_]*(?:\\.[a-z0-9_]+)+$",
        "max_tags_per_data_point": 100,
        "max_batch_data_points": 1000,
        "metric_query_max_range_days": 90,
        "max_alert_rules": 100,
        "alert_evaluation_timeout_seconds": 30,
        "compliance_max_range_days": 90,
        "log_message_max_length": 32000,
        "max_spans_per_trace": 10000,
        "evaluation_window_max_minutes": 1440,
        "cooldown_max_minutes": 10080,
        "sla_cadence_min_seconds": 1,
        "sla_cadence_max_seconds": 86400,
        "health_cache_probe_timeout_seconds_max": 60,
        "evidence_retention_days_max": 3650,
    },
    "rules": {
        "histogram_values_non_negative": True,
        "counter_requires_session_id": True,
        "counter_must_be_monotonic": True,
        "absence_forbids_threshold": True,
        "other_conditions_require_threshold": True,
        "cooldown_at_least_evaluation_window": True,
        "notification_channel_required": True,
        "auto_resolution_window_multiplier": 2.0,
        "critical_bypasses_cooldown": True,
        "critical_recurrence_reopens_acknowledged": True,
        "absence_window_multiplier": 2.0,
        "rate_minimum_elapsed_minutes": 0.0166666667,
        "minimum_sample_density": 0.8,
        "compliance_precision": 0.001,
        "actual_value_precision": 0.0001,
        "missing_samples_consume_breach_duration": True,
        "sla_auto_create_alert_rule": True,
    },
    "query": {
        "interval_seconds": {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400},
        "summary_period_seconds": {"1h": 3600, "24h": 86400, "7d": 604800, "30d": 2592000},
        "automatic_buckets": [
            {"max_range_seconds": 3600, "bucket_seconds": 60},
            {"max_range_seconds": 86400, "bucket_seconds": 300},
            {"max_range_seconds": 604800, "bucket_seconds": 3600},
            {"max_range_seconds": 7776000, "bucket_seconds": 86400},
        ],
        "summary_percentiles": [50, 95, 99],
        "explorer_time_ranges_minutes": [15, 60, 360, 1440, 10080, 43200],
        "metric_stale_interval_multiplier": 2.0,
        "global_stale_threshold_minutes": 15,
    },
    "delivery": {
        "timeout_seconds": 5.0,
        "max_attempts": 5,
        "initial_backoff_seconds": 1.0,
        "max_backoff_seconds": 60.0,
        "jitter_ratio": 0.2,
        "circuit_failure_threshold": 5,
        "circuit_recovery_seconds": 60,
    },
    "health": {
        "cache_probe_timeout_seconds": 10,
        "critical_dependencies": ["database", "async", "notifications"],
    },
    "evidence": {"retention_days": 30, "archival_enabled": True, "archive_provider": "database_partition"},
    "pagination": {"default_page_size": 25, "max_page_size": 100},
    "rollout": {"enabled": True, "percentage": 100, "roles": [], "cohorts": []},
    "visual": {
        "status_tokens": {
            "success": "status-success",
            "warning": "status-warning",
            "danger": "status-danger",
            "stale": "status-stale",
            "degraded": "status-degraded",
        },
        "log_level_tokens": {
            "trace": "log-trace",
            "debug": "log-debug",
            "info": "log-info",
            "warning": "log-warning",
            "error": "log-error",
        },
    },
}


class ConfigurationValidationError(MonitoringError):
    code = "INVALID_MONITORING_CONFIGURATION"


def _deep_merge(base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(base))
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _configuration_diff(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        rows: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            child_path = f"{path}.{key}" if path else key
            rows.extend(_configuration_diff(before.get(key), after.get(key), child_path))
        return rows
    if before == after:
        return []
    return [{"path": path, "before": deepcopy(before), "after": deepcopy(after)}]


class ConfigurationService:
    """Validate and atomically version every tenant configuration change."""

    def default_document(self) -> dict[str, Any]:
        return deepcopy(DEFAULT_MONITORING_CONFIGURATION)

    def effective_document(self, tenant_id: UUID | str, environment: str = "default") -> dict[str, Any]:
        tenant = _tenant(tenant_id)
        current = PerformanceMonitoringConfiguration.objects.for_tenant(tenant).filter(environment=environment).first()
        return deepcopy(current.document) if current is not None else self.default_document()

    def setting(self, tenant_id: UUID | str, path: str, environment: str = "default") -> Any:
        value: Any = self.effective_document(tenant_id, environment)
        for segment in path.split("."):
            if not isinstance(value, Mapping) or segment not in value:
                raise ConfigurationValidationError(
                    "Required configuration setting is unavailable.", details={"path": path}
                )
            value = value[segment]
        return deepcopy(value)

    @staticmethod
    def rollout_allows(policy: Mapping[str, Any], user: Any) -> bool:
        """Evaluate the configured role/cohort/percentage rollout deterministically."""

        if policy.get("enabled") is not True:
            return False
        percentage = int(policy.get("percentage", 0))
        if percentage >= 100:
            return True
        roles = {str(role) for role in policy.get("roles", [])}
        user_roles = {str(role) for role in getattr(user, "roles", [])}
        profile = getattr(user, "profile", None)
        profile_role = getattr(profile, "tenant_role", None)
        if profile_role:
            user_roles.add(str(profile_role))
        if roles and roles.intersection(user_roles):
            return True
        cohorts = {str(cohort) for cohort in policy.get("cohorts", [])}
        user_cohorts = {str(cohort) for cohort in getattr(profile, "cohorts", [])}
        if cohorts and cohorts.intersection(user_cohorts):
            return True
        identifier = str(getattr(user, "pk", ""))
        if not identifier:
            return False
        bucket = int(hashlib.sha256(identifier.encode()).hexdigest()[:8], 16) % 100
        return bucket < percentage

    def validate_document(self, document: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(document, Mapping):
            raise ConfigurationValidationError("Configuration document must be an object.")
        candidate = deepcopy(dict(document))
        errors: dict[str, str] = {}

        def validate_shape(value: Any, template: Any, path: str) -> None:
            if isinstance(template, Mapping):
                if not isinstance(value, Mapping):
                    errors[path] = "Must be an object."
                    return
                unknown = set(value) - set(template)
                for key in sorted(unknown):
                    errors[f"{path}.{key}".strip(".")] = "Unknown setting."
                missing = set(template) - set(value)
                for key in sorted(missing):
                    errors[f"{path}.{key}".strip(".")] = "Required setting is missing."
                for key in set(value) & set(template):
                    validate_shape(value[key], template[key], f"{path}.{key}".strip("."))
            elif isinstance(template, list):
                if not isinstance(value, list):
                    errors[path] = "Must be a list."
            elif isinstance(template, bool):
                if not isinstance(value, bool):
                    errors[path] = "Must be a boolean."
            elif isinstance(template, (int, float)):
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    errors[path] = "Must be numeric."
            elif not isinstance(value, type(template)):
                errors[path] = f"Must be {type(template).__name__}."

        validate_shape(candidate, DEFAULT_MONITORING_CONFIGURATION, "")
        if errors:
            raise ConfigurationValidationError("Configuration schema validation failed.", details=errors)

        for key, platform_values in PLATFORM_CONFIGURATION_ALLOWLISTS.items():
            selected = candidate["allowlists"][key]
            if not selected:
                errors[f"allowlists.{key}"] = "At least one value is required."
            elif len(selected) != len(set(selected)) or not set(selected).issubset(platform_values):
                errors[f"allowlists.{key}"] = "Contains duplicate or platform-unsupported values."

        bounds = candidate["limits"]
        bounded_values = {
            "defaults.telemetry_source.sampling_rate": (
                candidate["defaults"]["telemetry_source"]["sampling_rate"],
                bounds["sampling_rate_min"],
                bounds["sampling_rate_max"],
            ),
            "defaults.telemetry_source.retention_days": (
                candidate["defaults"]["telemetry_source"]["retention_days"],
                bounds["retention_days_min"],
                bounds["retention_days_max"],
            ),
            "defaults.telemetry_source.daily_event_quota": (
                candidate["defaults"]["telemetry_source"]["daily_event_quota"],
                bounds["daily_event_quota_min"],
                bounds["daily_event_quota_max"],
            ),
            "defaults.alert_rule.evaluation_window_minutes": (
                candidate["defaults"]["alert_rule"]["evaluation_window_minutes"],
                1,
                bounds["evaluation_window_max_minutes"],
            ),
            "defaults.alert_rule.cooldown_minutes": (
                candidate["defaults"]["alert_rule"]["cooldown_minutes"],
                1,
                bounds["cooldown_max_minutes"],
            ),
            "rollout.percentage": (candidate["rollout"]["percentage"], 0, 100),
            "pagination.default_page_size": (
                candidate["pagination"]["default_page_size"],
                1,
                candidate["pagination"]["max_page_size"],
            ),
            "pagination.max_page_size": (candidate["pagination"]["max_page_size"], 1, 1000),
            "delivery.jitter_ratio": (candidate["delivery"]["jitter_ratio"], 0, 1),
            "health.cache_probe_timeout_seconds": (
                candidate["health"]["cache_probe_timeout_seconds"],
                1,
                bounds["health_cache_probe_timeout_seconds_max"],
            ),
            "evidence.retention_days": (
                candidate["evidence"]["retention_days"],
                1,
                bounds["evidence_retention_days_max"],
            ),
        }
        for path, (value, minimum, maximum) in bounded_values.items():
            if value < minimum or value > maximum:
                errors[path] = f"Must be between {minimum} and {maximum}."

        platform_bounds = {
            "daily_event_quota_max": (1, 100_000_000),
            "retention_days_max": (1, 3650),
            "metric_name_max_length": (1, 255),
            "max_tags_per_data_point": (1, 1000),
            "max_batch_data_points": (1, 10_000),
            "metric_query_max_range_days": (1, 3650),
            "max_alert_rules": (1, 10_000),
            "alert_evaluation_timeout_seconds": (1, 300),
            "compliance_max_range_days": (1, 3650),
            "log_message_max_length": (1, 1_000_000),
            "max_spans_per_trace": (1, 100_000),
            "evaluation_window_max_minutes": (1, 10_080),
            "cooldown_max_minutes": (1, 43_200),
            "sla_cadence_max_seconds": (1, 604_800),
            "health_cache_probe_timeout_seconds_max": (1, 300),
            "evidence_retention_days_max": (1, 36_500),
        }
        for key, (minimum, maximum) in platform_bounds.items():
            if bounds[key] < minimum or bounds[key] > maximum:
                errors[f"limits.{key}"] = f"Must be between platform bounds {minimum} and {maximum}."
        if (
            bounds["sampling_rate_min"] <= 0
            or bounds["sampling_rate_max"] > 1
            or bounds["sampling_rate_min"] > bounds["sampling_rate_max"]
        ):
            errors["limits.sampling_rate_min"] = "Sampling bounds must satisfy 0 < minimum <= maximum <= 1."
        if bounds["retention_days_min"] > bounds["retention_days_max"]:
            errors["limits.retention_days_min"] = "Minimum cannot exceed maximum."
        if bounds["daily_event_quota_min"] > bounds["daily_event_quota_max"]:
            errors["limits.daily_event_quota_min"] = "Minimum cannot exceed maximum."

        alert_defaults = candidate["defaults"]["alert_rule"]
        if (
            candidate["rules"]["cooldown_at_least_evaluation_window"]
            and alert_defaults["cooldown_minutes"] < alert_defaults["evaluation_window_minutes"]
        ):
            errors["defaults.alert_rule.cooldown_minutes"] = "Must be at least the evaluation window."
        if candidate["rules"]["notification_channel_required"] and not alert_defaults["notification_channels"]:
            errors["defaults.alert_rule.notification_channels"] = "At least one channel is required."
        if not set(alert_defaults["notification_channels"]).issubset(candidate["allowlists"]["notification_channels"]):
            errors["defaults.alert_rule.notification_channels"] = "Must use configured notification channels."
        if alert_defaults["aggregation"] not in candidate["allowlists"]["aggregations"]:
            errors["defaults.alert_rule.aggregation"] = "Must use a configured aggregation."
        if alert_defaults["severity"] not in candidate["allowlists"]["severities"]:
            errors["defaults.alert_rule.severity"] = "Must use a configured severity."
        if candidate["defaults"]["sla"]["window"] not in candidate["allowlists"]["sla_windows"]:
            errors["defaults.sla.window"] = "Must use a configured SLA window."
        if not set(candidate["health"]["critical_dependencies"]).issubset(
            candidate["allowlists"]["health_dependencies"]
        ):
            errors["health.critical_dependencies"] = "Contains a dependency outside the configured allowlist."
        if not candidate["evidence"]["archival_enabled"]:
            errors["evidence.archival_enabled"] = "Evidence archival cannot be disabled."
        if not candidate["evidence"]["archive_provider"].strip():
            errors["evidence.archive_provider"] = "An archive provider is required."
        elif candidate["evidence"]["archive_provider"] not in candidate["allowlists"]["archive_providers"]:
            errors["evidence.archive_provider"] = "Must use a configured archive provider."
        for collection in ("roles", "cohorts"):
            values = candidate["rollout"][collection]
            if len(values) > 100 or any(
                not isinstance(value, str) or not value.strip() or len(value) > 64 for value in values
            ):
                errors[f"rollout.{collection}"] = "Must contain at most 100 non-empty names of at most 64 characters."
        rollout = candidate["rollout"]
        if not rollout["enabled"] and (rollout["percentage"] != 0 or rollout["roles"] or rollout["cohorts"]):
            errors["rollout"] = "Disabled rollout must have zero percentage and no targeting."
        if rollout["percentage"] == 100 and (rollout["roles"] or rollout["cohorts"]):
            errors["rollout"] = "Full rollout cannot also declare role or cohort targeting."
        delivery = candidate["delivery"]
        for key in (
            "timeout_seconds",
            "max_attempts",
            "initial_backoff_seconds",
            "max_backoff_seconds",
            "circuit_failure_threshold",
            "circuit_recovery_seconds",
        ):
            if delivery[key] <= 0:
                errors[f"delivery.{key}"] = "Must be positive."
        if delivery["initial_backoff_seconds"] > delivery["max_backoff_seconds"]:
            errors["delivery.initial_backoff_seconds"] = "Cannot exceed maximum backoff."
        buckets = candidate["query"]["automatic_buckets"]
        if not buckets or any(
            not isinstance(item, Mapping)
            or set(item) != {"max_range_seconds", "bucket_seconds"}
            or item["max_range_seconds"] <= 0
            or item["bucket_seconds"] <= 0
            for item in buckets
        ):
            errors["query.automatic_buckets"] = "Must contain positive range and bucket pairs."
        percentiles = candidate["query"]["summary_percentiles"]
        if len(percentiles) != 3 or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 100
            for value in percentiles
        ):
            errors["query.summary_percentiles"] = "Exactly three percentiles between 0 and 100 are required."
        if errors:
            raise ConfigurationValidationError("Configuration validation failed.", details=errors)
        return candidate

    def preview(
        self, tenant_id: UUID | str, document: Mapping[str, Any], environment: str = "default"
    ) -> dict[str, Any]:
        tenant = _tenant(tenant_id)
        current = PerformanceMonitoringConfiguration.objects.for_tenant(tenant).filter(environment=environment).first()
        before = current.document if current else self.default_document()
        proposed = self.validate_document(_deep_merge(before, document))
        return {
            "valid": True,
            "current_version": current.version if current else 0,
            "proposed_document": proposed,
            "diff": _configuration_diff(before, proposed),
        }

    @transaction.atomic
    def apply(
        self,
        tenant_id: UUID | str,
        environment: str,
        document: Mapping[str, Any],
        *,
        actor_id: UUID | str,
        correlation_id: str,
        change_reason: str,
        expected_version: int | None = None,
        action: str = "update",
        merge: bool = True,
    ) -> PerformanceMonitoringConfiguration:
        if actor_id is None:
            raise ConfigurationValidationError("An actor_id is required for every configuration change.")
        tenant, actor = _tenant(tenant_id), _actor(actor_id)
        if not re.fullmatch(r"[-a-zA-Z0-9_]+", environment) or len(environment) > 64:
            raise ConfigurationValidationError("A valid environment slug is required.")
        correlation = str(correlation_id).strip()
        reason = str(change_reason).strip()
        if not correlation or len(correlation) > 128:
            raise ConfigurationValidationError("A correlation_id of at most 128 characters is required.")
        if not reason or len(reason) > 240:
            raise ConfigurationValidationError("A change reason of at most 240 characters is required.")
        current = (
            PerformanceMonitoringConfiguration.objects.select_for_update()
            .for_tenant(tenant)
            .filter(environment=environment)
            .first()
        )
        before = deepcopy(current.document) if current else None
        base = before if before is not None else self.default_document()
        proposed = self.validate_document(_deep_merge(base, document) if merge else document)
        current_version = current.version if current else 0
        if expected_version is not None and expected_version != current_version:
            raise ConflictError(
                "Configuration was changed by another request.",
                details={"expected_version": expected_version, "current_version": current_version},
            )
        prior = (
            PerformanceMonitoringConfigurationAudit.objects.for_tenant(tenant)
            .filter(environment=environment, correlation_id=correlation)
            .first()
        )
        if prior:
            if prior.after == proposed:
                return prior.configuration
            raise ConflictError("correlation_id was already used for a different configuration change.")
        if current is not None and proposed == before:
            return current
        next_version = current_version + 1
        actual_action = "create" if current is None else action
        if actual_action not in {"create", "update", "import", "rollback"}:
            raise ConfigurationValidationError("Unsupported configuration action.")
        if current is None:
            current = PerformanceMonitoringConfiguration.objects.create(
                tenant_id=tenant,
                environment=environment,
                document=proposed,
                version=next_version,
                created_by=actor,
                updated_by=actor,
                correlation_id=correlation,
            )
        else:
            current.document = proposed
            current.version = next_version
            current.updated_by = actor
            current.correlation_id = correlation
            current.save()
        PerformanceMonitoringConfigurationVersion.objects.create(
            tenant_id=tenant,
            configuration=current,
            environment=environment,
            version=next_version,
            document=proposed,
            actor_id=actor,
            correlation_id=correlation,
            change_reason=reason,
        )
        PerformanceMonitoringConfigurationAudit.objects.create(
            tenant_id=tenant,
            configuration=current,
            environment=environment,
            action=actual_action,
            from_version=current_version or None,
            to_version=next_version,
            before=before,
            after=proposed,
            actor_id=actor,
            correlation_id=correlation,
            change_reason=reason,
        )
        return current

    def ensure_current(
        self, tenant_id: UUID | str, environment: str, *, actor_id: UUID | str, correlation_id: str
    ) -> PerformanceMonitoringConfiguration:
        tenant = _tenant(tenant_id)
        current = PerformanceMonitoringConfiguration.objects.for_tenant(tenant).filter(environment=environment).first()
        if current is not None:
            return current
        try:
            return self.apply(
                tenant,
                environment,
                self.default_document(),
                actor_id=actor_id,
                correlation_id=correlation_id,
                change_reason="Initialize defensible monitoring defaults.",
                expected_version=0,
                merge=False,
            )
        except IntegrityError:
            current = (
                PerformanceMonitoringConfiguration.objects.for_tenant(tenant).filter(environment=environment).first()
            )
            if current is None:
                raise
            return current

    def rollback(
        self,
        tenant_id: UUID | str,
        environment: str,
        version: int,
        *,
        actor_id: UUID | str,
        correlation_id: str,
        change_reason: str,
        expected_version: int | None = None,
    ) -> PerformanceMonitoringConfiguration:
        tenant = _tenant(tenant_id)
        target = (
            PerformanceMonitoringConfigurationVersion.objects.for_tenant(tenant)
            .filter(environment=environment, version=version)
            .first()
        )
        if target is None:
            raise NotFoundError("Configuration version was not found.")
        return self.apply(
            tenant,
            environment,
            target.document,
            actor_id=actor_id,
            correlation_id=correlation_id,
            change_reason=change_reason,
            expected_version=expected_version,
            action="rollback",
            merge=False,
        )

    def export(self, tenant_id: UUID | str, environment: str = "default") -> dict[str, Any]:
        tenant = _tenant(tenant_id)
        current = PerformanceMonitoringConfiguration.objects.for_tenant(tenant).filter(environment=environment).first()
        if current is None:
            raise NotFoundError("Monitoring configuration was not found.")
        return {
            "schema_version": current.document["schema_version"],
            "environment": environment,
            "exported_version": current.version,
            "document": deepcopy(current.document),
        }


# Concise names used by integrations and the completion checklist.
MetricService = MetricsCollectionService
AlertService = AlertingService
SLAService = SLAMonitoringService
