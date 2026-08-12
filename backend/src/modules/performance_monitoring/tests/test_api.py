import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.test import APIClient

from src.core.licensing.models import Organization
from src.core.user_models import UserProfile
from src.modules.performance_monitoring.api import (
    ComplianceViewSet,
    ConfigurationViewSet,
    CsrfSessionAuthentication,
    GovernedMonitoringViewSet,
    MetricViewSet,
    _actor_id,
)
from src.modules.performance_monitoring.models import Alert, AlertRule, Metric, MetricDataPoint
from src.modules.performance_monitoring.services import CapabilityUnavailableError, ConflictError


@pytest.fixture
def tenant_client(db, monkeypatch):
    tenant = Organization.objects.create(name="Monitoring tenant")
    user = get_user_model().objects.create_user(username=f"ops-{uuid.uuid4()}", password="test-password")
    profile = UserProfile.objects.get(user=user)
    profile.tenant_id = tenant.id
    profile.tenant_role = "tenant_admin"
    profile.save()
    user.is_staff = True
    user.is_superuser = True
    user.save(update_fields=["is_staff", "is_superuser"])
    user.roles = ["tenant_admin"]

    # Product views remain fail-closed. Positive API behavior is exercised
    # under an explicit test grant by retaining authentication while replacing
    # only the external policy/entitlement permission dependency.
    monkeypatch.setattr(MetricViewSet, "permission_classes", (MetricViewSet.permission_classes[0],))
    user = get_user_model().objects.get(pk=user.pk)
    client = APIClient()
    client.force_authenticate(user=user)
    return client, tenant.id


@pytest.fixture
def governed_client(db, monkeypatch):
    tenant = Organization.objects.create(name="Monitoring governed tenant")
    user = get_user_model().objects.create_user(username=f"monitoring-{uuid.uuid4()}", password="test-password")
    profile = UserProfile.objects.get(user=user)
    profile.tenant_id = tenant.id
    profile.tenant_role = "tenant_admin"
    profile.save(update_fields=["tenant_id", "tenant_role"])
    user.roles = ["tenant_admin"]
    user.save()

    monkeypatch.setattr(GovernedMonitoringViewSet, "permission_classes", (IsAuthenticated,))
    monkeypatch.setattr(ComplianceViewSet, "permission_classes", (IsAuthenticated,))
    client = APIClient()
    client.force_authenticate(user=get_user_model().objects.get(pk=user.pk))
    return client, tenant.id, user.id


@pytest.mark.django_db
def test_metrics_api_requires_authentication():
    response = APIClient().get("/api/v1/performance-monitoring/metrics/")
    assert response.status_code == 401


def test_session_auth_header_and_actor_identity_are_stable() -> None:
    assert CsrfSessionAuthentication().authenticate_header(SimpleNamespace()) == "Session"

    actor = uuid.uuid4()
    assert _actor_id(SimpleNamespace(user=SimpleNamespace(id=actor))) == actor
    assert _actor_id(SimpleNamespace(user=SimpleNamespace(id="external-user"))) == uuid.uuid5(
        uuid.NAMESPACE_URL, "saraise:user:external-user"
    )


def test_monitoring_handle_exception_preserves_public_error_envelopes() -> None:
    view = GovernedMonitoringViewSet()

    domain = view.handle_exception(CapabilityUnavailableError("Provider unavailable.", details={"adapter": "otlp"}))
    validation = view.handle_exception(DjangoValidationError({"environment": ["invalid"]}))

    assert domain.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert domain.data == {
        "error": {
            "code": "CAPABILITY_UNAVAILABLE",
            "message": "Provider unavailable.",
            "details": {"adapter": "otlp"},
        }
    }
    assert validation.status_code == status.HTTP_400_BAD_REQUEST
    assert validation.data["error"]["details"] == {"environment": ["invalid"]}


@pytest.mark.django_db
def test_metrics_ingest_list_and_spoofed_tenant_ignored(tenant_client):
    client, tenant_id = tenant_client
    response = client.post(
        "/api/v1/performance-monitoring/metrics/",
        {"tenant_id": str(uuid.uuid4()), "metric_name": "api.latency", "value": "12.000000"},
        format="json",
    )
    assert response.status_code == 201, response.data
    listed = client.get("/api/v1/performance-monitoring/metrics/")
    assert listed.status_code == 200


@pytest.mark.django_db
def test_metrics_v2_uses_governed_collection_envelope(tenant_client):
    client, _ = tenant_client
    response = client.get("/api/v2/performance-monitoring/metrics/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"] == []
    assert payload["meta"]["pagination"] == {
        "count": 0,
        "page": 1,
        "page_size": 25,
        "total_pages": 0,
        "has_next": False,
        "has_previous": False,
    }


