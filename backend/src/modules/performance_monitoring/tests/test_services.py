import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.modules.performance_monitoring.models import (
    AlertState,
    MetricDataPoint,
    MetricType,
    MonitoredService,
    MonitoringEnvironment,
    SourceType,
    TelemetrySource,
)
from src.modules.performance_monitoring.services import (
    AlertingService,
    ConflictError,
    InvalidMetricValueError,
    MetricsCollectionService,
    SLAMonitoringService,
    TelemetryService,
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

    first = service.ingest_log(tenant, payload)
    assert service.ingest_log(tenant, payload).id == first.id

    with pytest.raises(ConflictError):
        service.ingest_log(tenant, {**payload, "message": "different event"})


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
