import uuid
from datetime import timedelta

import pytest
from django.db.models import QuerySet
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.modules.performance_monitoring.models import (
    Alert,
    AlertCondition,
    AlertNotificationOutcome,
    AlertRule,
    AlertState,
    Comparison,
    ComplianceState,
    Dashboard,
    DeliveryState,
    LogEntry,
    Metric,
    MetricDataPoint,
    MetricType,
    MonitoredService,
    MonitoringEnvironment,
    PerformanceMonitoringConfigurationAudit,
    PerformanceMonitoringConfigurationVersion,
    Severity,
    SLADefinition,
    SLAWindow,
    SourceType,
    TelemetrySource,
    Trace,
)
from src.modules.performance_monitoring.services import (
    AlertingService,
    CapabilityUnavailableError,
    ConfigurationService,
    ConfigurationValidationError,
    ConflictError,
    CoreNotificationAdapter,
    InsufficientDataError,
    InvalidMetricValueError,
    InvalidTimeRangeError,
    MetricNotFoundError,
    MetricsCollectionService,
    MonitoringCatalogService,
    MonitoringError,
    NotFoundError,
    SLAMonitoringService,
    SLANotFoundError,
    SLOMonitoringService,
    TelemetryService,
    deliver_alert_notification_job,
)


@pytest.mark.django_db
def test_metric_ingestion_idempotency_counter_and_query():
    tenant = uuid.uuid4()
    service = MetricsCollectionService()
    first = service.record_metric(
        tenant,
        "orders.processed.count",
        1,
        metric_type=MetricType.COUNTER,
        session_id="worker-1",
        idempotency_key="one",
    )
    assert (
        service.record_metric(
            tenant,
            "ORDERS.PROCESSED.COUNT",
            1,
            metric_type=MetricType.COUNTER,
            session_id="worker-1",
            idempotency_key="one",
        ).id
        == first.id
    )
    with pytest.raises(InvalidMetricValueError):
        service.record_metric(
            tenant, "orders.processed.count", 0, metric_type=MetricType.COUNTER, session_id="worker-1"
        )
    result = service.query_metrics(
        tenant,
        "orders.processed.count",
        start=timezone.now() - timedelta(minutes=1),
        end=timezone.now() + timedelta(minutes=1),
    )
    assert result.data and result.data[0].value == 1


@pytest.mark.django_db
def test_metric_definition_preserves_explicit_boundary_values_and_defaults():
    tenant = uuid.uuid4()
    service = MetricsCollectionService()

    explicit = service.define_metric(
        tenant,
        "worker.queue.depth",
        MetricType.GAUGE,
        unit="items",
        namespace="workers",
        expected_interval_seconds=1,
        retention_days=1,
        default_tags={"queue": "critical"},
    )
    defaulted = service.define_metric(tenant, "worker.queue.latency", MetricType.HISTOGRAM)

    assert explicit.unit == "items"
    assert explicit.namespace == "workers"
    assert explicit.expected_interval_seconds == 1
    assert explicit.retention_days == 1
    assert explicit.default_tags == {"queue": "critical"}
    assert defaulted.unit == "1"
    assert defaulted.namespace == "custom"
    assert defaulted.expected_interval_seconds == 60
    assert defaulted.retention_days == 90


@pytest.mark.django_db
def test_batch_partial_failure_is_explicit():
    result = MetricsCollectionService().record_metrics_batch(
        uuid.uuid4(),
        [
            {"metric_name": "api.latency", "value": 1},
            {"metric_name": "bad name", "value": 1},
        ],
        atomic=False,
    )
    assert (result.accepted, result.rejected, result.errors[0]["code"]) == (1, 1, "INVALID_METRIC_NAME")


@pytest.mark.django_db
def test_metric_summary_reports_empty_series_and_missing_metric_fails_closed():
    tenant = uuid.uuid4()
    service = MetricsCollectionService()
    metric = service.define_metric(tenant, "api.error.rate", MetricType.GAUGE)

    summary = service.get_metric_summary(tenant, [metric.metric_name], "1h")
    assert summary[0].count == 0
    assert summary[0].minimum is None
    assert summary[0].p95 is None

    with pytest.raises(MetricNotFoundError):
        service.get_metric_summary(tenant, ["api.missing"], "1h")


