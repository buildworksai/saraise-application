"""Black-box v2 API contract tests.

Only the access-decision result is isolated in successful-path tests; identity,
session authentication, CSRF, tenant middleware, querysets, serializers and
the governed response envelope remain real.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.urls import resolve
from rest_framework import status, viewsets
from rest_framework.exceptions import NotAuthenticated, NotFound, PermissionDenied, ValidationError

from src.core.access.permissions import RequiresAccess
from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination
from src.modules.ai_agent_management import api
from src.modules.ai_agent_management import serializers as module_serializers
from src.modules.ai_agent_management.approval_models import ApprovalRequest
from src.modules.ai_agent_management.models import Agent
from src.modules.ai_agent_management.urls import router

BASE = "/api/v2/ai-agent-management/"

EXPECTED_ROUTES = {
    "agents",
    "executions",
    "configuration",
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
    routed = {name for name in dir(viewset) if getattr(getattr(viewset, name, None), "mapping", None) is not None}
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


def test_tenant_viewset_identity_helpers_fail_closed(monkeypatch):
    view = api.GovernedTenantViewSet()

    assert api._principal_id(SimpleNamespace(pk=7)) == api.uuid5(api.NAMESPACE_URL, "saraise:user:7")
    with pytest.raises(NotAuthenticated):
        api._principal_id(SimpleNamespace(pk=""))

    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: None)
    view.request = SimpleNamespace(user=SimpleNamespace(pk=7, is_authenticated=True))
    with pytest.raises(PermissionDenied):
        view.tenant_id()
    assert view.tenant_id_for_query() is None

    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: "not-a-uuid")
    with pytest.raises(PermissionDenied):
        view.tenant_id()
    assert view.tenant_id_for_query() is None

    view.request = SimpleNamespace(correlation_id="not-a-uuid")
    with pytest.raises(ValidationError):
        view.correlation_id()


@pytest.mark.django_db
def test_agent_custom_actions_parse_payloads_and_delegate_to_tenant_services(monkeypatch, agent, actor_id):
    view = api.AgentViewSet()
    view.get_object = lambda: agent
    view.tenant_id = lambda: agent.tenant_id
    view.actor_id = lambda: actor_id
    calls = []

    def disable(tenant, actor, agent_id, reason, transition_key):
        calls.append(("disable", tenant, actor, agent_id, reason, transition_key))
        agent.status = "disabled"
        return agent

    def retire(tenant, actor, agent_id, reason, transition_key):
        calls.append(("retire", tenant, actor, agent_id, reason, transition_key))
        agent.status = "retired"
        return agent

    monkeypatch.setattr(api.AgentService, "disable_agent", disable)
    monkeypatch.setattr(api.AgentService, "retire_agent", retire)

    disable_request = SimpleNamespace(data={"transition_key": "disable-1", "reason": "maintenance"})
    assert view.disable(disable_request, pk=agent.id).data["status"] == "disabled"

    retire_request = SimpleNamespace(data={"transition_key": "retire-1", "reason": "replacement"})
    assert view.retire(retire_request, pk=agent.id).data["status"] == "retired"

    assert calls == [
        ("disable", agent.tenant_id, actor_id, agent.id, "maintenance", "disable-1"),
        ("retire", agent.tenant_id, actor_id, agent.id, "replacement", "retire-1"),
    ]


@pytest.mark.django_db
def test_execution_transition_rejects_agent_mismatch_before_service_call(monkeypatch, execution, actor_id):
    view = api.AgentExecutionViewSet()
    view.get_object = lambda: execution
    view.tenant_id = lambda: execution.tenant_id
    view.actor_id = lambda: actor_id

    monkeypatch.setattr(api.ExecutionService, "pause", lambda *args: pytest.fail("must not delegate"))
    request = SimpleNamespace(data={"transition_key": "pause-1", "agent_id": uuid4()})

    with pytest.raises(NotFound):
        view.pause(request, pk=execution.id)


@pytest.mark.django_db
def test_approval_cancel_action_uses_request_permission_branch(monkeypatch, execution, tool, actor_id, approver_id):
    approval = ApprovalRequest.objects.create(
        tenant_id=execution.tenant_id,
        tool=tool,
        agent_execution=execution,
        requested_by=actor_id,
        requested_for=approver_id,
        tool_input={},
    )
    view = api.ApprovalRequestViewSet()
    view.get_object = lambda: approval
    view.tenant_id = lambda: execution.tenant_id
    view.actor_id = lambda: actor_id
    captured = {}

    def cancel(tenant, actor, approval_id, transition_key):
        captured.update(
            tenant=tenant,
            actor=actor,
            approval_id=approval_id,
            transition_key=transition_key,
        )
        approval.status = "cancelled"
        return approval

    monkeypatch.setattr(api.ApprovalService, "cancel", cancel)

    response = view.cancel(SimpleNamespace(data={"transition_key": "cancel-1"}), pk=approval.id)

    assert response.data["status"] == "cancelled"
    assert captured == {
        "tenant": execution.tenant_id,
        "actor": actor_id,
        "approval_id": approval.id,
        "transition_key": "cancel-1",
    }


@pytest.mark.django_db
def test_tool_validate_action_returns_service_diagnostic(monkeypatch, tool, actor_id):
    view = api.ToolViewSet()
    view.get_object = lambda: tool
    view.tenant_id = lambda: tool.tenant_id
    view.actor_id = lambda: actor_id

    monkeypatch.setattr(
        api.ToolService,
        "validation_diagnostic",
        lambda tenant, tool_id, direction, value: {
            "tenant_id": str(tenant),
            "tool_id": str(tool_id),
            "direction": direction,
            "valid": value == {"value": 1},
            "issues": (),
        },
    )

    response = view.validate(SimpleNamespace(data={"direction": "input", "value": {"value": 1}}), pk=tool.id)

    assert response.data["valid"] is True
    assert response.data["tenant_id"] == str(tool.tenant_id)
    assert response.data["tool_id"] == str(tool.id)