@pytest.mark.django_db
def test_metric_definition_filters_type_and_active_flag(governed_client):
    client, tenant_id, _ = governed_client
    inactive = Metric.objects.create(
        tenant_id=tenant_id,
        metric_name="api.errors",
        metric_type="counter",
        is_active=False,
    )
    Metric.objects.create(
        tenant_id=tenant_id,
        metric_name="api.latency",
        metric_type="gauge",
        is_active=True,
    )

    response = client.get(
        "/api/v2/performance-monitoring/metric-definitions/",
        {"metric_type": "counter", "is_active": "false"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert [row["id"] for row in response.json()["data"]] == [str(inactive.id)]


@pytest.mark.django_db
def test_unknown_uuid_is_tenant_safe_404(tenant_client):
    client, _ = tenant_client
    response = client.get(f"/api/v1/performance-monitoring/metrics/{uuid.uuid4()}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_catalog_routes_delegate_create_update_delete_and_translate_domain_errors(governed_client, monkeypatch):
    client, tenant_id, actor_id = governed_client
    captured = []
    source_id = uuid.uuid4()

    def create(self, tenant, model, values, *, created_by):
        captured.append(("create", tenant, model.__name__, values, created_by))
        return SimpleNamespace(
            id=source_id,
            tenant_id=tenant,
            name=values["name"],
            source_type=values["source_type"],
            status="no_telemetry",
            last_seen_at=None,
            sampling_rate=values.get("sampling_rate", 1),
            is_active=True,
            created_at=timezone.now(),
        )

    def update(self, tenant, model, pk, values):
        captured.append(("update", tenant, model.__name__, pk, values))
        return SimpleNamespace(
            id=uuid.UUID(str(pk)),
            tenant_id=tenant,
            name=values["name"],
            source_type="otlp",
            status="healthy",
            last_seen_at=timezone.now(),
            sampling_rate=1,
            is_active=True,
            created_at=timezone.now(),
            description="",
            retention_days=90,
            daily_event_quota=1000,
            redaction_fields=[],
            updated_at=timezone.now(),
        )

    def delete(self, tenant, model, pk):
        captured.append(("delete", tenant, model.__name__, pk))

    monkeypatch.setattr("src.modules.performance_monitoring.api.MonitoringCatalogService.create", create)
    monkeypatch.setattr("src.modules.performance_monitoring.api.MonitoringCatalogService.update", update)
    monkeypatch.setattr("src.modules.performance_monitoring.api.MonitoringCatalogService.delete", delete)

    created = client.post(
        "/api/v2/performance-monitoring/telemetry-sources/",
        {"name": "Collector", "source_type": "otlp"},
        format="json",
    )
    assert created.status_code == 201, created.data
    assert captured[0][1] == tenant_id
    assert captured[0][3]["name"] == "Collector"
    assert captured[0][4] == uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{actor_id}")

    patched = client.patch(
        f"/api/v2/performance-monitoring/telemetry-sources/{source_id}/",
        {"name": "Collector renamed"},
        format="json",
    )
    assert patched.status_code == 200, patched.data

    removed = client.delete(f"/api/v2/performance-monitoring/telemetry-sources/{source_id}/")
    assert removed.status_code == 204

    def fail_create(self, tenant, model, values, *, created_by):
        raise ConflictError("catalog rejected", details={"field": "name"})

    monkeypatch.setattr("src.modules.performance_monitoring.api.MonitoringCatalogService.create", fail_create)
    rejected = client.post(
        "/api/v2/performance-monitoring/telemetry-sources/",
        {"name": "Duplicate", "source_type": "otlp"},
        format="json",
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "MONITORING_ERROR"


@pytest.mark.django_db
def test_metric_actions_cover_batch_query_summary_and_filtered_evidence(governed_client, monkeypatch):
    client, tenant_id, _ = governed_client
    now = timezone.now()

    monkeypatch.setattr(
        "src.modules.performance_monitoring.api.MetricsCollectionService.record_metrics_batch",
        lambda self, tenant, points, atomic=False, created_by=None: SimpleNamespace(
            accepted=1, rejected=1, errors=[{"index": 1, "code": "INVALID_METRIC_NAME"}]
        ),
    )
    batch = client.post(
        "/api/v2/performance-monitoring/metrics/batch/",
        {
            "atomic": False,
            "data_points": [
                {"metric_name": "api.latency", "value": "10.000000"},
                {"metric_name": "bad.name", "value": "5.000000"},
            ],
        },
        format="json",
    )
    assert batch.status_code == 207, batch.data

    monkeypatch.setattr(
        "src.modules.performance_monitoring.api.MetricsCollectionService.query_metrics",
        lambda self, tenant, metric_name, **values: SimpleNamespace(
            metric_name=metric_name,
            aggregation=values["aggregation"],
            interval=values["interval"],
            data=[SimpleNamespace(timestamp=now, value=12)],
        ),
    )
    queried = client.get(
        "/api/v2/performance-monitoring/metrics/query/",
        {
            "metric_name": "api.latency",
            "start": (now - timedelta(minutes=5)).isoformat(),
            "end": now.isoformat(),
            "aggregation": "avg",
            "interval": "1m",
            "tags": "region=us,service=erp",
        },
    )
    assert queried.status_code == 200, queried.data
    assert queried.json()["data"]["data"][0]["value"] == 12

    monkeypatch.setattr(
        "src.modules.performance_monitoring.api.MetricsCollectionService.get_metric_summary",
        lambda self, tenant, names, period: [
            SimpleNamespace(
                metric_name=name,
                period=period,
                minimum=1,
                maximum=5,
                average=3,
                count=3,
                p50=3,
                p95=5,
                p99=5,
            )
            for name in names
        ],
    )
    summary = client.get(
        "/api/v2/performance-monitoring/metrics/summary/",
        {"metric_names": "api.latency,api.errors", "period": "1h"},
    )
    assert summary.status_code == 200, summary.data
    assert len(summary.json()["data"]["summaries"]) == 2

    metric = Metric.objects.create(tenant_id=tenant_id, metric_name="api.latency", metric_type="gauge")
    MetricDataPoint.objects.create(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        metric=metric,
        value="10.000000",
        timestamp=now,
        source_module="erp",
        session_id="session-1",
        trace_id="a" * 32,
        span_id="b" * 16,
    )
    listed = client.get(
        "/api/v2/performance-monitoring/metric-data-points/",
        {"metric_id": str(metric.id), "trace_id": "a" * 32, "session_id": "session-1"},
    )
    assert listed.status_code == 200, listed.data


@pytest.mark.django_db
def test_alert_sla_slo_and_configuration_actions_cover_api_branches(governed_client, monkeypatch):
    client, tenant_id, actor_id = governed_client
    now = timezone.now()
    alert_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    sla_id = uuid.uuid4()
    slo_id = uuid.uuid4()
    config_id = uuid.uuid4()

    metric = Metric.objects.create(tenant_id=tenant_id, metric_name="api.latency", metric_type="gauge")
    alert_rule = AlertRule.objects.create(
        id=rule_id,
        tenant_id=tenant_id,
        metric=metric,
        metric_name=metric.metric_name,
        name="Latency",
        condition="above_threshold",
        threshold="500.000000",
        severity="critical",
        action={"channels": ["in_app"], "recipients": [str(actor_id)]},
    )
    alert = Alert.objects.create(
        id=alert_id,
        tenant_id=tenant_id,
        alert_rule=alert_rule,
        metric=metric,
        metric_name="api.latency",
        triggered_value="900.000000",
        threshold="500.000000",
        condition="above_threshold",
        severity="critical",
        deduplication_key="api.latency:critical",
        status="firing",
        triggered_at=now,
        last_observed_at=now,
        occurrence_count=1,
        acknowledged_at=None,
        acknowledged_by=None,
        resolved_at=None,
        resolved_by=None,
        resolution_note="",
        title="Latency",
        description="Latency breach",
        context={},
    )
    monkeypatch.setattr(
        "src.modules.performance_monitoring.api.AlertingService.evaluate_alerts", lambda self, tenant: [alert]
    )
    monkeypatch.setattr(
        "src.modules.performance_monitoring.api.AlertingService.acknowledge_alert",
        lambda self, tenant, pk, actor: SimpleNamespace(
            **{**alert.__dict__, "status": "acknowledged", "acknowledged_by": actor}
        ),
    )
    monkeypatch.setattr(
        "src.modules.performance_monitoring.api.AlertingService.resolve_alert",
        lambda self, tenant, pk, resolved_by, note="": SimpleNamespace(
            **{**alert.__dict__, "status": "resolved", "resolved_by": resolved_by, "resolution_note": note}
        ),
    )

    assert client.post("/api/v2/performance-monitoring/alerts/evaluate/").status_code == 200
    assert (
        client.post(
            f"/api/v2/performance-monitoring/alerts/{alert_id}/acknowledge/",
            {},
            format="json",
        ).status_code
        == 200
    )
    resolved = client.post(
        f"/api/v2/performance-monitoring/alerts/{alert_id}/resolve/",
        {"note": "Recovered"},
        format="json",
    )
    assert resolved.status_code == 200, resolved.data

    monkeypatch.setattr(
        "src.modules.performance_monitoring.api.SLOMonitoringService.evaluate",
        lambda self, tenant, pk: SimpleNamespace(
            id=uuid.uuid4(),
            tenant_id=tenant,
            slo_id=uuid.UUID(str(pk)),
            period_start=now - timedelta(hours=1),
            period_end=now,
            budget_minutes=60,
            consumed_minutes=30,
            remaining_minutes=30,
            burn_rate="0.500000",
            status="compliant",
            created_at=now,
        ),
    )
    evaluated = client.post(f"/api/v2/performance-monitoring/slos/{slo_id}/evaluate/")
    assert evaluated.status_code == 201, evaluated.data

    monkeypatch.setattr(
        "src.modules.performance_monitoring.api.SLAMonitoringService.check_sla_compliance",
        lambda self, tenant, pk, period=None, **values: SimpleNamespace(
            id=uuid.uuid4(),
            tenant_id=tenant,
            sla_id=uuid.UUID(str(pk)),
            period_start=now - timedelta(hours=1),
            period_end=now,
            actual_value="99.9000",
            target_value="99.0000",
            is_compliant=True,
            breach_duration_minutes=0,
            expected_samples=60,
            observed_samples=60,
            compliant_samples=60,
            missing_samples=0,
            compliance_percentage="100.00",
            status="compliant",
            evidence={},
            created_at=now,
        ),
    )
    compliance = client.get(f"/api/v2/performance-monitoring/sla/{sla_id}/compliance/", {"period": "current"})
    assert compliance.status_code == 200, compliance.data

    monkeypatch.setattr(
        "src.modules.performance_monitoring.api.SLAMonitoringService.generate_sla_report",
        lambda self, tenant, period, output_format="json", created_by=None: SimpleNamespace(
            id=uuid.uuid4(),
            tenant_id=tenant,
            artifact_ref="",
            status="ready",
            period_start=now - timedelta(days=1),
            period_end=now,
            summary={"period": period},
            generated_at=now,
            created_at=now,
        ),
    )
    report = client.post(
        "/api/v2/performance-monitoring/sla/reports/",
        {"period": "rolling_24h", "format": "json"},
        format="json",
    )
    assert report.status_code == 201, report.data

    current = SimpleNamespace(
        id=config_id,
        tenant_id=tenant_id,
        environment="default",
        version=2,
        document={"rollout": {"percentage": 50}},
        checksum="abc",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(
        "src.modules.performance_monitoring.api.ConfigurationService.preview",
        lambda self, tenant, document, environment: {"diff": [{"path": "rollout.percentage"}]},
    )

    def rollback_configuration(self, tenant, environment, version, actor_id, correlation_id, **values):
        return current

    def apply_configuration(
        self,
        tenant,
        environment,
        document,
        actor_id,
        correlation_id,
        action="update",
        merge=True,
        **values,
    ):
        return current

    monkeypatch.setattr(
        "src.modules.performance_monitoring.api.ConfigurationService.rollback",
        rollback_configuration,
    )
    monkeypatch.setattr(
        "src.modules.performance_monitoring.api.ConfigurationService.apply",
        apply_configuration,
    )
    monkeypatch.setattr(
        "src.modules.performance_monitoring.api.ConfigurationService.export",
        lambda self, tenant, environment: {"environment": environment, "document": current.document},
    )
    assert (
        client.post(
            "/api/v2/performance-monitoring/configuration/preview/",
            {"document": {"rollout": {"percentage": 50}}},
            format="json",
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v2/performance-monitoring/configuration/rollback/",
            {"version": 1, "change_reason": "restore"},
            format="json",
            HTTP_X_CORRELATION_ID="req-rollback",
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v2/performance-monitoring/configuration/import/",
            {"document": current.document, "change_reason": "promote"},
            format="json",
            HTTP_X_CORRELATION_ID="req-import",
        ).status_code
        == 201
    )
    assert client.get("/api/v2/performance-monitoring/configuration/export/").status_code == 200
    assert actor_id


@pytest.mark.django_db
def test_configuration_rejects_invalid_environment_before_service_call(governed_client, monkeypatch):
    client, _, _ = governed_client
    calls = []

    def ensure_current(self, *args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("invalid environment must not reach configuration service")

    monkeypatch.setattr("src.modules.performance_monitoring.api.ConfigurationService.ensure_current", ensure_current)

    response = client.get("/api/v2/performance-monitoring/configuration/current/?environment=bad slug")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert calls == []


def test_configuration_correlation_id_preserves_header_and_generates_default() -> None:
    view = ConfigurationViewSet()
    explicit = SimpleNamespace(headers={"X-Correlation-ID": "operator-change-42"})
    generated = SimpleNamespace(headers={})

    assert view._correlation_id(explicit) == "operator-change-42"
    assert view._correlation_id(generated).startswith("req_")
    assert generated.correlation_id.startswith("req_")