@pytest.mark.django_db
def test_metric_edge_paths_cover_validation_aggregation_and_atomic_rollback():
    tenant = uuid.uuid4()
    service = MetricsCollectionService()

    with pytest.raises(MonitoringError):
        service.define_metric("not-a-uuid", "api.latency", MetricType.GAUGE)

    actor_label = "external-observer"
    metric = service.define_metric(tenant, "api.duration", MetricType.GAUGE, created_by=actor_label)
    assert metric.created_by == uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{actor_label}")
    assert service.define_metric(tenant, "API.DURATION", MetricType.GAUGE).id == metric.id
    with pytest.raises(ConflictError):
        service.define_metric(tenant, "api.duration", MetricType.COUNTER)
    with pytest.raises(InvalidMetricValueError):
        service.define_metric(tenant, "api.disabled", "disabled")

    source = TelemetrySource.objects.create(
        tenant_id=tenant, created_by=uuid.uuid4(), name="collector", source_type="otlp"
    )
    related_metric = service.define_metric(tenant, "api.related", MetricType.GAUGE, source_id=source.id)
    service.record_metric(tenant, related_metric.metric_name, 1)
    source.refresh_from_db()
    assert source.status == "healthy" and source.last_seen_at is not None
    with pytest.raises(MonitoringError, match="Source not found"):
        service.define_metric(tenant, "api.missing.source", MetricType.GAUGE, source_id=uuid.uuid4())

    with pytest.raises(InvalidMetricValueError, match="at most"):
        service.record_metric(tenant, "api.too.many.tags", 1, tags={f"k{i}": "v" for i in range(101)})
    with pytest.raises(InvalidMetricValueError, match="finite"):
        service.record_metric(tenant, "api.bad.value", "NaN")
    with pytest.raises(InvalidMetricValueError, match="timezone"):
        service.record_metric(tenant, "api.naive.time", 1, timestamp=timezone.now().replace(tzinfo=None))
    with pytest.raises(InvalidMetricValueError, match="negative"):
        service.record_metric(tenant, "api.histogram", -1, metric_type=MetricType.HISTOGRAM)

    service.record_metric(tenant, "api.counter", 5, metric_type=MetricType.COUNTER, session_id="worker")
    with pytest.raises(InvalidMetricValueError, match="monotonic"):
        service.record_metric(tenant, "api.counter", 4, metric_type=MetricType.COUNTER, session_id="worker")

    with pytest.raises(MonitoringError):
        service.record_metrics_batch(
            tenant,
            [{"metric_name": "batch.valid", "value": 1}, {"metric_name": "bad name", "value": 1}],
            atomic=True,
        )
    assert not Metric.objects.for_tenant(tenant).filter(metric_name="batch.valid").exists()

    now = timezone.now().replace(second=10, microsecond=0)
    for index, value in enumerate((1, 2, 3)):
        service.record_metric(tenant, "api.duration", value, timestamp=now + timedelta(seconds=index))
    start, end = now - timedelta(seconds=1), now + timedelta(seconds=3)
    assert (
        service.query_metrics(tenant, "api.duration", start=start, end=end, aggregation="sum", interval="1m")
        .data[0]
        .value
        == 6
    )
    assert (
        service.query_metrics(tenant, "api.duration", start=start, end=end, aggregation="min", interval="1m")
        .data[0]
        .value
        == 1
    )
    assert (
        service.query_metrics(tenant, "api.duration", start=start, end=end, aggregation="max", interval="1m")
        .data[0]
        .value
        == 3
    )
    assert (
        service.query_metrics(tenant, "api.duration", start=start, end=end, aggregation="count", interval="1m")
        .data[0]
        .value
        == 3
    )
    assert service.query_metrics(tenant, "api.duration", start=start, end=end, aggregation="p95", interval="1m").data[
        0
    ].value == pytest.approx(2.9)
    with pytest.raises(MonitoringError, match="Unsupported aggregation"):
        service.query_metrics(tenant, "api.duration", start=start, end=end, aggregation="median")


@pytest.mark.django_db
def test_deactivate_metric_soft_deletes_definition_and_purge_is_governed():
    tenant = uuid.uuid4()
    service = MetricsCollectionService()
    metric = service.define_metric(tenant, "api.requests", MetricType.COUNTER)

    service.deactivate_metric(tenant, metric.id)
    metric.refresh_from_db()
    assert metric.is_active is False
    assert metric.is_deleted is True

    with pytest.raises(CapabilityUnavailableError) as exc:
        service.purge_expired_data(tenant)
    assert exc.value.code == "CAPABILITY_UNAVAILABLE"


@pytest.mark.django_db
def test_alert_state_machine_and_tenant_boundary():
    tenant = uuid.uuid4()
    metrics = MetricsCollectionService()
    metrics.record_metric(tenant, "api.latency", 800)
    alerts = AlertingService(
        notification_sender=lambda *_args: pytest.fail(
            "notification delivery must never run in the request transaction"
        )
    )
    rule = alerts.create_alert_rule(
        tenant,
        "api.latency",
        "above_threshold",
        500,
        {"channels": ["in_app"], "recipients": [str(uuid.uuid4())]},
        name="Latency",
    )
    alert = alerts.evaluate_alert_rule(tenant, rule.id)
    assert alert and alert.status == AlertState.FIRING
    job = AsyncJob.objects.get(tenant_id=tenant, payload__alert_id=str(alert.id))
    assert job.command == "performance_monitoring.deliver_alert_notification"
    delivery = OutboxEvent.objects.get(tenant_id=tenant, aggregate_id=job.id)
    assert delivery.event_type == "async_job.enqueued"
    assert delivery.payload["correlation_id"] == job.correlation_id
    acknowledged = alerts.acknowledge_alert(tenant, alert.id, uuid.uuid4())
    assert acknowledged.status == AlertState.ACKNOWLEDGED and acknowledged.acknowledged_by
    assert alerts.resolve_alert(tenant, alert.id, resolved_by=uuid.uuid4()).status == AlertState.RESOLVED
    with pytest.raises(Exception):
        alerts.acknowledge_alert(uuid.uuid4(), alert.id, uuid.uuid4())


@pytest.mark.django_db
def test_alert_rule_invalid_update_rolls_back_and_delete_soft_deactivates():
    tenant = uuid.uuid4()
    service = AlertingService()
    rule = service.create_alert_rule(
        tenant,
        "api.errors",
        "above_threshold",
        10,
        {"channels": ["in_app"], "recipients": ["ops"]},
        name="Error rate",
    )
    before = (rule.condition, rule.threshold, rule.updated_at)

    with pytest.raises(MonitoringError, match="Absence rules"):
        service.update_alert_rule(tenant, rule.id, condition="absence", threshold=5)

    rule.refresh_from_db()
    assert (rule.condition, rule.threshold, rule.updated_at) == before
    service.delete_alert_rule(tenant, rule.id)
    rule.refresh_from_db()
    assert rule.is_active is False
    assert rule.is_deleted is True


