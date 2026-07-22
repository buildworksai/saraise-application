"""Black-box v2 API contract tests.

Only the access-decision result is isolated in successful-path tests; identity,
session authentication, CSRF, tenant middleware, querysets, serializers and
the governed response envelope remain real.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from django.urls import resolve
from rest_framework import status, viewsets

from src.core.access.permissions import RequiresAccess
from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination
from src.modules.ai_agent_management import api
from src.modules.ai_agent_management import serializers as module_serializers
from src.modules.ai_agent_management.models import Agent
from src.modules.ai_agent_management.urls import router

BASE = "/api/v2/ai-agent-management/"

EXPECTED_ROUTES = {
    "agents",
    "executions",
    "schedules",
    "approvals",
    "sod-policies",
    "sod-violations",
    "tools",
    "tool-invocations",
    "egress-rules",
    "egress-requests",
    "secrets",
    "secret-accesses",
    "quotas",
    "quota-usage",
    "saturation",
    "kill-switches",
    "token-usage",
    "cost-records",
    "cost-summaries",
    "audit-events",
    "audit-trails",
    "jobs",
}


def _viewsets():
    return [viewset for _prefix, viewset, _basename in router.registry]


def _items(response):
    payload = response.json()
    assert set(payload) == {"data", "meta"}
    assert "correlation_id" in payload["meta"]
    assert "timestamp" in payload["meta"]
    data = payload["data"]
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


def test_router_exposes_the_complete_v2_resource_surface():
    assert {prefix for prefix, _viewset, _basename in router.registry} == EXPECTED_ROUTES
    assert resolve(f"{BASE}health/").url_name in {"ai-agent-management-health", "health_check", "health"}


@pytest.mark.parametrize("viewset", _viewsets())
def test_every_viewset_is_governed_paginated_and_deny_by_default(viewset):
    assert issubclass(viewset, GovernedAPIViewMixin)
    assert issubclass(viewset, viewsets.GenericViewSet)
    assert viewset.pagination_class is GovernedPageNumberPagination
    assert RequiresAccess in viewset.permission_classes or any(
        isinstance(permission, RequiresAccess) for permission in viewset.permission_classes
    )
    assert viewset.permission_map
    assert all(isinstance(permission, str) and permission for permission in viewset.permission_map.values())
    assert isinstance(viewset.required_entitlement, str) and viewset.required_entitlement
    assert isinstance(viewset.quota_resource, str) and viewset.quota_resource
    assert isinstance(viewset.quota_cost, int) and viewset.quota_cost > 0


@pytest.mark.parametrize(
    ("viewset_name", "actions"),
    (
        ("AgentViewSet", {"activate", "disable", "retire", "execute", "evaluate"}),
        ("AgentExecutionViewSet", {"pause", "resume", "terminate"}),
        ("AgentSchedulerTaskViewSet", {"cancel"}),
        ("ApprovalRequestViewSet", {"approve", "reject", "cancel"}),
        ("ToolViewSet", {"validate"}),
        ("SecretViewSet", {"rotate", "deactivate"}),
        ("KillSwitchViewSet", {"deactivate"}),
        ("CostSummaryViewSet", {"recalculate"}),
    ),
)
def test_required_custom_actions_are_routed(viewset_name, actions):
    viewset = getattr(api, viewset_name)
    routed = {
        name
        for name in dir(viewset)
        if getattr(getattr(viewset, name, None), "mapping", None) is not None
    }
    assert actions <= routed


@pytest.mark.parametrize(
    "viewset_name",
    (
        "AgentExecutionViewSet",
        "SoDViolationViewSet",
        "ToolInvocationViewSet",
        "EgressRequestViewSet",
        "SecretAccessViewSet",
        "QuotaViewSet",
        "QuotaUsageViewSet",
        "ShardSaturationViewSet",
        "TokenUsageViewSet",
        "CostRecordViewSet",
        "AuditEventViewSet",
        "AuditTrailViewSet",
        "AsyncJobViewSet",
    ),
)
def test_evidence_viewsets_have_no_generic_mutation_routes(viewset_name):
    viewset = getattr(api, viewset_name)
    assert not issubclass(viewset, viewsets.ModelViewSet)
    assert not {"create", "update", "partial_update", "destroy"} & set(viewset.__dict__)


@pytest.mark.django_db
@pytest.mark.parametrize("resource", sorted(EXPECTED_ROUTES))
def test_every_resource_rejects_anonymous_access(api_client, resource):
    response = api_client.get(f"{BASE}{resource}/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    payload = response.json()
    assert set(payload) == {"error"}
    assert payload["error"]["code"]
    assert payload["error"]["correlation_id"]


@pytest.fixture
def allow_access(monkeypatch):
    monkeypatch.setattr(RequiresAccess, "has_permission", lambda self, request, view: True)
    monkeypatch.setattr(RequiresAccess, "has_object_permission", lambda self, request, view, obj: True)


@pytest.mark.django_db
def test_agent_list_uses_envelope_pagination_filters_and_deterministic_order(
    authenticated_tenant_a_client,
    tenant_a,
    tenant_b,
    allow_access,
):
    actor = uuid4()
    own = Agent.objects.create(
        tenant_id=tenant_a.id,
        name="Alpha governed agent",
        identity_type="system_bound",
        subject_id=uuid4(),
        runner_key="runner.alpha",
        created_by=actor,
    )
    Agent.objects.create(
        tenant_id=tenant_a.id,
        name="Zulu hidden by search",
        identity_type="system_bound",
        subject_id=uuid4(),
        runner_key="runner.beta",
        created_by=actor,
    )
    foreign = Agent.objects.create(
        tenant_id=tenant_b.id,
        name="Alpha foreign agent",
        identity_type="system_bound",
        subject_id=uuid4(),
        runner_key="runner.alpha",
        created_by=actor,
    )

    response = authenticated_tenant_a_client.get(
        f"{BASE}agents/",
        {"search": "Alpha", "runner_key": "runner.alpha", "ordering": "name", "page_size": 1},
    )
    assert response.status_code == status.HTTP_200_OK
    items = _items(response)
    assert [item["id"] for item in items] == [str(own.id)]
    assert str(foreign.id) not in {item["id"] for item in items}
    assert response.json()["meta"]["pagination"]["page_size"] == 1


@pytest.mark.django_db
def test_cross_tenant_detail_is_hidden_with_governed_404(
    authenticated_tenant_a_client,
    tenant_b,
    allow_access,
):
    foreign = Agent.objects.create(
        tenant_id=tenant_b.id,
        name="Foreign",
        identity_type="system_bound",
        subject_id=uuid4(),
        runner_key="runner.foreign",
        created_by=uuid4(),
    )
    response = authenticated_tenant_a_client.get(f"{BASE}agents/{foreign.id}/")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    payload = response.json()
    assert set(payload) == {"error"}
    assert payload["error"]["code"]


def test_secret_serializers_never_declare_cryptographic_storage_fields():
    serializers = [
        value
        for name, value in vars(module_serializers).items()
        if isinstance(value, type) and name.startswith("Secret") and name.endswith("Serializer")
    ]
    assert serializers
    forbidden = {"plaintext", "ciphertext", "wrapped_data_key", "key_id", "encrypted_value", "encryption_key_id"}
    for serializer_class in serializers:
        instance = serializer_class()
        if "Create" in serializer_class.__name__ or "Rotate" in serializer_class.__name__:
            forbidden_for_action = forbidden - {"plaintext"}
        else:
            forbidden_for_action = forbidden
        assert not forbidden_for_action & set(instance.fields)


def test_audit_and_execution_serializers_do_not_expose_opaque_payloads():
    forbidden = {
        "task_definition",
        "tool_input",
        "input_data",
        "output_data",
        "authorization",
        "provider_body",
        "prompt",
        "completion",
    }
    for name, serializer_class in vars(module_serializers).items():
        if not isinstance(serializer_class, type) or not name.endswith("Serializer"):
            continue
        if not any(token in name for token in ("Audit", "Execution", "ToolInvocation", "ApprovalRequest")):
            continue
        assert not forbidden & set(serializer_class().fields), name
