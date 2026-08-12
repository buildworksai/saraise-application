"""Governed v2 routing, envelope, serializer, and service delegation tests."""

import uuid
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess

from .. import api
from ..models import AnalysisStatus, ExportStatus
from ..permissions import ActionAccessMixin
from ..serializers import EventBatchIngestSerializer, ProcessModelCreateSerializer, TransitionActionSerializer
from ..services import DEFAULT_CONFIGURATION, IngestResult
from .factories import (
    AnalysisFactory,
    CaseMetricFactory,
    ConformanceFactory,
    DeviationFactory,
    DiscoveryFactory,
    EventFactory,
    ExportFactory,
    FindingFactory,
    ModelFactory,
    VariantFactory,
    VersionFactory,
    graph,
)

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db
BASE = "/api/v2/process-mining"
ORIGINAL_GET_PERMISSIONS = ActionAccessMixin.get_permissions


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
    payload = {
        "process_name": "orders",
        "source_module": "canonical",
        "events": [{"case_id": "c", "activity": "a", "occurred_at": "2026-07-21T08:00:00Z"}],
    }
    with patch.object(api.EventLogService, "ingest_events", return_value=IngestResult(1, 0, 0, ())) as method:
        response = authenticated_tenant_a_client.post(f"{BASE}/events/", payload, format="json")
    assert response.status_code == 201 and response.json()["data"]["accepted"] == 1
    method.assert_called_once()
    _tenant_id, _actor_id, source_module, process_name, events = method.call_args.args
    assert source_module == "canonical"
    assert process_name == "orders"
    assert events[0]["case_id"] == "c"
    assert events[0]["activity"] == "a"
    assert events[0]["occurred_at"].isoformat().startswith("2026-07-21T08:00:00")


def test_action_access_mixin_sets_valid_tenant_permission_and_default_quota():
    tenant_id = uuid.uuid4()

    class View(ActionAccessMixin):
        action_permissions = {"list": "process_mining.event:read"}

    view = View()
    view.action = "list"
    view.request = SimpleNamespace(user=SimpleNamespace(profile=SimpleNamespace(tenant_id=str(tenant_id))))

    permissions = ORIGINAL_GET_PERMISSIONS(view)

    assert view.request.tenant_id == tenant_id
    assert view.required_permission == "process_mining.event:read"
    assert view.required_entitlement == "process_mining.core"
    assert view.quota_resource == "process_mining.api_reads"
    assert view.quota_cost == 1
    assert [permission.__class__ for permission in permissions] == [IsAuthenticated, RequiresAccess]


def test_action_access_mixin_invalid_tenant_fails_closed_and_sets_action_quota():
    class View(ActionAccessMixin):
        action_permissions = {"create": "process_mining.export:create"}
        action_quotas = {"create": "process_mining.export_bytes"}

    view = View()
    view.action = "create"
    view.request = SimpleNamespace(user=SimpleNamespace(profile=SimpleNamespace(tenant_id="not-a-uuid")))

    ORIGINAL_GET_PERMISSIONS(view)

    assert view.request.tenant_id is None
    assert view.required_permission == "process_mining.export:create"
    assert view.required_entitlement == "process_mining.core"
    assert view.quota_resource == "process_mining.export_bytes"
    assert view.quota_cost == 1


@pytest.mark.parametrize(
    "serializer,payload",
    [
        (
            EventBatchIngestSerializer,
            {
                "process_name": "p",
                "source_module": "canonical",
                "events": [{"case_id": "c", "activity": "a", "occurred_at": "2026-07-21T08:00:00Z"}],
            },
        ),
        (ProcessModelCreateSerializer, {"name": "m", "process_name": "p", "description": "", "model_data": graph()}),
        (TransitionActionSerializer, {"transition_key": "key"}),
    ],
)
def test_mutation_serializers_reject_tenant_spoofing(serializer, payload):
    value = serializer(data={**payload, "tenant_id": str(uuid.uuid4())})
    assert not value.is_valid() and "tenant_id" in value.errors


def test_unknown_ordering_returns_validation_envelope(authenticated_tenant_a_client):
    response = authenticated_tenant_a_client.get(f"{BASE}/exports/?ordering=artifact_key")
    assert response.status_code == 400 and response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_export_retry_requires_idempotency_key(authenticated_tenant_a_client, tenant_a):
    export = ExportFactory(tenant_id=tenant_a.id)

    response = authenticated_tenant_a_client.post(
        f"{BASE}/exports/{export.id}/retry/", {"transition_key": "retry-once"}, format="json"
    )

    assert response.status_code == 400
    assert response.json()["error"]["detail"]["idempotency_key"] == "This field is required for retry."