@pytest.mark.django_db
def test_alert_rule_policy_rejects_missing_threshold_cooldown_and_channel():
    tenant = uuid.uuid4()
    service = AlertingService()

    with pytest.raises(MonitoringError, match="Threshold is required"):
        service.create_alert_rule(
            tenant,
            "api.errors.missing.threshold",
            AlertCondition.ABOVE,
            None,
            {"channels": ["in_app"], "recipients": ["ops"]},
            name="Missing threshold",
        )
    with pytest.raises(MonitoringError, match="Cooldown must be at least"):
        service.create_alert_rule(
            tenant,
            "api.errors.cooldown",
            AlertCondition.ABOVE,
            1,
            {"channels": ["in_app"], "recipients": ["ops"]},
            evaluation_window_minutes=10,
            cooldown_minutes=1,
            name="Bad cooldown",
        )
    with pytest.raises(MonitoringError, match="notification channel"):
        service.create_alert_rule(
            tenant,
            "api.errors.no.channel",
            AlertCondition.ABOVE,
            1,
            {"channels": [], "recipients": ["ops"]},
            name="No channel",
        )


@pytest.mark.django_db
def test_alert_evaluation_timeout_stops_the_batch(monkeypatch):
    tenant = uuid.uuid4()
    metric = MetricsCollectionService().define_metric(tenant, "api.timeout", MetricType.GAUGE)
    AlertingService().create_alert_rule(
        tenant,
        metric.metric_name,
        AlertCondition.ABOVE,
        1,
        {"channels": ["in_app"], "recipients": ["ops"]},
        name="Timeout guard",
    )
    ticks = iter((1000.0, 1001.0))
    monkeypatch.setattr("src.modules.performance_monitoring.services.time.monotonic", lambda: next(ticks))

    def setting_with_zero_timeout(_tenant, path):
        if path.endswith("alert_evaluation_timeout_seconds"):
            return 0
        return ConfigurationService().setting(_tenant, path)

    monkeypatch.setattr("src.modules.performance_monitoring.services._setting", setting_with_zero_timeout)

    with pytest.raises(CapabilityUnavailableError, match="safety bound"):
        AlertingService().evaluate_alerts(tenant)


@pytest.mark.django_db
def test_alert_auto_resolution_requires_clear_condition_and_elapsed_window():
    tenant = uuid.uuid4()
    metrics = MetricsCollectionService()
    metric = metrics.define_metric(tenant, "api.latency.auto", MetricType.GAUGE)
    metrics.record_metric(
        tenant,
        metric.metric_name,
        900,
        timestamp=timezone.now() - timedelta(seconds=10),
    )
    alerts = AlertingService()
    rule = alerts.create_alert_rule(
        tenant,
        metric.metric_name,
        "above_threshold",
        500,
        {"channels": ["in_app"], "recipients": ["ops"]},
        evaluation_window_minutes=1,
        cooldown_minutes=1,
        name="Latency auto",
    )
    alert = alerts.evaluate_alert_rule(tenant, rule.id)
    assert alert and alert.status == AlertState.FIRING

    metrics.record_metric(tenant, metric.metric_name, 100)
    type(alert).objects.for_tenant(tenant).filter(id=alert.id).update(
        last_observed_at=timezone.now() - timedelta(minutes=10)
    )

    resolved = alerts.evaluate_alert_rule(tenant, rule.id)
    assert resolved is not None
    assert resolved.id == alert.id
    assert resolved.status == AlertState.RESOLVED
    assert resolved.resolution_note == "Condition cleared automatically."


@pytest.mark.django_db
def test_alert_recurrence_respects_cooldown_and_reopens_acknowledged_critical_alert():
    tenant = uuid.uuid4()
    metrics = MetricsCollectionService()
    metric = metrics.define_metric(tenant, "api.latency.recurrence", MetricType.GAUGE)
    metrics.record_metric(tenant, metric.metric_name, 900, timestamp=timezone.now() - timedelta(minutes=2))
    alerts = AlertingService()
    rule = alerts.create_alert_rule(
        tenant,
        metric.metric_name,
        AlertCondition.ABOVE,
        500,
        {"channels": ["in_app"], "recipients": ["ops"]},
        evaluation_window_minutes=5,
        cooldown_minutes=30,
        severity=Severity.CRITICAL,
        name="Critical recurrence",
    )
    first = alerts.evaluate_alert_rule(tenant, rule.id)
    assert first is not None
    acknowledged = alerts.acknowledge_alert(tenant, first.id, uuid.uuid4())

    metrics.record_metric(tenant, metric.metric_name, 950)
    reopened = alerts.evaluate_alert_rule(tenant, rule.id)

    assert reopened is not None
    assert reopened.id == acknowledged.id
    assert reopened.status == AlertState.FIRING
    assert reopened.acknowledged_at is None
    assert reopened.acknowledged_by is None
    assert reopened.occurrence_count == 2


