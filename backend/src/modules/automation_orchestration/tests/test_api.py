"""Black-box contracts for the governed v2 orchestration API."""

from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.core.api.results import CapabilityUnavailable, OperationFailed

from ..api import (
    ConfigurationViewSet,
    DefinitionViewSet,
    EdgeViewSet,
    NodeViewSet,
    OrchestrationHealthView,
    RunViewSet,
    ScheduleViewSet,
    TaskRunViewSet,
    _actor_id,
    _as_uuid,
    _service_call,
)
from ..models import OrchestrationDefinition, OrchestrationTaskRun
from ..services import (
    DefinitionService,
    ExecutionService,
    OrchestrationServiceError,
    ServiceValidationError,
    StateConflictError,
)

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def allow_access_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep real session/CSRF authentication while replacing remote policy IO."""

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


def _payload(response):
    return response.json()["data"]


def _definition_payload(key: str = "api-flow") -> dict[str, object]:
    return {
        "key": key,
        "name": "API flow",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": True},
        "output_schema": {"type": "object", "properties": {}, "additionalProperties": True},
    }


def _create_definition(client, key: str = "api-flow") -> dict[str, object]:
    response = client.post("/api/v2/automation-orchestration/definitions/", _definition_payload(key), format="json")
    assert response.status_code == status.HTTP_201_CREATED
    return _payload(response)


def _add_node(client, definition_id: str, key: str = "root", *, priority: int = 0) -> dict[str, object]:
    response = client.post(
        f"/api/v2/automation-orchestration/definitions/{definition_id}/nodes/",
        {
            "key": key,
            "name": key.title(),
            "node_type": "internal",
            "handler_key": "core.passthrough",
            "priority": priority,
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    return _payload(response)


def _actor_uuid_for_user(user) -> uuid.UUID:
    return _actor_id(type("Request", (), {"user": user})())


def _publish_via_service(tenant_id: uuid.UUID, actor_id: uuid.UUID, key: str = "api-published"):
    definition = DefinitionService.create_definition(tenant_id, actor_id, _definition_payload(key))
    DefinitionService.add_node(
        tenant_id,
        definition.id,
        actor_id,
        {"key": "root", "name": "Root", "node_type": "internal", "handler_key": "core.passthrough"},
    )
    return DefinitionService.publish(tenant_id, definition.id, actor_id, f"publish-{key}")


def test_unauthenticated_definition_list_is_401(api_client) -> None:
    response = api_client.get("/api/v2/automation-orchestration/definitions/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_api_boundary_helpers_normalize_invalid_inputs_and_service_errors() -> None:
    assert _as_uuid("00000000-0000-0000-0000-000000000001", "id") == uuid.UUID("00000000-0000-0000-0000-000000000001")
    with pytest.raises(ValidationError):
        _as_uuid("not-a-uuid", "id")
    with pytest.raises(NotFound):
        _service_call(lambda: (_ for _ in ()).throw(OrchestrationDefinition.DoesNotExist()))
    with pytest.raises(OperationFailed) as conflict:
        _service_call(lambda: (_ for _ in ()).throw(StateConflictError("No", code="NOPE")))
    assert conflict.value.status_code == status.HTTP_409_CONFLICT
    assert conflict.value.error_code == "NOPE"
    with pytest.raises(ValidationError) as validation:
        _service_call(lambda: (_ for _ in ()).throw(ServiceValidationError("Bad", code="BAD_INPUT")))
    assert "Bad" in str(validation.value.detail)
    with pytest.raises(ValidationError) as django_validation:
        _service_call(lambda: (_ for _ in ()).throw(DjangoValidationError({"field": ["No"]})))
    assert "field" in str(django_validation.value.detail)
    with pytest.raises(OperationFailed) as service_error:
        _service_call(lambda: (_ for _ in ()).throw(OrchestrationServiceError("Down", code="DOWN")))
    assert service_error.value.error_code == "DOWN"


def test_definition_crud_uses_v2_envelope_and_pagination(tenant_a_client, tenant_a) -> None:
    create = tenant_a_client.post(
        "/api/v2/automation-orchestration/definitions/",
        {
            "key": "daily-ledger",
            "name": "Daily ledger",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            "output_schema": {"type": "object", "properties": {}, "additionalProperties": True},
        },
        format="json",
    )
    assert create.status_code == status.HTTP_201_CREATED
    created = _payload(create)
    assert created["tenant_id"] == str(tenant_a.id)
    assert create.json()["meta"]["correlation_id"]

    listing = tenant_a_client.get("/api/v2/automation-orchestration/definitions/?search=ledger&page_size=1")
    assert listing.status_code == status.HTTP_200_OK
    assert listing.json()["meta"]["pagination"]["page_size"] == 1
    assert [item["id"] for item in _payload(listing)] == [created["id"]]

    update = tenant_a_client.patch(
        f"/api/v2/automation-orchestration/definitions/{created['id']}/",
        {"name": "Daily general ledger", "transition_key": "api-edit"},
        format="json",
    )
    assert update.status_code == status.HTTP_200_OK
    assert _payload(update)["name"] == "Daily general ledger"

    delete = tenant_a_client.delete(f"/api/v2/automation-orchestration/definitions/{created['id']}/")
    assert delete.status_code == status.HTTP_204_NO_CONTENT
    assert OrchestrationDefinition.objects.get(pk=created["id"]).is_deleted is True


def test_unknown_and_protected_definition_fields_are_rejected(tenant_a_client, tenant_b) -> None:
    response = tenant_a_client.post(
        "/api/v2/automation-orchestration/definitions/",
        {"key": "spoof", "name": "Spoof", "tenant_id": str(tenant_b.id), "status": "published"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unsafe_action_requires_csrf(tenant_a_user) -> None:
    from src.core.testing.factories import authenticated_api_client

    client = authenticated_api_client(tenant_a_user, enforce_csrf_checks=False)
    # Re-enable enforcement with a fresh client/session and deliberately omit the token.
    from rest_framework.test import APIClient

    csrf_client = APIClient(enforce_csrf_checks=True)
    assert csrf_client.login(username=tenant_a_user.username, password="saraise-test-password")
    response = csrf_client.post(
        "/api/v2/automation-orchestration/definitions/", {"key": "csrf", "name": "CSRF"}, format="json"
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    del client


@pytest.mark.parametrize(
    ("viewset", "actions"),
    [
        (
            DefinitionViewSet,
            {
                "list",
                "retrieve",
                "create",
                "partial_update",
                "destroy",
                "validate_graph",
                "publish",
                "clone",
                "retire",
                "nodes",
                "edges",
                "snapshot",
            },
        ),
        (NodeViewSet, {"retrieve", "partial_update", "destroy"}),
        (EdgeViewSet, {"retrieve", "partial_update", "destroy"}),
        (ScheduleViewSet, {"list", "retrieve", "create", "partial_update", "destroy", "pause", "resume", "retire"}),
        (RunViewSet, {"list", "retrieve", "create", "pause", "resume", "cancel", "retry", "task_runs", "events"}),
        (TaskRunViewSet, {"retrieve", "retry"}),
        (
            ConfigurationViewSet,
            {"list", "create", "preview", "versions", "audits", "rollback", "import_document", "export_document"},
        ),
    ],
)
def test_every_action_has_explicit_access_metadata(viewset, actions) -> None:
    assert set(viewset.access_by_action) == actions
    assert all(requirement.permission and requirement.entitlement for requirement in viewset.access_by_action.values())


def test_cross_tenant_definition_identifier_is_404(tenant_a_client, tenant_b) -> None:
    definition = OrchestrationDefinition.objects.create(
        tenant_id=tenant_b.id,
        key="private",
        version=1,
        name="Private",
        created_by=uuid.uuid4(),
        updated_by=uuid.uuid4(),
    )
    response = tenant_a_client.get(f"/api/v2/automation-orchestration/definitions/{definition.id}/")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_node_catalog_exposes_real_core_descriptor(tenant_a_client) -> None:
    response = tenant_a_client.get("/api/v2/automation-orchestration/node-types/")
    assert response.status_code == status.HTTP_200_OK
    descriptors = _payload(response)
    assert any(item["key"] == "core.passthrough" for item in descriptors)


def test_definition_graph_actions_cover_nodes_edges_snapshot_publish_clone_and_retire(tenant_a_client) -> None:
    definition = _create_definition(tenant_a_client, "api-graph")
    root = _add_node(tenant_a_client, definition["id"], "root", priority=10)
    child = _add_node(tenant_a_client, definition["id"], "child")

    nodes = tenant_a_client.get(f"/api/v2/automation-orchestration/definitions/{definition['id']}/nodes/?page_size=5")
    assert nodes.status_code == status.HTTP_200_OK
    assert [item["key"] for item in _payload(nodes)] == ["root", "child"]

    node_detail = tenant_a_client.get(f"/api/v2/automation-orchestration/nodes/{root['id']}/")
    assert node_detail.status_code == status.HTTP_200_OK
    assert _payload(node_detail)["key"] == "root"

    node_update = tenant_a_client.patch(
        f"/api/v2/automation-orchestration/nodes/{child['id']}/",
        {"name": "Child renamed", "priority": 5},
        format="json",
    )
    assert node_update.status_code == status.HTTP_200_OK
    assert _payload(node_update)["name"] == "Child renamed"

    edge_create = tenant_a_client.post(
        f"/api/v2/automation-orchestration/definitions/{definition['id']}/edges/",
        {"upstream_node_id": root["id"], "downstream_node_id": child["id"], "condition": "always"},
        format="json",
    )
    assert edge_create.status_code == status.HTTP_201_CREATED
    edge = _payload(edge_create)

    edges = tenant_a_client.get(f"/api/v2/automation-orchestration/definitions/{definition['id']}/edges/?page_size=5")
    assert edges.status_code == status.HTTP_200_OK
    assert _payload(edges)[0]["id"] == edge["id"]

    edge_detail = tenant_a_client.get(f"/api/v2/automation-orchestration/edges/{edge['id']}/")
    assert edge_detail.status_code == status.HTTP_200_OK
    edge_update = tenant_a_client.patch(
        f"/api/v2/automation-orchestration/edges/{edge['id']}/",
        {"condition": "on_success", "priority": 3},
        format="json",
    )
    assert edge_update.status_code == status.HTTP_200_OK
    assert _payload(edge_update)["priority"] == 3

    validation = tenant_a_client.post(f"/api/v2/automation-orchestration/definitions/{definition['id']}/validate/")
    assert validation.status_code == status.HTTP_200_OK
    assert _payload(validation)["valid"] is True

    snapshot = tenant_a_client.get(f"/api/v2/automation-orchestration/definitions/{definition['id']}/snapshot/")
    assert snapshot.status_code == status.HTTP_200_OK
    assert snapshot["ETag"].startswith('"graph-')

    published = tenant_a_client.post(
        f"/api/v2/automation-orchestration/definitions/{definition['id']}/publish/",
        {"transition_key": "api-publish"},
        format="json",
    )
    assert published.status_code == status.HTTP_200_OK
    assert _payload(published)["status"] == "published"

    clone = tenant_a_client.post(f"/api/v2/automation-orchestration/definitions/{definition['id']}/clone/")
    assert clone.status_code == status.HTTP_201_CREATED
    assert _payload(clone)["version"] == 2

    retired = tenant_a_client.post(
        f"/api/v2/automation-orchestration/definitions/{definition['id']}/retire/",
        {"transition_key": "api-retire"},
        format="json",
    )
    assert retired.status_code == status.HTTP_200_OK
    assert _payload(retired)["status"] == "retired"


def test_node_and_edge_destroy_soft_delete_draft_graph_members(tenant_a_client) -> None:
    definition = _create_definition(tenant_a_client, "api-delete-graph")
    root = _add_node(tenant_a_client, definition["id"], "root")
    child = _add_node(tenant_a_client, definition["id"], "child")
    edge = _payload(
        tenant_a_client.post(
            f"/api/v2/automation-orchestration/definitions/{definition['id']}/edges/",
            {"upstream_node_id": root["id"], "downstream_node_id": child["id"]},
            format="json",
        )
    )

    edge_delete = tenant_a_client.delete(f"/api/v2/automation-orchestration/edges/{edge['id']}/")
    assert edge_delete.status_code == status.HTTP_204_NO_CONTENT
    node_delete = tenant_a_client.delete(f"/api/v2/automation-orchestration/nodes/{child['id']}/")
    assert node_delete.status_code == status.HTTP_204_NO_CONTENT


def test_schedule_api_filters_updates_transitions_and_deletes(tenant_a_client, tenant_a, tenant_a_user) -> None:
    definition = _publish_via_service(tenant_a.id, _actor_uuid_for_user(tenant_a_user), "api-schedule")
    create = tenant_a_client.post(
        "/api/v2/automation-orchestration/schedules/",
        {
            "definition_id": str(definition.id),
            "name": "Business hours",
            "cron_expression": "0 8 * * 1-5",
            "timezone": "UTC",
            "misfire_policy": "run_once",
            "input": {},
        },
        format="json",
    )
    assert create.status_code == status.HTTP_201_CREATED
    schedule = _payload(create)

    listing = tenant_a_client.get(
        "/api/v2/automation-orchestration/schedules/",
        {"status": "active", "definition_id": str(definition.id), "search": "Business", "page_size": 5},
    )
    assert listing.status_code == status.HTTP_200_OK
    assert [item["id"] for item in _payload(listing)] == [schedule["id"]]

    bad_due_before = tenant_a_client.get("/api/v2/automation-orchestration/schedules/?due_before=not-a-date")
    assert bad_due_before.status_code == status.HTTP_400_BAD_REQUEST

    detail = tenant_a_client.get(f"/api/v2/automation-orchestration/schedules/{schedule['id']}/")
    assert detail.status_code == status.HTTP_200_OK

    update = tenant_a_client.patch(
        f"/api/v2/automation-orchestration/schedules/{schedule['id']}/",
        {"name": "Business hours updated", "timezone": "Asia/Kolkata", "transition_key": "ignored-by-update"},
        format="json",
    )
    assert update.status_code == status.HTTP_200_OK
    assert _payload(update)["timezone"] == "Asia/Kolkata"

    paused = tenant_a_client.post(
        f"/api/v2/automation-orchestration/schedules/{schedule['id']}/pause/",
        {"transition_key": "api-pause-schedule"},
        format="json",
    )
    assert paused.status_code == status.HTTP_200_OK
    resumed = tenant_a_client.post(
        f"/api/v2/automation-orchestration/schedules/{schedule['id']}/resume/",
        {"transition_key": "api-resume-schedule"},
        format="json",
    )
    assert resumed.status_code == status.HTTP_200_OK
    retired = tenant_a_client.post(
        f"/api/v2/automation-orchestration/schedules/{schedule['id']}/retire/",
        {"transition_key": "api-retire-schedule"},
        format="json",
    )
    assert retired.status_code == status.HTTP_200_OK
    deleted = tenant_a_client.delete(f"/api/v2/automation-orchestration/schedules/{schedule['id']}/")
    assert deleted.status_code == status.HTTP_204_NO_CONTENT


def test_run_and_task_api_lists_controls_events_and_retry_lineage(tenant_a_client, tenant_a, tenant_a_user) -> None:
    definition = _publish_via_service(tenant_a.id, _actor_uuid_for_user(tenant_a_user), "api-run")
    create = tenant_a_client.post(
        "/api/v2/automation-orchestration/runs/",
        {"definition_id": str(definition.id), "input": {}, "idempotency_key": "api-run-1", "trigger_type": "manual"},
        format="json",
    )
    assert create.status_code == status.HTTP_202_ACCEPTED
    run = _payload(create)

    invalid_date = tenant_a_client.get("/api/v2/automation-orchestration/runs/?created_from=not-a-date")
    assert invalid_date.status_code == status.HTTP_400_BAD_REQUEST

    listing = tenant_a_client.get(
        "/api/v2/automation-orchestration/runs/",
        {"status": "queued", "definition_id": str(definition.id), "trigger_type": "manual", "page_size": 5},
    )
    assert listing.status_code == status.HTTP_200_OK
    assert [item["id"] for item in _payload(listing)] == [run["id"]]

    detail = tenant_a_client.get(f"/api/v2/automation-orchestration/runs/{run['id']}/")
    assert detail.status_code == status.HTTP_200_OK

    task_runs = tenant_a_client.get(f"/api/v2/automation-orchestration/runs/{run['id']}/task-runs/?page_size=5")
    assert task_runs.status_code == status.HTTP_200_OK
    task_id = _payload(task_runs)[0]["id"]

    task_detail = tenant_a_client.get(f"/api/v2/automation-orchestration/task-runs/{task_id}/")
    assert task_detail.status_code == status.HTTP_200_OK

    events = tenant_a_client.get(f"/api/v2/automation-orchestration/runs/{run['id']}/events/?page_size=5")
    assert events.status_code == status.HTTP_200_OK
    assert any(item["event_type"] == "run.queued" for item in _payload(events))

    cancelled = tenant_a_client.post(
        f"/api/v2/automation-orchestration/runs/{run['id']}/cancel/",
        {"transition_key": "api-cancel-run"},
        format="json",
    )
    assert cancelled.status_code == status.HTTP_200_OK
    assert _payload(cancelled)["status"] == "cancelled"

    retry = tenant_a_client.post(
        f"/api/v2/automation-orchestration/runs/{run['id']}/retry/",
        {"idempotency_key": "api-run-1-retry"},
        format="json",
    )
    assert retry.status_code == status.HTTP_202_ACCEPTED
    assert _payload(retry)["parent_run_id"] == run["id"]

    task_retry = tenant_a_client.post(
        f"/api/v2/automation-orchestration/task-runs/{task_id}/retry/",
        {"idempotency_key": "api-task-retry"},
        format="json",
    )
    assert task_retry.status_code == status.HTTP_202_ACCEPTED
    assert _payload(task_retry)["node_key"] == "root"


def test_run_pause_resume_and_cancel_actions_use_shared_control_path(tenant_a_client, tenant_a, tenant_a_user) -> None:
    actor_id = _actor_uuid_for_user(tenant_a_user)
    definition = _publish_via_service(tenant_a.id, actor_id, "api-run-control")
    run = ExecutionService.start_run(tenant_a.id, definition.id, actor_id, {}, "api-running", "manual")
    ExecutionService.execute_run(tenant_a.id, run.id)

    paused = tenant_a_client.post(
        f"/api/v2/automation-orchestration/runs/{run.id}/pause/",
        {"transition_key": "api-pause-run"},
        format="json",
    )
    assert paused.status_code == status.HTTP_200_OK
    assert _payload(paused)["status"] == "paused"

    resumed = tenant_a_client.post(
        f"/api/v2/automation-orchestration/runs/{run.id}/resume/",
        {"transition_key": "api-resume-run"},
        format="json",
    )
    assert resumed.status_code == status.HTTP_200_OK
    assert _payload(resumed)["status"] == "running"

    cancelled = tenant_a_client.post(
        f"/api/v2/automation-orchestration/runs/{run.id}/cancel/",
        {"transition_key": "api-cancel-running"},
        format="json",
    )
    assert cancelled.status_code == status.HTTP_200_OK
    assert _payload(cancelled)["status"] == "cancelled"


def test_configuration_api_round_trips_preview_versions_audit_rollback_import_and_export(tenant_a_client) -> None:
    document = {"defaults": {"max_parallel_tasks": 7}}
    preview = tenant_a_client.post(
        "/api/v2/automation-orchestration/configuration/preview/",
        {"environment": "development", "cohort": "api", "document": document},
        format="json",
    )
    assert preview.status_code == status.HTTP_200_OK
    assert preview.json()["data"]["changed_sections"] == ["defaults"]

    create = tenant_a_client.post(
        "/api/v2/automation-orchestration/configuration/",
        {
            "environment": "development",
            "cohort": "api",
            "document": document,
            "enabled": True,
            "rollout_percentage": 50,
            "allowed_roles": ["ops"],
        },
        format="json",
    )
    assert create.status_code == status.HTTP_201_CREATED
    assert create.json()["data"]["version"] == 1

    exported = tenant_a_client.get(
        "/api/v2/automation-orchestration/configuration/export/?environment=development&cohort=api"
    )
    assert exported.status_code == status.HTTP_200_OK
    assert exported.json()["data"]["document"]["defaults"]["max_parallel_tasks"] == 7

    imported = tenant_a_client.post(
        "/api/v2/automation-orchestration/configuration/import/",
        {
            "environment": "development",
            "cohort": "api",
            "document": {"defaults": {"max_parallel_tasks": 8}},
            "enabled": True,
        },
        format="json",
    )
    assert imported.status_code == status.HTTP_201_CREATED
    assert imported.json()["data"]["version"] == 2

    versions = tenant_a_client.get(
        "/api/v2/automation-orchestration/configuration/versions/?environment=development&cohort=api"
    )
    assert versions.status_code == status.HTTP_200_OK
    assert [item["version"] for item in _payload(versions)] == [2, 1]

    audits = tenant_a_client.get(
        "/api/v2/automation-orchestration/configuration/audits/?environment=development&cohort=api"
    )
    assert audits.status_code == status.HTTP_200_OK
    assert len(_payload(audits)) == 2

    rollback = tenant_a_client.post(
        "/api/v2/automation-orchestration/configuration/rollback/",
        {"environment": "development", "cohort": "api", "version": 1},
        format="json",
    )
    assert rollback.status_code == status.HTTP_200_OK
    assert rollback.json()["data"]["version"] == 3


def test_health_view_maps_ready_and_not_ready_payloads(tenant_a_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.modules.automation_orchestration.api.sanitized_health_payload",
        lambda tenant_id: ({"status": "ready", "checks": {"database": "ready"}}, status.HTTP_200_OK),
    )
    ready = tenant_a_client.get("/api/v2/automation-orchestration/health/")
    assert ready.status_code == status.HTTP_200_OK
    assert _payload(ready)["status"] == "ready"

    monkeypatch.setattr(
        "src.modules.automation_orchestration.api.sanitized_health_payload",
        lambda tenant_id: (
            {"status": "not_ready", "checks": {"database": "unavailable"}},
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ),
    )
    not_ready = tenant_a_client.get("/api/v2/automation-orchestration/health/")
    assert not_ready.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert not_ready.json()["error"]["code"] == "CAPABILITY_UNAVAILABLE"


def test_viewset_fallbacks_cover_missing_tenant_and_pagination_guard(api_client) -> None:
    view = DefinitionViewSet()
    assert view.tenant_id_or_none() is None

    class NoPaginationView(DefinitionViewSet):
        def paginate_queryset(self, queryset):
            return None

    with pytest.raises(CapabilityUnavailable):
        NoPaginationView()._paginate([], DefinitionViewSet)

    auth = __import__(
        "src.modules.automation_orchestration.api", fromlist=["RequiredSessionAuthentication"]
    ).RequiredSessionAuthentication()
    assert auth.authenticate_header(api_client.get("/").wsgi_request) == "Session"
    assert OrchestrationHealthView.required_permission
    assert OrchestrationTaskRun.objects.none().count() == 0
