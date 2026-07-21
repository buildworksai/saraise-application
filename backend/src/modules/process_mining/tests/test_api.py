"""Governed v2 routing, envelope, serializer, and service delegation tests."""
import uuid
from unittest.mock import patch

import pytest
from rest_framework.permissions import IsAuthenticated

from .. import api
from ..serializers import EventBatchIngestSerializer, ProcessModelCreateSerializer, TransitionActionSerializer
from ..services import IngestResult
from .factories import EventFactory, ModelFactory, graph

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db
BASE = "/api/v2/process-mining"


@pytest.fixture(autouse=True)
def authenticated_policy_boundary(monkeypatch):
    monkeypatch.setattr(api.ActionAccessMixin, "get_permissions", lambda self: [IsAuthenticated()])


def test_anonymous_requests_are_401(api_client):
    assert api_client.get(f"{BASE}/models/").status_code == 401


def test_model_list_is_paginated_governed_envelope(authenticated_tenant_a_client, tenant_a):
    ModelFactory(tenant_id=tenant_a.id)
    response = authenticated_tenant_a_client.get(f"{BASE}/models/")
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 1 and body["meta"]["pagination"]["page_size"] == 25
    assert body["meta"]["correlation_id"]


def test_event_ingestion_delegates_to_service(authenticated_tenant_a_client):
    payload = {"process_name": "orders", "source_module": "canonical", "events": [{"case_id": "c", "activity": "a", "occurred_at": "2026-07-21T08:00:00Z"}]}
    with patch.object(api.EventLogService, "ingest_events", return_value=IngestResult(1, 0, 0, ())) as method:
        response = authenticated_tenant_a_client.post(f"{BASE}/events/", payload, format="json")
    assert response.status_code == 201 and response.json()["data"]["accepted"] == 1
    method.assert_called_once()


@pytest.mark.parametrize("serializer,payload", [(EventBatchIngestSerializer, {"process_name": "p", "source_module": "canonical", "events": [{"case_id": "c", "activity": "a", "occurred_at": "2026-07-21T08:00:00Z"}]}), (ProcessModelCreateSerializer, {"name": "m", "process_name": "p", "description": "", "model_data": graph()}), (TransitionActionSerializer, {"transition_key": "key"})])
def test_mutation_serializers_reject_tenant_spoofing(serializer, payload):
    value = serializer(data={**payload, "tenant_id": str(uuid.uuid4())})
    assert not value.is_valid() and "tenant_id" in value.errors


def test_unknown_ordering_returns_validation_envelope(authenticated_tenant_a_client):
    response = authenticated_tenant_a_client.get(f"{BASE}/exports/?ordering=artifact_key")
    assert response.status_code == 400 and response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_append_only_event_methods_are_not_routed(authenticated_tenant_a_client, tenant_a):
    event = EventFactory(tenant_id=tenant_a.id)
    assert authenticated_tenant_a_client.patch(f"{BASE}/events/{event.id}/", {}, format="json").status_code == 405
    assert authenticated_tenant_a_client.delete(f"{BASE}/events/{event.id}/").status_code == 405