@pytest.mark.django_db
def test_absence_alert_waits_for_sparse_series_safety_window():
    tenant = uuid.uuid4()
    metric = MetricsCollectionService().define_metric(tenant, "worker.heartbeat", MetricType.GAUGE)
    recent = timezone.now() - timedelta(minutes=3)
    MetricDataPoint.objects.create(tenant_id=tenant, metric=metric, value=1, timestamp=recent)
    rule = AlertRule.objects.create(
        tenant_id=tenant,
        created_by=uuid.uuid4(),
        metric=metric,
        metric_name=metric.metric_name,
        condition=AlertCondition.ABSENCE,
        threshold=None,
        evaluation_window_minutes=5,
        cooldown_minutes=1,
        severity=Severity.WARNING,
        action={"channels": ["in_app"], "recipients": ["ops"]},
        name="Worker heartbeat missing",
    )

    assert AlertingService().evaluate_alert_rule(tenant, rule.id) is None
    assert not Alert.objects.for_tenant(tenant).filter(alert_rule=rule).exists()

    old_metric = MetricsCollectionService().define_metric(tenant, "worker.heartbeat.old", MetricType.GAUGE)
    MetricDataPoint.objects.create(
        tenant_id=tenant,
        metric=old_metric,
        value=1,
        timestamp=timezone.now() - timedelta(minutes=11),
    )
    old_rule = AlertRule.objects.create(
        tenant_id=tenant,
        created_by=uuid.uuid4(),
        metric=old_metric,
        metric_name=old_metric.metric_name,
        condition=AlertCondition.ABSENCE,
        threshold=None,
        evaluation_window_minutes=5,
        cooldown_minutes=1,
        severity=Severity.WARNING,
        action={"channels": ["in_app"], "recipients": ["ops"]},
        name="Old worker heartbeat missing",
    )

    alert = AlertingService().evaluate_alert_rule(tenant, old_rule.id)
    assert alert is not None
    assert alert.condition == AlertCondition.ABSENCE
    assert alert.triggered_value is None


@pytest.mark.django_db
def test_notification_job_records_retry_evidence_and_reuses_sent_outcome(monkeypatch):
    tenant = uuid.uuid4()
    metrics = MetricsCollectionService()
    metrics.record_metric(tenant, "api.latency.notify", 900)
    alerts = AlertingService()
    rule = alerts.create_alert_rule(
        tenant,
        "api.latency.notify",
        "above_threshold",
        500,
        {"channels": ["email"], "recipients": ["ops@example.com"]},
        name="Latency notification",
    )
    alert = alerts.evaluate_alert_rule(tenant, rule.id)
    assert alert is not None
    job = AsyncJob.objects.get(tenant_id=tenant, payload__alert_id=str(alert.id))
    attempts = {"count": 0}

    missing_alert_job = AsyncJob.objects.create(
        tenant_id=tenant,
        actor_id="system",
        command=job.command,
        idempotency_key="notify-missing-alert",
        payload={key: value for key, value in job.payload.items() if key != "alert_id"},
        correlation_id="notify-missing-alert",
    )
    with pytest.raises(MonitoringError) as missing_alert:
        deliver_alert_notification_job(missing_alert_job)
    assert missing_alert.value.args == ("Notification job alert is required.",)

    def flaky_sender(_tenant, _alert, _delivery):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise CapabilityUnavailableError("temporary notification failure")
        return "provider-message-1"

    monkeypatch.setattr("src.modules.performance_monitoring.services.CoreNotificationAdapter.send", flaky_sender)
    monkeypatch.setattr("src.modules.performance_monitoring.services.time.sleep", lambda _seconds: None)

    result = deliver_alert_notification_job(job)

    assert result["state"] == DeliveryState.SENT
    assert attempts["count"] == 2
    assert (
        AlertNotificationOutcome.objects.for_tenant(tenant)
        .filter(idempotency_key=job.payload["delivery_key"], state=DeliveryState.FAILED)
        .exists()
    )
    sent = AlertNotificationOutcome.objects.for_tenant(tenant).get(state=DeliveryState.SENT)
    assert sent.provider_message_id == "provider-message-1"
    assert deliver_alert_notification_job(job) == {"outcome_id": str(sent.id), "state": DeliveryState.SENT}


@pytest.mark.django_db
def test_log_ingestion_is_idempotent_and_conflicting_reuse_fails_deterministically():
    tenant = uuid.uuid4()
    actor = uuid.uuid4()
    source = TelemetrySource.objects.create(
        tenant_id=tenant,
        created_by=actor,
        name="application logs",
        source_type=SourceType.APPLICATION,
    )
    environment = MonitoringEnvironment.objects.create(
        tenant_id=tenant,
        created_by=actor,
        name="Production",
        slug="production",
    )
    monitored_service = MonitoredService.objects.create(
        tenant_id=tenant,
        created_by=actor,
        environment=environment,
        name="Orders",
        slug="orders",
    )
    payload = {
        "source_id": source.id,
        "service_id": monitored_service.id,
        "environment_id": environment.id,
        "message": "order accepted",
        "level": "info",
        "idempotency_key": "log-request-1",
        "correlation_id": "request-1",
    }
    service = TelemetryService()

    with pytest.raises(MonitoringError) as missing_source:
        service.ingest_log(tenant, {key: value for key, value in payload.items() if key != "source_id"})
    assert missing_source.value.args == ("Telemetry source is required.",)

    first = service.ingest_log(tenant, payload)
    assert service.ingest_log(tenant, payload).id == first.id

    with pytest.raises(ConflictError):
        service.ingest_log(tenant, {**payload, "message": "different event"})


