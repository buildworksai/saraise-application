"""Cross-tenant list, detail, mutation, action, worker, and evidence isolation."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated

from .. import api
from ..models import ProcessModel
from ..tasks import discover_process_task
from .factories import AnalysisFactory, ConformanceFactory, DiscoveryFactory, EventFactory, ExportFactory, ModelFactory, graph

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db
BASE = "/api/v2/process-mining"


@pytest.fixture(autouse=True)
def authenticated_policy_boundary(monkeypatch):
    monkeypatch.setattr(api.ActionAccessMixin, "get_permissions", lambda self: [IsAuthenticated()])


@pytest.mark.parametrize("factory,path", [(ExportFactory, "exports"), (DiscoveryFactory, "discoveries"), (ModelFactory, "models"), (ConformanceFactory, "conformance-checks"), (AnalysisFactory, "bottleneck-analyses")])
def test_list_and_detail_hide_other_tenant(authenticated_tenant_a_client, tenant_a, tenant_b, factory, path):
    own = factory(tenant_id=tenant_a.id)
    other = factory(tenant_id=tenant_b.id)
    listed = authenticated_tenant_a_client.get(f"{BASE}/{path}/").json()["data"]
    assert {row["id"] for row in listed} == {str(own.id)}
    assert authenticated_tenant_a_client.get(f"{BASE}/{path}/{other.id}/").status_code == 404


def test_event_list_and_detail_hide_other_tenant(authenticated_tenant_a_client, tenant_a, tenant_b):
    start, end = timezone.now() - timedelta(days=1), timezone.now() + timedelta(minutes=1)
    own = EventFactory(tenant_id=tenant_a.id, process_name="orders", occurred_at=timezone.now())
    other = EventFactory(tenant_id=tenant_b.id, process_name="orders", occurred_at=timezone.now())
    response = authenticated_tenant_a_client.get(f"{BASE}/events/", {"process_name": "orders", "start": start.isoformat(), "end": end.isoformat()})
    assert {row["id"] for row in response.json()["data"]} == {str(own.id)}
    assert authenticated_tenant_a_client.get(f"{BASE}/events/{other.id}/").status_code == 404


def test_create_payload_cannot_spoof_tenant(authenticated_tenant_a_client, tenant_a, tenant_b):
    response = authenticated_tenant_a_client.post(f"{BASE}/models/", {"tenant_id": str(tenant_b.id), "name": "Reference", "process_name": "orders", "description": "", "model_data": graph()}, format="json")
    assert response.status_code == 400
    assert not ProcessModel.objects.for_tenant(tenant_b.id).filter(name="Reference").exists()
    response = authenticated_tenant_a_client.post(f"{BASE}/models/", {"name": "Reference", "process_name": "orders", "description": "", "model_data": graph()}, format="json")
    assert response.status_code == 201
    assert ProcessModel.objects.for_tenant(tenant_a.id).filter(pk=response.json()["data"]["id"]).exists()


def test_cross_tenant_update_delete_and_actions_are_404(authenticated_tenant_a_client, tenant_b):
    model = ModelFactory(tenant_id=tenant_b.id)
    export = ExportFactory(tenant_id=tenant_b.id)
    assert authenticated_tenant_a_client.patch(f"{BASE}/models/{model.id}/", {"name": "stolen"}, format="json").status_code == 404
    assert authenticated_tenant_a_client.delete(f"{BASE}/models/{model.id}/").status_code == 404
    assert authenticated_tenant_a_client.post(f"{BASE}/models/{model.id}/set-reference/", {"version_id": model.id, "transition_key": "x"}, format="json").status_code == 404
    assert authenticated_tenant_a_client.post(f"{BASE}/exports/{export.id}/cancel/", {"transition_key": "x"}, format="json").status_code == 404
    model.refresh_from_db(); export.refresh_from_db()
    assert model.name != "stolen" and not model.is_deleted and not export.is_deleted


def test_worker_without_tenant_fails_closed():
    with pytest.raises(Exception, match="requires tenant_id"):
        discover_process_task(discovery_id=DiscoveryFactory().id, async_job_id=DiscoveryFactory().id)
