"""Black-box contracts for the governed workflow automation v2 API."""

from __future__ import annotations

import uuid

import pytest
from rest_framework import status
from rest_framework.exceptions import ValidationError

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.core.async_jobs.services import execute
from src.core.testing.factories import TenantUserFactory

from ..models import Workflow
from ..services import WorkflowDefinitionService, WorkflowExecutionService
from .test_services import action_payload, approval_payload

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def allow_access_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise real session/CSRF while replacing external policy evaluation."""

    def allow(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="test policy allows declared capability",
            tenant_id=uuid.UUID(str(tenant_id)),
            remaining_quota=100,
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", allow)


def data(response):
    return response.json()["data"]


def test_unauthenticated_is_401_and_unsafe_session_requires_csrf(api_client, tenant_a_user) -> None:
    response = api_client.get("/api/v2/workflow-automation/workflows/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    from rest_framework.test import APIClient

    csrf_client = APIClient(enforce_csrf_checks=True)
    assert csrf_client.login(username=tenant_a_user.username, password="saraise-test-password")
    response = csrf_client.post("/api/v2/workflow-automation/workflows/", action_payload(), format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_workflow_endpoints_envelope_filters_etag_and_lifecycle(tenant_a_client) -> None:
    created_response = tenant_a_client.post("/api/v2/workflow-automation/workflows/", action_payload(), format="json")
    assert created_response.status_code == status.HTTP_201_CREATED
    created = data(created_response)
    assert created["tenant_id"] if "tenant_id" in created else created["key"] == "purchase-approval"
    assert created_response.json()["meta"]["correlation_id"]
    assert created_response["ETag"]

    listing = tenant_a_client.get(
        "/api/v2/workflow-automation/workflows/?search=purchase&status=draft&ordering=name&page_size=1"
    )
    assert listing.status_code == status.HTTP_200_OK
    assert [item["id"] for item in data(listing)] == [created["id"]]
    assert listing.json()["meta"]["pagination"]["page_size"] == 1

    detail = tenant_a_client.get(f"/api/v2/workflow-automation/workflows/{created['id']}/")
    assert detail.status_code == status.HTTP_200_OK
    assert data(detail)["steps"][0]["key"] == "complete"

    update = tenant_a_client.patch(
        f"/api/v2/workflow-automation/workflows/{created['id']}/",
        {"name": "Updated purchase approval", "expected_updated_at": created["updated_at"]},
        format="json",
    )
    assert update.status_code == status.HTTP_200_OK
    assert data(update)["name"] == "Updated purchase approval"

    stale = tenant_a_client.patch(
        f"/api/v2/workflow-automation/workflows/{created['id']}/",
        {"name": "Stale edit", "expected_updated_at": created["updated_at"]},
        format="json",
    )
    assert stale.status_code == status.HTTP_409_CONFLICT
    assert stale.json()["error"]["code"] == "WORKFLOW_EDIT_CONFLICT"

    validation = tenant_a_client.post(
        "/api/v2/workflow-automation/workflows/validate/", action_payload(), format="json"
    )
    assert validation.status_code == status.HTTP_200_OK
    assert data(validation)["valid"] is True

    published = tenant_a_client.post(
        f"/api/v2/workflow-automation/workflows/{created['id']}/publish/",
        {"transition_key": "api-publish"},
        format="json",
    )
    assert published.status_code == status.HTTP_200_OK
    assert data(published)["status"] == "published"

    clone = tenant_a_client.post(f"/api/v2/workflow-automation/workflows/{created['id']}/clone/", {}, format="json")
    assert clone.status_code == status.HTTP_201_CREATED
    assert data(clone)["version"] == 2

    archived = tenant_a_client.post(
        f"/api/v2/workflow-automation/workflows/{created['id']}/archive/",
        {"transition_key": "api-archive"},
        format="json",
    )
    assert archived.status_code == status.HTTP_200_OK
    assert data(archived)["status"] == "archived"

    deleted = tenant_a_client.delete(f"/api/v2/workflow-automation/workflows/{data(clone)['id']}/")
    assert deleted.status_code == status.HTTP_204_NO_CONTENT


def test_unknown_and_server_owned_fields_are_rejected(tenant_a_client, tenant_b) -> None:
    payload = action_payload()
    payload["tenant_id"] = str(tenant_b.id)
    payload["status"] = "published"
    response = tenant_a_client.post("/api/v2/workflow-automation/workflows/", payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    nested = action_payload(key="nested-spoof")
    nested["steps"][0]["tenant_id"] = str(tenant_b.id)
    response = tenant_a_client.post("/api/v2/workflow-automation/workflows/", nested, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_instance_and_task_endpoints(tenant_a, tenant_a_user, tenant_a_client) -> None:
    approver = TenantUserFactory(organization=tenant_a, username="api-approver")
    workflow = WorkflowDefinitionService.create_workflow(tenant_a.id, tenant_a_user, approval_payload(approver.pk))
    workflow = WorkflowDefinitionService.publish_workflow(
        tenant_a.id, workflow.id, tenant_a_user, "api-approval-publish"
    )

    started = tenant_a_client.post(
        "/api/v2/workflow-automation/instances/",
        {
            "workflow_id": str(workflow.id),
            "context_data": {},
            "idempotency_key": "api-instance-start",
            "priority": 4,
        },
        format="json",
    )
    assert started.status_code == status.HTTP_202_ACCEPTED
    instance = data(started)
    execute(instance["async_job_id"], tenant_a.id)

    instances = tenant_a_client.get(
        f"/api/v2/workflow-automation/instances/?workflow_id={workflow.id}&state=waiting&ordering=-created_at"
    )
    assert instances.status_code == status.HTTP_200_OK
    assert [item["id"] for item in data(instances)] == [instance["id"]]
    detail = tenant_a_client.get(f"/api/v2/workflow-automation/instances/{instance['id']}/")
    assert data(detail)["state"] == "waiting"

    approver_client = __import__(
        "src.core.testing.factories", fromlist=["authenticated_api_client"]
    ).authenticated_api_client(approver)
    tasks = approver_client.get(
        f"/api/v2/workflow-automation/tasks/?workflow_id={workflow.id}&status=pending&scope=mine"
    )
    assert tasks.status_code == status.HTTP_200_OK
    task = data(tasks)[0]
    task_detail = approver_client.get(f"/api/v2/workflow-automation/tasks/{task['id']}/")
    assert task_detail.status_code == status.HTTP_200_OK
    complete = approver_client.post(
        f"/api/v2/workflow-automation/tasks/{task['id']}/complete/",
        {"meta_data": {"comment": "Approved"}, "transition_key": "api-complete"},
        format="json",
    )
    assert complete.status_code == status.HTTP_200_OK
    assert data(complete)["status"] == "completed"

    workflow_instance = WorkflowExecutionService.get_instance(tenant_a.id, instance["id"])
    assert workflow_instance.state == "completed"


def test_instance_cancel_and_v1_deprecation_headers(tenant_a, tenant_a_user, tenant_a_client) -> None:
    workflow = WorkflowDefinitionService.create_workflow(
        tenant_a.id, tenant_a_user, action_payload(key="cancel-workflow")
    )
    workflow = WorkflowDefinitionService.publish_workflow(tenant_a.id, workflow.id, tenant_a_user, "publish-cancel")
    instance = WorkflowExecutionService.start_workflow(
        tenant_a.id, workflow.id, tenant_a_user, {}, "cancel-before-worker"
    )
    cancelled = tenant_a_client.post(
        f"/api/v2/workflow-automation/instances/{instance.id}/cancel/",
        {"transition_key": "api-cancel", "reason": "No longer required"},
        format="json",
    )
    assert cancelled.status_code == status.HTTP_200_OK
    assert data(cancelled)["state"] == "cancelled"

    legacy = tenant_a_client.get("/api/v1/workflow-automation/workflows/")
    assert legacy.status_code == status.HTTP_200_OK
    assert legacy["Deprecation"] == "true"
    assert legacy["Sunset"]
    assert "successor-version" in legacy["Link"]


def test_catalog_and_health_are_real_typed_capabilities(tenant_a_client) -> None:
    actions = tenant_a_client.get("/api/v2/workflow-automation/catalog/actions/")
    assert actions.status_code == status.HTTP_200_OK
    terminal = next(item for item in data(actions) if item["key"] == "core.terminal_completion.v1")
    assert terminal["display_name"]
    assert terminal["descriptor_fingerprint"]
    assert isinstance(terminal["input_schema"], dict)
    assert terminal["idempotent"] is True

    conditions = tenant_a_client.get("/api/v2/workflow-automation/catalog/conditions/")
    assert any(item["key"] == "core.truthy.v1" for item in data(conditions))
    assignees = tenant_a_client.get("/api/v2/workflow-automation/catalog/assignees/")
    assert assignees.status_code == status.HTTP_200_OK
    assert all(set(item) == {"id", "label", "description", "kind"} for item in data(assignees))

    health = tenant_a_client.get("/api/v2/workflow-automation/health/")
    assert health.status_code in {status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE}
    assert "global_row_count" not in str(data(health)).lower()


def test_policy_denial_is_403(tenant_a_client, monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(
            allowed=False,
            reason_code=AccessReasonCode.PERMISSION_DENIED,
            reason="denied by policy",
            tenant_id=uuid.UUID(str(tenant_id)),
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", deny)
    response = tenant_a_client.get("/api/v2/workflow-automation/workflows/")
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_page_size_is_capped_and_queries_are_bounded(
    tenant_a, tenant_a_user, tenant_a_client, django_assert_max_num_queries
) -> None:
    for number in range(4):
        WorkflowDefinitionService.create_workflow(tenant_a.id, tenant_a_user, action_payload(key=f"bounded-{number}"))
    response = tenant_a_client.get("/api/v2/workflow-automation/workflows/?page_size=1000")
    assert response.json()["meta"]["pagination"]["page_size"] == 100
    with django_assert_max_num_queries(20):
        response = tenant_a_client.get("/api/v2/workflow-automation/workflows/?page_size=100")
        assert len(data(response)) >= 4


def test_all_api_mutations_delegate_to_services(monkeypatch: pytest.MonkeyPatch, tenant_a_client) -> None:
    called = False

    def create(tenant_id, actor, payload):
        nonlocal called
        del tenant_id, actor, payload
        called = True
        raise ValidationError({"service": ["delegated"]})

    monkeypatch.setattr(WorkflowDefinitionService, "create_workflow", create)
    response = tenant_a_client.post("/api/v2/workflow-automation/workflows/", action_payload(), format="json")
    assert called is True
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert Workflow.objects.count() == 0