@pytest.mark.django_db
def test_log_ingestion_recovers_existing_entry_after_database_idempotency_race(monkeypatch):
    tenant = uuid.uuid4()
    actor = uuid.uuid4()
    source = TelemetrySource.objects.create(
        tenant_id=tenant,
        created_by=actor,
        name="race logs",
        source_type=SourceType.APPLICATION,
    )
    payload = {
        "source_id": source.id,
        "message": "worker started",
        "level": "info",
        "idempotency_key": "log-race-1",
        "correlation_id": "request-race-1",
    }
    existing = LogEntry.objects.create(
        tenant_id=tenant,
        source=source,
        timestamp=timezone.now(),
        level="info",
        message="worker started",
        attributes={},
        trace_id="",
        span_id="",
        correlation_id="request-race-1",
        idempotency_key="log-race-1",
    )
    original_first = QuerySet.first
    hidden_precheck = {"used": False}

    def first_with_race(queryset):
        if queryset.model is LogEntry and not hidden_precheck["used"]:
            hidden_precheck["used"] = True
            return None
        return original_first(queryset)

    monkeypatch.setattr(QuerySet, "first", first_with_race)

    recovered = TelemetryService().ingest_log(tenant, payload)

    assert hidden_precheck["used"] is True
    assert recovered.id == existing.id
    assert LogEntry.objects.for_tenant(tenant).filter(source=source, idempotency_key="log-race-1").count() == 1


@pytest.mark.django_db
def test_trace_ingestion_validates_shape_persists_spans_and_replays_existing_trace():
    tenant = uuid.uuid4()
    actor = uuid.uuid4()
    source = TelemetrySource.objects.create(
        tenant_id=tenant,
        created_by=actor,
        name="traces",
        source_type=SourceType.APPLICATION,
    )
    environment = MonitoringEnvironment.objects.create(
        tenant_id=tenant,
        created_by=actor,
        name="Production",
        slug="production",
    )
    service_model = MonitoredService.objects.create(
        tenant_id=tenant,
        created_by=actor,
        environment=environment,
        name="Orders",
        slug="orders",
    )
    now = timezone.now()
    payload = {
        "source_id": source.id,
        "service_id": service_model.id,
        "environment_id": environment.id,
        "trace_id": "a" * 32,
        "name": "checkout",
        "started_at": now,
        "ended_at": now + timedelta(milliseconds=125),
        "duration_ms": 125,
        "status": "ok",
        "attributes": {"http.route": "/orders"},
        "sampled": False,
        "spans": [
            {
                "service_id": service_model.id,
                "span_id": "b" * 16,
                "name": "db",
                "started_at": now,
                "ended_at": now + timedelta(milliseconds=75),
                "duration_ms": 75,
                "status": "error",
                "events": [{"name": "timeout"}],
            }
        ],
    }
    telemetry = TelemetryService()

    with pytest.raises(MonitoringError) as missing_source:
        telemetry.ingest_trace(tenant, {key: value for key, value in payload.items() if key != "source_id"})
    assert missing_source.value.args == ("Telemetry source is required.",)
    with pytest.raises(MonitoringError, match="trace_id"):
        telemetry.ingest_trace(tenant, {**payload, "trace_id": "not-valid"})
    with pytest.raises(MonitoringError) as missing_name:
        telemetry.ingest_trace(
            tenant,
            {key: value for key, value in {**payload, "trace_id": "d" * 32}.items() if key != "name"},
        )
    assert missing_name.value.args == ("Trace name is required.",)
    with pytest.raises(MonitoringError, match="span_id"):
        telemetry.ingest_trace(
            tenant,
            {**payload, "trace_id": "c" * 32, "spans": [{**payload["spans"][0], "span_id": "bad"}]},
        )

    trace = telemetry.ingest_trace(tenant, payload)

    assert trace.environment_id == environment.id
    assert trace.name == "checkout"
    assert trace.status == "ok"
    assert trace.attributes == {"http.route": "/orders"}
    assert trace.sampled is False
    assert trace.span_count == 1
    assert trace.error_span_count == 1
    assert trace.duration_ms == 125
    assert trace.started_at == now
    assert trace.ended_at == now + timedelta(milliseconds=125)
    assert Trace.objects.for_tenant(tenant).count() == 1
    span = trace.spans.get()
    assert span.service_id == service_model.id
    assert span.name == "db"
    assert span.status == "error"
    assert span.duration_ms == 75
    assert span.events == [{"name": "timeout"}]
    source.refresh_from_db()
    assert source.status == "healthy" and source.last_seen_at is not None
    replay = telemetry.ingest_trace(tenant, {**payload, "name": "ignored replay"})
    assert replay.id == trace.id
    default_status_trace = telemetry.ingest_trace(
        tenant,
        {key: value for key, value in {**payload, "trace_id": "e" * 32}.items() if key not in {"sampled", "status"}},
    )
    assert default_status_trace.status == "unset"
    assert default_status_trace.sampled is True


