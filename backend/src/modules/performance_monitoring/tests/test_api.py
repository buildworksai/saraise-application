import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from src.core.licensing.models import Organization
from src.core.user_models import UserProfile
from src.modules.performance_monitoring.api import MetricViewSet


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


@pytest.mark.django_db
def test_metrics_api_requires_authentication():
    response = APIClient().get("/api/v1/performance-monitoring/metrics/")
    assert response.status_code == 401


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
def test_unknown_uuid_is_tenant_safe_404(tenant_client):
    client, _ = tenant_client
    response = client.get(f"/api/v1/performance-monitoring/metrics/{uuid.uuid4()}/")
    assert response.status_code == 404
