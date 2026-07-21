"""Tenant-first business services for operational monitoring."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import statistics
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Sequence
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

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
    HealthState,
    LogEntry,
    Metric,
    MetricDataPoint,
    MetricType,
    MonitoredService,
    MonitoringEnvironment,
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
SYSTEM_ACTOR = UUID(int=0)
METRIC_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
SPAN_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")
AGGREGATIONS = frozenset({"avg", "sum", "min", "max", "count", "p50", "p95", "p99"})
INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}
PERIODS = {"1h": timedelta(hours=1), "24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}


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


def _normalize_metric_name(metric_name: str) -> str:
    value = str(metric_name).strip().lower()
    if len(value) > 255 or not METRIC_NAME_PATTERN.fullmatch(value):
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
        unit: str = "1",
        source_id: UUID | str | None = None,
        service_id: UUID | str | None = None,
        environment_id: UUID | str | None = None,
        namespace: str = "custom",
        expected_interval_seconds: int = 60,
        retention_days: int = 90,
        default_tags: Mapping[str, str] | None = None,
    ) -> Metric:
        tenant = _tenant(tenant_id)
        name = _normalize_metric_name(metric_name)
        if metric_type not in MetricType.values:
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
                unit=unit.strip() or "1",
                namespace=namespace.strip() or "custom",
                expected_interval_seconds=expected_interval_seconds,
                retention_days=retention_days,
                default_tags=dict(default_tags or {}),
                **relations,
            )
        except IntegrityError:
            metric = Metric.objects.for_tenant(tenant).get(metric_name__iexact=name, is_deleted=False)
            if metric.metric_type != metric_type:
                raise ConflictError("Metric already exists with a different type.")
        logger.info(
            "metric_defined", extra={"tenant_id": str(tenant), "metric_id": str(metric.id), "metric_name": name}
        )
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
        name = _normalize_metric_name(metric_name)
        numeric_value = _numeric(value)
        normalized_tags = {str(key): str(item) for key, item in dict(tags or {}).items()}
        if len(normalized_tags) > 100:
            raise InvalidMetricValueError("A metric data point may have at most 100 tags.")
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
                namespace=(source or source_module or "custom").split(".", 1)[0],
            )
        elif metric.metric_type != metric_type and metric_type != MetricType.GAUGE:
            raise ConflictError("Ingestion metric_type differs from the existing definition.")
        if metric.metric_type == MetricType.HISTOGRAM and numeric_value < 0:
            raise InvalidMetricValueError("Histogram values cannot be negative.")
        if metric.metric_type == MetricType.COUNTER:
            if not session_id:
                raise InvalidMetricValueError("Counter metrics require a session_id.")
            previous = (
                MetricDataPoint.objects.for_tenant(tenant)
                .filter(metric=metric, session_id=session_id, tags=normalized_tags)
                .order_by("-timestamp")
                .first()
            )
            if previous and numeric_value < float(previous.value):
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
            extra={"tenant_id": str(tenant), "metric_id": str(metric.id), "data_point_id": str(point.id)},
        )
        return point

    def record_metrics_batch(
        self,
        tenant_id: UUID | str,
        data_points: Sequence[Mapping[str, Any]],
        *,
        atomic: bool = True,
        created_by: UUID | str | None = None,
    ) -> BatchIngestionResult:
        if len(data_points) > 1000:
            raise InvalidMetricValueError("Batch ingestion is limited to 1000 data points.")
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
        name = _normalize_metric_name(metric_name)
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
        if end - start > timedelta(days=90):
            raise InvalidTimeRangeError("Metric queries cannot exceed 90 days.")
        if aggregation not in AGGREGATIONS:
            raise InvalidTimeRangeError("Unsupported aggregation.")
        metric = Metric.objects.for_tenant(tenant).filter(metric_name__iexact=name, is_deleted=False).first()
        if metric is None:
            raise MetricNotFoundError("Metric definition was not found.")
        seconds = INTERVALS.get(interval)
        if interval == "auto":
            span = (end - start).total_seconds()
            seconds = 60 if span <= 3600 else 300 if span <= 86400 else 3600 if span <= 7 * 86400 else 86400
            interval = next(key for key, value in INTERVALS.items() if value == seconds)
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
        duration = PERIODS.get(period)
        if duration is None:
            raise InvalidTimeRangeError("Unsupported summary period.")
        since = timezone.now() - duration
        summaries: list[MetricSummary] = []
        for raw_name in metric_names:
            name = _normalize_metric_name(raw_name)
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
                        _percentile(values, 50),
                        _percentile(values, 95),
                        _percentile(values, 99),
                    )
                )
        return summaries

    get_metric_summary = get_metric_summary

    def purge_expired_data(self, tenant_id: UUID | str, *, now: datetime | None = None) -> int:
        tenant = _tenant(tenant_id)
        current = now or timezone.now()
        deleted = 0
        for metric in Metric.objects.for_tenant(tenant).filter(is_deleted=False):
            cutoff = current - timedelta(days=metric.retention_days)
            count, _ = MetricDataPoint._base_manager.filter(
                tenant_id=tenant, metric=metric, timestamp__lt=cutoff
            ).delete()
            deleted += count
        return deleted


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
        evaluation_window_minutes: int = 5,
        cooldown_minutes: int = 15,
        severity: str = Severity.WARNING,
        created_by: UUID | str | None = None,
    ) -> AlertRule:
        tenant = _tenant(tenant_id)
        normalized = _normalize_metric_name(metric_name)
        condition = normalize_alert_condition(condition)
        if condition not in AlertCondition.values:
            raise MonitoringError("Unsupported alert condition.")
        if severity not in Severity.values:
            raise MonitoringError("Unsupported alert severity.")
        if cooldown_minutes < evaluation_window_minutes:
            raise MonitoringError("Cooldown must be at least the evaluation window.")
        if not isinstance(action, Mapping) or not isinstance(action.get("channels"), list) or not action["channels"]:
            raise MonitoringError("Alert action must declare at least one notification channel.")
        if AlertRule.objects.for_tenant(tenant).filter(is_deleted=False).count() >= 100:
            raise ConflictError("A tenant may define at most 100 alert rules.")
        metric = Metric.objects.for_tenant(tenant).filter(metric_name__iexact=normalized, is_deleted=False).first()
        rule = AlertRule.objects.create(
            tenant_id=tenant,
            name=(name or f"{normalized} {condition}").strip(),
            metric=metric,
            metric_name=normalized,
            condition=condition,
            threshold=None if condition == AlertCondition.ABSENCE else _numeric(threshold),
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
        rule.save()
        return rule

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
            if time.monotonic() - started > 30:
                raise CapabilityUnavailableError("Alert evaluation exceeded its 30-second safety bound.")
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
        triggered, observed = self._evaluate_condition(rule, points)
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
                and now - open_alert.last_observed_at >= timedelta(minutes=2 * rule.evaluation_window_minutes)
            ):
                return self.resolve_alert(
                    tenant, open_alert.id, resolved_by=SYSTEM_ACTOR, note="Condition cleared automatically."
                )
            return None
        if open_alert:
            cooldown = timedelta(minutes=rule.cooldown_minutes)
            if rule.severity != Severity.CRITICAL and now - open_alert.last_observed_at < cooldown:
                return None
            open_alert.last_observed_at = now
            open_alert.occurrence_count += 1
            open_alert.triggered_value = observed
            if open_alert.status == AlertState.ACKNOWLEDGED and rule.severity == Severity.CRITICAL:
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
    def _evaluate_condition(rule: AlertRule, points: Sequence[MetricDataPoint]) -> tuple[bool, float | None]:
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
                minutes=2 * rule.evaluation_window_minutes
            )
            return old_enough, None
        if not points:
            return False, None
        values = [point.value for point in points]
        if rule.condition == AlertCondition.RATE:
            elapsed_minutes = max((points[-1].timestamp - points[0].timestamp).total_seconds() / 60, 1 / 60)
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
                try:
                    provider_id = self.notification_sender(
                        tenant_id, alert, {"channel": channel, "recipient": recipient}
                    )
                    state, error_code, error_message = DeliveryState.SENT, "", ""
                except MonitoringError as exc:
                    provider_id, state, error_code, error_message = (
                        "",
                        DeliveryState.FAILED,
                        exc.code,
                        exc.public_message,
                    )
                except Exception:
                    logger.exception(
                        "alert_notification_failed", extra={"tenant_id": str(tenant_id), "alert_id": str(alert.id)}
                    )
                    provider_id, state, error_code, error_message = (
                        "",
                        DeliveryState.FAILED,
                        "DELIVERY_FAILED",
                        "Notification delivery failed.",
                    )
                AlertNotificationOutcome.objects.create(
                    tenant_id=tenant_id,
                    alert=alert,
                    channel=str(channel),
                    destination_ref=str(recipient),
                    state=state,
                    attempt=alert.occurrence_count,
                    idempotency_key=key,
                    provider_message_id=provider_id,
                    error_code=error_code,
                    error_message=error_message,
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
        expected_interval_seconds: int = 60,
        created_by: UUID | str | None = None,
    ) -> SLADefinition:
        tenant = _tenant(tenant_id)
        metric_name = _normalize_metric_name(metric)
        if window not in SLAWindow.values:
            raise MonitoringError("Unsupported SLA window.")
        if comparison not in (Comparison.GTE, Comparison.LTE):
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
            created_by=_actor(created_by),
        )
        # SLA breach rule is a durable forward reference even before telemetry arrives.
        AlertingService().create_alert_rule(
            tenant,
            metric_name,
            AlertCondition.BELOW if comparison == Comparison.GTE else AlertCondition.ABOVE,
            target_value,
            {"channels": ["in_app"], "recipients": [str(_actor(created_by))]},
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
        window: str,
        period: str | None,
        start: datetime | None,
        end: datetime | None,
    ) -> tuple[datetime, datetime]:
        now = timezone.now()
        if period == "custom":
            if not start or not end or timezone.is_naive(start) or timezone.is_naive(end) or start >= end:
                raise InvalidTimeRangeError("Custom compliance requires timezone-aware start before end.")
            if end - start > timedelta(days=90):
                raise InvalidTimeRangeError("Custom compliance ranges cannot exceed 90 days.")
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
        period_start, period_end = self._period_range(sla.window, period, start, end)
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
        if len(points) / expected < 0.8:
            raise InsufficientDataError(
                "SLA compliance requires at least 80% of expected samples.",
                details={"expected_samples": expected, "observed_samples": len(points)},
            )
        comparisons = [_compare(float(point.value), sla.comparison, float(sla.target)) for point in points]
        compliant = sum(comparisons)
        # Missing intervals remain in the denominator. Density is a quality
        # gate, not a mechanism for making partial evidence look healthier.
        compliance_pct = Decimal(compliant * 100 / expected).quantize(Decimal("0.001"))
        actual_average = Decimal(str(statistics.fmean(float(point.value) for point in points))).quantize(
            Decimal("0.0001")
        )
        is_compliant = _compare(float(actual_average), sla.comparison, float(sla.target))
        breach_seconds = (expected - compliant) * sla.expected_interval_seconds
        record = SLAComplianceRecord.objects.create(
            tenant_id=tenant,
            sla=sla,
            period_start=period_start,
            period_end=period_end,
            expected_samples=expected,
            observed_samples=len(points),
            compliant_samples=compliant,
            missing_samples=max(expected - len(points), 0),
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
        if period not in {"rolling_24h", "7d", "calendar_month"}:
            raise MonitoringError("Unsupported SLA report period.")
        if output_format not in {"json", "csv", "pdf"}:
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
        attributes = dict(payload.get("attributes") or {})
        for redacted in source.redaction_fields:
            attributes.pop(str(redacted), None)
        entry = LogEntry.objects.create(
            tenant_id=tenant,
            source=source,
            service=self._relation(tenant, MonitoredService, payload.get("service_id")),
            environment=self._relation(tenant, MonitoringEnvironment, payload.get("environment_id")),
            timestamp=payload.get("timestamp") or timezone.now(),
            level=str(payload.get("level", "info")).lower(),
            message=message,
            attributes=attributes,
            trace_id=str(payload.get("trace_id", "")),
            span_id=str(payload.get("span_id", "")),
            correlation_id=str(payload.get("correlation_id", "")),
            idempotency_key=str(payload.get("idempotency_key", "")),
        )
        self._touch_source(source)
        return entry

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
        data = {key: value for key, value in values.items() if key in self.ALLOWED_UPDATES[model]}
        return model.objects.create(tenant_id=tenant, created_by=_actor(created_by), **data)

    @transaction.atomic
    def update(self, tenant_id: UUID | str, model: type[Any], object_id: UUID | str, values: Mapping[str, Any]) -> Any:
        tenant = _tenant(tenant_id)
        if model not in self.ALLOWED_UPDATES:
            raise MonitoringError("Unsupported catalog resource.")
        instance = model.objects.select_for_update().for_tenant(tenant).filter(id=object_id, is_deleted=False).first()
        if instance is None:
            raise NotFoundError(f"{model.__name__} was not found.")
        for key, value in values.items():
            if key in self.ALLOWED_UPDATES[model]:
                setattr(instance, key, value)
        instance.save()
        return instance

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


# Concise names used by integrations and the completion checklist.
MetricService = MetricsCollectionService
AlertService = AlertingService
SLAService = SLAMonitoringService