@pytest.mark.parametrize("path", ["discoveries", "conformance-checks", "bottleneck-analyses"])
def test_invalid_detail_identifiers_are_404_not_500(authenticated_tenant_a_client, path):
    response = authenticated_tenant_a_client.get(f"{BASE}/{path}/__uat_invalid_id__/")
    assert response.status_code == 404


def test_append_only_event_methods_are_not_routed(authenticated_tenant_a_client, tenant_a):
    event = EventFactory(tenant_id=tenant_a.id)
    assert authenticated_tenant_a_client.patch(f"{BASE}/events/{event.id}/", {}, format="json").status_code == 405
    assert authenticated_tenant_a_client.delete(f"{BASE}/events/{event.id}/").status_code == 405


def test_tenant_governed_viewset_fails_closed_for_invalid_tenant_actor_and_rollout(monkeypatch, tenant_a_user):
    view = api.TenantGovernedViewSet()
    view.request = SimpleNamespace(user=SimpleNamespace(profile=SimpleNamespace(tenant_id="bad"), id=uuid.uuid4()))
    assert view.tenant_queryset(api.ProcessEvent).count() == 0
    with pytest.raises(api.PermissionDenied):
        view.tenant_id()

    view.request = SimpleNamespace(
        user=SimpleNamespace(profile=SimpleNamespace(tenant_id=tenant_a_user.profile.tenant_id))
    )
    with pytest.raises(api.PermissionDenied):
        view.actor_id()

    disabled = {**DEFAULT_CONFIGURATION, "enabled": False}
    monkeypatch.setattr(api.ProcessMiningConfigurationService, "resolve", lambda self, tenant_id: disabled)
    view.request = SimpleNamespace(user=tenant_a_user)
    with pytest.raises(api.PermissionDenied):
        view.tenant_id()

    role_limited = {**DEFAULT_CONFIGURATION, "rollout_roles": ["finance_manager"]}
    monkeypatch.setattr(api.ProcessMiningConfigurationService, "resolve", lambda self, tenant_id: role_limited)
    with pytest.raises(api.PermissionDenied):
        view.tenant_id()

    cohort_limited = {**DEFAULT_CONFIGURATION, "rollout_cohorts": ["beta"]}
    monkeypatch.setattr(api.ProcessMiningConfigurationService, "resolve", lambda self, tenant_id: cohort_limited)
    with pytest.raises(api.PermissionDenied):
        view.tenant_id()


def test_process_overview_list_retrieve_and_not_found(authenticated_tenant_a_client):
    rows = [{"process_name": "order_to_cash", "case_count": 7}]
    with patch.object(api.ProcessModelService, "get_process_overview", side_effect=[rows, rows, []]) as service:
        listing = authenticated_tenant_a_client.get(f"{BASE}/processes/")
        detail = authenticated_tenant_a_client.get(f"{BASE}/processes/order_to_cash/")
        missing = authenticated_tenant_a_client.get(f"{BASE}/processes/missing/")

    assert listing.status_code == 200
    assert listing.json()["data"][0]["process_name"] == "order_to_cash"
    assert detail.status_code == 200
    assert detail.json()["data"]["case_count"] == 7
    assert missing.status_code == 404
    assert service.call_count == 3