@pytest.mark.django_db
def test_sla_versioning_and_density_compliance():
    tenant = uuid.uuid4()
    metric = MetricsCollectionService().define_metric(tenant, "service.availability", MetricType.GAUGE)
    sla_service = SLAMonitoringService()
    sla = sla_service.define_sla(tenant, "Orders", metric.metric_name, 99, "rolling_1h", comparison="gte")
    now = timezone.now()
    MetricDataPoint.objects.bulk_create(
        [
            MetricDataPoint(tenant_id=tenant, metric=metric, value=100, timestamp=now - timedelta(minutes=index))
            for index in range(49)
        ]
    )
    record = sla_service.check_sla_compliance(tenant, sla.id)
    assert record.is_compliant and record.compliance_percentage < 100
    replacement = sla_service.update_sla(tenant, sla.id, target=99.5)
    assert replacement.version == 2 and replacement.previous_version_id == sla.id


@pytest.mark.django_db
def test_sla_update_delete_and_period_range_guards():
    tenant = uuid.uuid4()
    metric = MetricsCollectionService().define_metric(tenant, "service.period.availability", MetricType.GAUGE)
    service = SLAMonitoringService()
    sla = service.define_sla(tenant, "Orders", metric.metric_name, 99, "calendar_month", comparison="gte")

    renamed = service.update_sla(tenant, sla.id, name="Orders public SLA")
    assert renamed.id == sla.id
    assert renamed.name == "Orders public SLA"

    previous_start, previous_end = service._period_range(tenant, SLAWindow.CALENDAR_MONTH, "previous", None, None)
    assert previous_start.day == 1
    assert previous_start < previous_end

    with pytest.raises(InvalidTimeRangeError, match="timezone-aware"):
        service._period_range(
            tenant,
            SLAWindow.ROLLING_1H,
            "custom",
            timezone.now().replace(tzinfo=None),
            timezone.now(),
        )
    with pytest.raises(SLANotFoundError):
        service.update_sla(tenant, uuid.uuid4(), name="missing")

    service.delete_sla(tenant, sla.id)
    assert SLADefinition.objects.for_tenant(tenant).get(id=sla.id).is_deleted is True
    with pytest.raises(SLANotFoundError):
        service.delete_sla(tenant, uuid.uuid4())


@pytest.mark.django_db
def test_core_notification_adapter_requires_supported_channel_and_recipient():
    tenant = uuid.uuid4()
    metric = MetricsCollectionService().define_metric(tenant, "api.notify.guard", MetricType.GAUGE)
    rule = AlertingService().create_alert_rule(
        tenant,
        metric.metric_name,
        AlertCondition.ABOVE,
        1,
        {"channels": ["in_app"], "recipients": ["ops"]},
        name="Notification guard",
    )
    alert = Alert.objects.create(
        tenant_id=tenant,
        alert_rule=rule,
        metric=metric,
        metric_name=metric.metric_name,
        condition=AlertCondition.ABOVE,
        threshold=1,
        triggered_value=2,
        severity=Severity.WARNING,
        title="Guard",
        deduplication_key="guard",
    )

    with pytest.raises(CapabilityUnavailableError, match="unavailable"):
        CoreNotificationAdapter.send(tenant, alert, {"channel": "sms", "recipient": "ops"})
    with pytest.raises(CapabilityUnavailableError, match="explicit recipient"):
        CoreNotificationAdapter.send(tenant, alert, {"channel": "in_app", "recipient": "tenant-default"})


@pytest.mark.django_db
def test_sla_report_handles_insufficient_data_and_validates_artifact_receipts():
    tenant = uuid.uuid4()
    metric = MetricsCollectionService().define_metric(tenant, "service.report.availability", MetricType.GAUGE)
    service = SLAMonitoringService()
    service.define_sla(tenant, "Orders", metric.metric_name, 99, "rolling_1h", comparison="gte")

    with pytest.raises(CapabilityUnavailableError, match="artifact storage"):
        service.generate_sla_report(tenant, "rolling_24h", output_format="csv")

    with pytest.raises(CapabilityUnavailableError, match="invalid durable receipt"):
        service.generate_sla_report(
            tenant,
            "rolling_24h",
            output_format="csv",
            artifact_writer=lambda *_args: ("artifact://sla.csv", "not-a-sha"),
        )

    report = service.generate_sla_report(
        tenant,
        "rolling_24h",
        output_format="csv",
        artifact_writer=lambda *_args: ("artifact://sla.csv", "a" * 64),
    )

    assert report.artifact_ref == "artifact://sla.csv"
    assert report.summary["summary"]["insufficient_data"] == 1
    assert report.summary["sla_results"][0]["status"] == "insufficient_data"


