import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated
from rest_framework.test import APIClient

from src.core.licensing.models import Organization
from src.core.user_models import UserProfile
from src.modules.performance_monitoring.api import AlertRuleViewSet
from src.modules.performance_monitoring.models import AlertRule, MetricType
from src.modules.performance_monitoring.services import AlertingService, MetricNotFoundError, MetricsCollectionService


def _tenant_client(tenant: Organization) -> APIClient:
    user = get_user_model().objects.create_user(
        username=f"monitoring-isolation-{uuid.uuid4()}",
        password="test-password",
    )
    profile = UserProfile.objects.get(user=user)
    profile.tenant_id = tenant.id
    profile.tenant_role = "tenant_admin"
    profile.save(update_fields=["tenant_id", "tenant_role"])
    user = get_user_model().objects.get(pk=user.pk)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_metric_list_detail_and_mutation_are_tenant_isolated():
    first, second = uuid.uuid4(), uuid.uuid4()
    service = MetricsCollectionService()
    service.record_metric(first, "shared.metric", 10)
    service.record_metric(second, "shared.metric", 20)
    assert service.get_metric_summary(first, ["shared.metric"], "1h")[0].average == 10
    assert service.get_metric_summary(second, ["shared.metric"], "1h")[0].average == 20
    with pytest.raises(MetricNotFoundError):
        service.get_metric_summary(uuid.uuid4(), ["shared.metric"], "1h")


@pytest.mark.django_db
def test_case_insensitive_definition_is_tenant_local():
    tenant = uuid.uuid4()
    service = MetricsCollectionService()
    first = service.define_metric(tenant, "api.requests", MetricType.GAUGE)
    second = service.define_metric(tenant, "API.REQUESTS", MetricType.GAUGE)
    assert first.id == second.id


@pytest.mark.django_db
def test_cross_tenant_list_detail_create_update_delete_are_isolated(monkeypatch):
    """Exercise the hostile two-tenant CRUD matrix through the public API."""

    first_tenant = Organization.objects.create(name="Monitoring isolation A")
    second_tenant = Organization.objects.create(name="Monitoring isolation B")
    first_client = _tenant_client(first_tenant)
    second_client = _tenant_client(second_tenant)
    monkeypatch.setattr(AlertRuleViewSet, "permission_classes", (IsAuthenticated,))

    metrics = MetricsCollectionService()
    alerts = AlertingService(notification_sender=lambda *_args: "test-delivery")
    metrics.define_metric(first_tenant.id, "api.latency", MetricType.GAUGE)
    metrics.define_metric(second_tenant.id, "api.latency", MetricType.GAUGE)
    second_rule = alerts.create_alert_rule(
        second_tenant.id,
        "api.latency",
        "above",
        500,
        {"channels": ["in_app"], "recipients": ["ops"]},
        name="Tenant B latency",
    )

    created = first_client.post(
        "/api/v1/performance-monitoring/alerts/rules/",
        {
            "tenant_id": str(second_tenant.id),
            "name": "Tenant A latency",
            "metric_name": "api.latency",
            "condition": "above",
            "threshold": "250.000000",
            "action": {"channels": ["in_app"], "recipients": ["ops"]},
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    first_rule_id = created.data["id"]
    assert AlertRule.objects.get(id=first_rule_id).tenant_id == first_tenant.id

    first_list = first_client.get("/api/v1/performance-monitoring/alerts/rules/")
    second_list = second_client.get("/api/v1/performance-monitoring/alerts/rules/")
    assert first_list.status_code == second_list.status_code == 200
    assert {row["id"] for row in first_list.data["results"]} == {first_rule_id}
    assert {row["id"] for row in second_list.data["results"]} == {str(second_rule.id)}

    assert first_client.get(f"/api/v1/performance-monitoring/alerts/rules/{first_rule_id}/").status_code == 200
    assert first_client.get(f"/api/v1/performance-monitoring/alerts/rules/{second_rule.id}/").status_code == 404

    updated = first_client.patch(
        f"/api/v1/performance-monitoring/alerts/rules/{first_rule_id}/",
        {"name": "Tenant A latency updated"},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["name"] == "Tenant A latency updated"
    assert (
        first_client.patch(
            f"/api/v1/performance-monitoring/alerts/rules/{second_rule.id}/",
            {"name": "Cross-tenant overwrite"},
            format="json",
        ).status_code
        == 404
    )
    second_rule.refresh_from_db()
    assert second_rule.name == "Tenant B latency"

    assert first_client.delete(f"/api/v1/performance-monitoring/alerts/rules/{second_rule.id}/").status_code == 404
    assert first_client.delete(f"/api/v1/performance-monitoring/alerts/rules/{first_rule_id}/").status_code == 204
    assert AlertRule._base_manager.get(id=first_rule_id).is_deleted is True
    assert AlertRule.objects.for_tenant(second_tenant.id).filter(id=second_rule.id).exists()