def test_event_retrieve_uses_service_query_filters_and_detail_serializer(authenticated_tenant_a_client, tenant_a):
    event = EventFactory(tenant_id=tenant_a.id, process_name="orders")
    response = authenticated_tenant_a_client.get(
        f"{BASE}/events/{event.id}/",
        {"process_name": "orders", "start": event.occurred_at.isoformat(), "end": event.occurred_at.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(event.id)


def test_export_create_download_cancel_retry_and_delete_delegate_to_services(authenticated_tenant_a_client, tenant_a):
    export = ExportFactory(
        tenant_id=tenant_a.id,
        status=ExportStatus.COMPLETED,
        artifact_key="exports/order_to_cash.json",
        content_type="application/json",
    )
    queued = ExportFactory(tenant_id=tenant_a.id, idempotency_key="export-create")
    retry_job = ExportFactory(tenant_id=tenant_a.id, idempotency_key="export-retry")

    with (
        patch.object(api.ExportService, "request_export", return_value=queued) as request_export,
        patch.object(api.ExportService, "open_download", return_value=(export, BytesIO(b"[]"))) as open_download,
        patch.object(api.ExportService, "cancel_export", return_value=export) as cancel_export,
        patch.object(api.ExportService, "retry_export", return_value=retry_job) as retry_export,
        patch.object(api.ExportService, "delete_export") as delete_export,
    ):
        created = authenticated_tenant_a_client.post(
            f"{BASE}/exports/",
            {
                "process_name": "order_to_cash",
                "format": "json",
                "event_filter": {"activity": "Approve"},
                "idempotency_key": "export-create",
            },
            format="json",
        )
        downloaded = authenticated_tenant_a_client.get(f"{BASE}/exports/{export.id}/download/")
        cancelled = authenticated_tenant_a_client.post(
            f"{BASE}/exports/{export.id}/cancel/",
            {"transition_key": "cancel-export", "reason": "operator"},
            format="json",
        )
        retried = authenticated_tenant_a_client.post(
            f"{BASE}/exports/{export.id}/retry/",
            {"transition_key": "retry-export", "idempotency_key": "export-retry"},
            format="json",
        )
        deleted = authenticated_tenant_a_client.delete(f"{BASE}/exports/{export.id}/")

    assert created.status_code == 202
    assert downloaded.status_code == 200
    assert b"".join(downloaded.streaming_content) == b"[]"
    assert downloaded["Content-Disposition"].endswith('filename="order_to_cash.json"')
    assert cancelled.status_code == 200
    assert retried.status_code == 202
    assert deleted.status_code == 204
    request_export.assert_called_once()
    open_download.assert_called_once()
    cancel_export.assert_called_once()
    retry_export.assert_called_once()
    delete_export.assert_called_once()


def test_discovery_model_endpoints_cover_success_transitions_and_missing_children(
    authenticated_tenant_a_client, tenant_a
):
    discovery = DiscoveryFactory(tenant_id=tenant_a.id, status=AnalysisStatus.COMPLETED)
    discovered_model = ModelFactory(tenant_id=tenant_a.id)
    discovered_version = VersionFactory(process_model=discovered_model)
    retry_job = DiscoveryFactory(
        tenant_id=tenant_a.id, process_name="order_to_cash_retry", idempotency_key="disc-retry"
    )

    with (
        patch.object(api.ProcessDiscoveryService, "request_discovery", return_value=discovery) as request_discovery,
        patch.object(api.ProcessDiscoveryService, "get_discovered_model", return_value=discovered_version),
        patch.object(api.ProcessDiscoveryService, "cancel_discovery", return_value=discovery) as cancel_discovery,
        patch.object(api.ProcessDiscoveryService, "retry_discovery", return_value=retry_job) as retry_discovery,
        patch.object(api.ProcessDiscoveryService, "delete_discovery") as delete_discovery,
    ):
        created = authenticated_tenant_a_client.post(
            f"{BASE}/discoveries/",
            {
                "process_name": "order_to_cash",
                "algorithm": "inductive_miner",
                "parameters": {"threshold": 0.8},
                "idempotency_key": "disc-create",
            },
            format="json",
        )
        model = authenticated_tenant_a_client.get(f"{BASE}/discoveries/{discovery.id}/model/")
        cancelled = authenticated_tenant_a_client.post(
            f"{BASE}/discoveries/{discovery.id}/cancel/", {"transition_key": "disc-cancel"}, format="json"
        )
        retried = authenticated_tenant_a_client.post(
            f"{BASE}/discoveries/{discovery.id}/retry/",
            {"transition_key": "disc-retry-key", "idempotency_key": "disc-retry"},
            format="json",
        )
        deleted = authenticated_tenant_a_client.delete(f"{BASE}/discoveries/{discovery.id}/")

    missing_model = authenticated_tenant_a_client.get(f"{BASE}/discoveries/{uuid.uuid4()}/model/")

    assert created.status_code == 202
    assert model.status_code == 200
    assert cancelled.status_code == 200
    assert retried.status_code == 202
    assert deleted.status_code == 204
    assert missing_model.status_code == 404
    request_discovery.assert_called_once()
    cancel_discovery.assert_called_once()
    retry_discovery.assert_called_once()
    delete_discovery.assert_called_once()


def test_model_update_versions_set_reference_delete_and_version_detail(authenticated_tenant_a_client, tenant_a):
    model = ModelFactory(tenant_id=tenant_a.id, name="Reference")
    version = VersionFactory(process_model=model)
    replacement = ModelFactory(tenant_id=tenant_a.id, name="Imported")
    updated = ModelFactory(tenant_id=tenant_a.id, name="Updated")

    with (
        patch.object(api.ProcessModelService, "create_imported_model", return_value=replacement) as create_imported,
        patch.object(api.ProcessModelService, "update_model_metadata", return_value=updated) as update_metadata,
        patch.object(api.ProcessModelService, "set_reference_version", return_value=version) as set_reference,
        patch.object(api.ProcessModelService, "soft_delete_model") as soft_delete,
    ):
        created = authenticated_tenant_a_client.post(
            f"{BASE}/models/",
            {"name": "Imported", "process_name": "order_to_cash", "description": "", "model_data": graph()},
            format="json",
        )
        patched = authenticated_tenant_a_client.patch(
            f"{BASE}/models/{model.id}/", {"description": "New"}, format="json"
        )
        versions = authenticated_tenant_a_client.get(f"{BASE}/models/{model.id}/versions/")
        referenced = authenticated_tenant_a_client.post(
            f"{BASE}/models/{model.id}/set-reference/",
            {"version_id": str(version.id), "transition_key": "set-ref"},
            format="json",
        )
        version_detail = authenticated_tenant_a_client.get(f"{BASE}/model-versions/{version.id}/")
        deleted = authenticated_tenant_a_client.delete(f"{BASE}/models/{model.id}/")

    assert created.status_code == 201
    assert patched.status_code == 200
    assert versions.status_code == 200 and versions.json()["data"][0]["id"] == str(version.id)
    assert referenced.status_code == 200
    assert version_detail.status_code == 200
    assert deleted.status_code == 204
    create_imported.assert_called_once()
    update_metadata.assert_called_once()
    set_reference.assert_called_once()
    soft_delete.assert_called_once()


def test_conformance_and_bottleneck_actions_delegate_and_paginate_children(authenticated_tenant_a_client, tenant_a):
    check = ConformanceFactory(tenant_id=tenant_a.id)
    deviation = DeviationFactory(conformance_check=check)
    case_metric = CaseMetricFactory(conformance_check=check)
    retried_check = ConformanceFactory(tenant_id=tenant_a.id, idempotency_key="conf-retry")
    analysis = AnalysisFactory(tenant_id=tenant_a.id)
    finding = FindingFactory(analysis=analysis)
    variant = VariantFactory(analysis=analysis)
    retried_analysis = AnalysisFactory(tenant_id=tenant_a.id, process_name="retry")

    with (
        patch.object(api.ConformanceService, "request_check", return_value=check) as request_check,
        patch.object(api.ConformanceService, "list_deviations", return_value=[deviation]) as list_deviations,
        patch.object(api.ConformanceService, "get_fitness", return_value=(check, [case_metric])) as get_fitness,
        patch.object(api.ConformanceService, "cancel_check", return_value=check) as cancel_check,
        patch.object(api.ConformanceService, "retry_check", return_value=retried_check) as retry_check,
        patch.object(api.ConformanceService, "delete_check") as delete_check,
        patch.object(api.BottleneckService, "request_analysis", return_value=analysis) as request_analysis,
        patch.object(api.BottleneckService, "get_findings", return_value=[finding]) as get_findings,
        patch.object(api.BottleneckService, "get_variants", return_value=[variant]) as get_variants,
        patch.object(api.BottleneckService, "cancel_analysis", return_value=analysis) as cancel_analysis,
        patch.object(api.BottleneckService, "retry_analysis", return_value=retried_analysis) as retry_analysis,
        patch.object(api.BottleneckService, "delete_analysis") as delete_analysis,
    ):
        conformance_created = authenticated_tenant_a_client.post(
            f"{BASE}/conformance-checks/",
            {"process_model_version_id": str(check.process_model_version_id), "idempotency_key": "conf-create"},
            format="json",
        )
        deviations = authenticated_tenant_a_client.get(f"{BASE}/conformance-checks/{check.id}/deviations/")
        fitness = authenticated_tenant_a_client.get(f"{BASE}/conformance-checks/{check.id}/fitness/")
        conformance_cancelled = authenticated_tenant_a_client.post(
            f"{BASE}/conformance-checks/{check.id}/cancel/", {"transition_key": "conf-cancel"}, format="json"
        )
        conformance_retried = authenticated_tenant_a_client.post(
            f"{BASE}/conformance-checks/{check.id}/retry/",
            {"transition_key": "conf-retry-key", "idempotency_key": "conf-retry"},
            format="json",
        )
        conformance_deleted = authenticated_tenant_a_client.delete(f"{BASE}/conformance-checks/{check.id}/")
        bottleneck_created = authenticated_tenant_a_client.post(
            f"{BASE}/bottleneck-analyses/",
            {
                "process_name": "order_to_cash",
                "time_range_start": analysis.time_range_start.isoformat(),
                "time_range_end": analysis.time_range_end.isoformat(),
                "idempotency_key": "analysis-create",
            },
            format="json",
        )
        findings = authenticated_tenant_a_client.get(f"{BASE}/bottleneck-analyses/{analysis.id}/findings/")
        variants = authenticated_tenant_a_client.get(f"{BASE}/bottleneck-analyses/{analysis.id}/variants/")
        bottleneck_cancelled = authenticated_tenant_a_client.post(
            f"{BASE}/bottleneck-analyses/{analysis.id}/cancel/", {"transition_key": "analysis-cancel"}, format="json"
        )
        bottleneck_retried = authenticated_tenant_a_client.post(
            f"{BASE}/bottleneck-analyses/{analysis.id}/retry/",
            {"transition_key": "analysis-retry-key", "idempotency_key": "analysis-retry"},
            format="json",
        )
        bottleneck_deleted = authenticated_tenant_a_client.delete(f"{BASE}/bottleneck-analyses/{analysis.id}/")

    assert conformance_created.status_code == 202
    assert deviations.status_code == 200 and deviations.json()["data"][0]["id"] == str(deviation.id)
    assert fitness.status_code == 200 and fitness.json()["data"][0]["id"] == str(case_metric.id)
    assert conformance_cancelled.status_code == 200
    assert conformance_retried.status_code == 202
    assert conformance_deleted.status_code == 204
    assert bottleneck_created.status_code == 202
    assert findings.status_code == 200 and findings.json()["data"][0]["id"] == str(finding.id)
    assert variants.status_code == 200 and variants.json()["data"][0]["id"] == str(variant.id)
    assert bottleneck_cancelled.status_code == 200
    assert bottleneck_retried.status_code == 202
    assert bottleneck_deleted.status_code == 204
    for mocked in (
        request_check,
        list_deviations,
        get_fitness,
        cancel_check,
        retry_check,
        delete_check,
        request_analysis,
        get_findings,
        get_variants,
        cancel_analysis,
        retry_analysis,
        delete_analysis,
    ):
        mocked.assert_called_once()


def test_configuration_api_current_update_preview_history_rollback_import_export_and_health(
    authenticated_tenant_a_client,
    tenant_a,
):
    document = {**DEFAULT_CONFIGURATION, "retention_days": DEFAULT_CONFIGURATION["retention_days"] + 1}

    current = authenticated_tenant_a_client.get(f"{BASE}/configuration/current/")
    preview = authenticated_tenant_a_client.post(
        f"{BASE}/configuration/preview/", {"document": document}, format="json"
    )
    updated = authenticated_tenant_a_client.put(f"{BASE}/configuration/update/", {"document": document}, format="json")
    history = authenticated_tenant_a_client.get(f"{BASE}/configuration/history/")
    exported = authenticated_tenant_a_client.get(f"{BASE}/configuration/export/")
    imported = authenticated_tenant_a_client.post(
        f"{BASE}/configuration/import/", {"configuration": exported.json()["data"]}, format="json"
    )
    rolled_back = authenticated_tenant_a_client.post(
        f"{BASE}/configuration/rollback/", {"version": current.json()["data"]["version"]}, format="json"
    )

    with patch.object(api, "get_module_health") as health:
        health.return_value = SimpleNamespace(
            payload={
                "status": "healthy",
                "live": True,
                "ready": True,
                "checked_at": "2026-07-21T08:00:00Z",
                "dependencies": [],
            },
            status_code=200,
        )
        health_view = api.ModuleHealthAPIView()
        health_request = SimpleNamespace(tenant_id=tenant_a.id)
        health_view.request = health_request
        health_response = health_view.get(health_request)

    assert current.status_code == 200
    assert preview.status_code == 200 and preview.json()["data"]["valid"] is True
    assert updated.status_code == 200
    assert history.status_code == 200 and history.json()["data"]
    assert exported.status_code == 200 and exported.json()["data"]["module"] == "process_mining"
    assert imported.status_code == 200
    assert rolled_back.status_code == 200
    assert health_response.status_code == 200
    health.assert_called_once_with(tenant_a.id)