@pytest.mark.django_db
def test_slo_lifecycle_budget_evaluation_and_validation_paths():
    tenant = uuid.uuid4()
    actor = uuid.uuid4()
    environment = MonitoringEnvironment.objects.create(tenant_id=tenant, created_by=actor, name="Prod", slug="prod")
    monitored = MonitoredService.objects.create(
        tenant_id=tenant,
        created_by=actor,
        environment=environment,
        name="Checkout",
        slug="checkout",
    )
    metric = MetricsCollectionService().define_metric(tenant, "checkout.success", MetricType.GAUGE, created_by=actor)
    service = SLOMonitoringService()

    with pytest.raises(MonitoringError, match="Unsupported SLO comparison"):
        service.create(
            tenant,
            {
                "service_id": monitored.id,
                "indicator_metric_id": metric.id,
                "name": "Bad comparison",
                "comparison": "bad",
                "threshold": 1,
                "objective_percentage": 99,
            },
            created_by=actor,
        )
    with pytest.raises(MonitoringError, match="greater than 0"):
        service.create(
            tenant,
            {
                "service_id": monitored.id,
                "indicator_metric_id": metric.id,
                "name": "Bad objective",
                "comparison": Comparison.GTE,
                "threshold": 1,
                "objective_percentage": 0,
            },
            created_by=actor,
        )

    slo = service.create(
        tenant,
        {
            "service_id": monitored.id,
            "indicator_metric_id": metric.id,
            "name": "Checkout success",
            "comparison": Comparison.GTE,
            "threshold": 99,
            "objective_percentage": 99,
            "window_days": 1,
            "expected_interval_seconds": 60,
        },
        created_by=actor,
    )
    assert slo.error_budget_minutes == 14
    with pytest.raises(InsufficientDataError):
        service.evaluate(tenant, slo.id)

    MetricDataPoint.objects.create(tenant_id=tenant, metric=metric, value=100, timestamp=timezone.now())
    assert service.evaluate(tenant, slo.id).status == ComplianceState.COMPLIANT
    MetricDataPoint.objects.create(tenant_id=tenant, metric=metric, value=90, timestamp=timezone.now())
    breached = service.evaluate(tenant, slo.id)
    assert breached.status == ComplianceState.COMPLIANT
    assert breached.consumed_minutes == 1
    updated = service.update(tenant, slo.id, {"objective_percentage": 99.9})
    assert updated.error_budget_minutes == 1
    with pytest.raises(MonitoringError, match="positive"):
        service.update(tenant, slo.id, {"window_days": 0})
    service.update(
        tenant, slo.id, {"service_id": monitored.id, "indicator_metric_id": metric.id, "name": "Checkout SLO"}
    )
    with pytest.raises(MonitoringError, match="was not found"):
        service.update(tenant, uuid.uuid4(), {"name": "missing"})
    with pytest.raises(MonitoringError, match="was not found"):
        service.create(
            tenant,
            {
                "service_id": uuid.uuid4(),
                "indicator_metric_id": metric.id,
                "name": "Missing service",
                "comparison": Comparison.GTE,
                "threshold": 99,
                "objective_percentage": 99,
            },
            created_by=actor,
        )


@pytest.mark.django_db
def test_configuration_apply_preview_rollback_and_idempotent_correlation():
    tenant = uuid.uuid4()
    actor = uuid.uuid4()
    service = ConfigurationService()

    preview = service.preview(
        tenant,
        {"defaults": {"alert_rule": {"cooldown_minutes": 20}}},
        environment="production",
    )
    assert preview["valid"] is True
    assert any(item["path"] == "defaults.alert_rule.cooldown_minutes" for item in preview["diff"])

    created = service.apply(
        tenant,
        "production",
        {"defaults": {"alert_rule": {"cooldown_minutes": 20}}},
        actor_id=actor,
        correlation_id="pm-cfg-1",
        change_reason="Tune alert cooldown.",
        expected_version=0,
    )
    replay = service.apply(
        tenant,
        "production",
        {"defaults": {"alert_rule": {"cooldown_minutes": 20}}},
        actor_id=actor,
        correlation_id="pm-cfg-1",
        change_reason="Tune alert cooldown.",
        expected_version=1,
    )
    assert replay.id == created.id
    assert created.version == 1
    assert PerformanceMonitoringConfigurationVersion.objects.for_tenant(tenant).count() == 1
    assert PerformanceMonitoringConfigurationAudit.objects.for_tenant(tenant).get().action == "create"

    updated = service.apply(
        tenant,
        "production",
        {"defaults": {"alert_rule": {"cooldown_minutes": 30}}},
        actor_id=actor,
        correlation_id="pm-cfg-2",
        change_reason="Raise cooldown.",
        expected_version=1,
    )
    assert updated.version == 2
    rolled_back = service.rollback(
        tenant,
        "production",
        1,
        actor_id=actor,
        correlation_id="pm-cfg-3",
        change_reason="Rollback cooldown.",
        expected_version=2,
    )
    assert rolled_back.version == 3
    assert rolled_back.document["defaults"]["alert_rule"]["cooldown_minutes"] == 20
    assert service.export(tenant, "production")["exported_version"] == 3

    with pytest.raises(ConflictError):
        service.apply(
            tenant,
            "production",
            {"defaults": {"alert_rule": {"cooldown_minutes": 40}}},
            actor_id=actor,
            correlation_id="pm-cfg-1",
            change_reason="Conflicting replay.",
            expected_version=3,
        )


@pytest.mark.django_db
def test_configuration_validation_and_rollout_fail_closed():
    service = ConfigurationService()
    document = service.default_document()
    document["allowlists"]["notification_channels"] = []
    with pytest.raises(ConfigurationValidationError) as exc:
        service.validate_document(document)
    assert "allowlists.notification_channels" in exc.value.details

    disabled = {"enabled": False, "percentage": 10, "roles": [], "cohorts": []}
    with pytest.raises(ConfigurationValidationError):
        service.validate_document({**service.default_document(), "rollout": disabled})

    user = type("User", (), {"pk": "user-1", "roles": ["operator"], "profile": None})()
    assert service.rollout_allows({"enabled": True, "percentage": 0, "roles": ["operator"], "cohorts": []}, user)
    assert not service.rollout_allows({"enabled": False, "percentage": 100, "roles": [], "cohorts": []}, user)


@pytest.mark.django_db
def test_monitoring_catalog_defaults_and_configured_limits_are_enforced():
    tenant = uuid.uuid4()
    actor = uuid.uuid4()
    catalog = MonitoringCatalogService()

    source = catalog.create(
        tenant,
        TelemetrySource,
        {"name": "App", "source_type": SourceType.APPLICATION},
        created_by=actor,
    )
    assert (
        source.retention_days
        == ConfigurationService().default_document()["defaults"]["telemetry_source"]["retention_days"]
    )
    with pytest.raises(MonitoringError, match="Sampling rate"):
        catalog.update(tenant, TelemetrySource, source.id, {"sampling_rate": 2})
    with pytest.raises(MonitoringError, match="Unsupported catalog fields"):
        catalog.create(tenant, TelemetrySource, {"name": "Bad", "source_type": SourceType.APPLICATION, "sql": "x"})

    environment = catalog.create(
        tenant,
        MonitoringEnvironment,
        {"name": "Prod", "slug": "prod"},
        created_by=actor,
    )
    monitored_service = catalog.create(
        tenant,
        MonitoredService,
        {"environment": environment, "source": source, "name": "Orders", "slug": "orders"},
        created_by=actor,
    )
    assert monitored_service.namespace == "saraise"
    with pytest.raises(MonitoringError, match="positive"):
        catalog.create(tenant, Dashboard, {"name": "Bad", "refresh_interval_seconds": 0}, created_by=actor)

    catalog.delete(tenant, TelemetrySource, source.id)
    source.refresh_from_db()
    assert source.is_deleted is True
    assert source.is_active is False


@pytest.mark.django_db
def test_configuration_service_rejects_structural_bounds_and_missing_settings():
    service = ConfigurationService()
    tenant = uuid.uuid4()
    actor = uuid.uuid4()

    with pytest.raises(ConfigurationValidationError) as non_mapping:
        service.validate_document(["not", "a", "mapping"])
    assert "object" in str(non_mapping.value)

    document = service.default_document()
    document["limits"]["sampling_rate_min"] = 0
    document["limits"]["retention_days_min"] = 10
    document["limits"]["retention_days_max"] = 1
    document["defaults"]["alert_rule"]["notification_channels"] = []
    document["query"]["automatic_buckets"] = [{"max_range_seconds": 0, "bucket_seconds": 60}]
    document["query"]["summary_percentiles"] = [50, 95, 100]
    document["rollout"] = {"enabled": True, "percentage": 100, "roles": ["ops"], "cohorts": []}

    with pytest.raises(ConfigurationValidationError) as exc:
        service.validate_document(document)

    assert exc.value.details["limits.sampling_rate_min"].startswith("Sampling bounds")
    assert exc.value.details["limits.retention_days_min"] == "Minimum cannot exceed maximum."
    assert exc.value.details["defaults.alert_rule.notification_channels"] == "At least one channel is required."
    assert exc.value.details["query.automatic_buckets"] == "Must contain positive range and bucket pairs."
    assert exc.value.details["query.summary_percentiles"] == "Exactly three percentiles between 0 and 100 are required."
    assert exc.value.details["rollout"] == "Full rollout cannot also declare role or cohort targeting."

    with pytest.raises(ConfigurationValidationError) as missing:
        service.setting(tenant, "does.not.exist")
    assert missing.value.details == {"path": "does.not.exist"}

    with pytest.raises(ConfigurationValidationError):
        service.apply(
            tenant,
            "bad environment!",
            service.default_document(),
            actor_id=actor,
            correlation_id="pm-invalid-env",
            change_reason="Invalid environment slug.",
            expected_version=0,
            merge=False,
        )

    with pytest.raises(ConfigurationValidationError):
        service.apply(
            tenant,
            "qa",
            service.default_document(),
            actor_id=actor,
            correlation_id="",
            change_reason="Invalid missing correlation.",
            expected_version=0,
            merge=False,
        )

    current = service.ensure_current(tenant, "qa", actor_id=actor, correlation_id="pm-ensure")
    assert current.version == 1
    assert service.ensure_current(tenant, "qa", actor_id=actor, correlation_id="pm-ensure-replay").id == current.id

    with pytest.raises(NotFoundError):
        service.export(uuid.uuid4(), "qa")


@pytest.mark.django_db
def test_metric_collection_rejects_missing_relations_ranges_and_idempotency_conflicts():
    tenant = uuid.uuid4()
    service = MetricsCollectionService()

    with pytest.raises(NotFoundError, match="Source not found"):
        service.define_metric(tenant, "api.latency", MetricType.GAUGE, source_id=uuid.uuid4())

    point = service.record_metric(
        tenant,
        "api.duration",
        "10.5",
        tags={"route": "/orders"},
        idempotency_key="duration-1",
    )
    with pytest.raises(ConflictError):
        service.record_metric(
            tenant,
            "api.duration",
            "11.5",
            tags={"route": "/orders"},
            idempotency_key="duration-1",
        )

    with pytest.raises(InvalidMetricValueError):
        service.record_metric(tenant, "api.duration", "not-a-number")

    with pytest.raises(InvalidTimeRangeError):
        service.query_metrics(tenant, "api.duration", start=timezone.now(), end=timezone.now() - timedelta(seconds=1))

    with pytest.raises(InvalidTimeRangeError):
        service.query_metrics(
            tenant,
            "api.duration",
            start=timezone.now() - timedelta(minutes=1),
            end=timezone.now(),
            aggregation="unsupported",
        )

    result = service.query_metrics(
        tenant,
        "api.duration",
        {"start": point.timestamp - timedelta(seconds=1), "end": point.timestamp + timedelta(seconds=1)},
    )
    assert result.data[0].value == 10.5
