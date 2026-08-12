"""Public v2 route and authentication contracts."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.urls import resolve
from rest_framework.exceptions import MethodNotAllowed, NotFound, PermissionDenied, ValidationError
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.core.licensing.models import Organization
from src.core.user_models import UserProfile
from src.modules.business_intelligence import api as bi_api
from src.modules.business_intelligence.models import Dashboard, DashboardShare, QueryExecution
from src.modules.business_intelligence.services import DashboardService

User = get_user_model()
PREFIX = "/api/v2/business-intelligence"


def query_payload(code: str = "API_QUERY") -> dict[str, object]:
    return {
        "query_code": code,
        "name": "API query",
        "dataset_key": "business_intelligence.execution_audit",
        "dimensions": ["status"],
        "measures": [{"key": "execution_count"}],
        "row_limit": 100,
    }


@pytest.fixture
def tenant_user(db):
    org = Organization.objects.create(name="BI API Tenant")
    user = User.objects.create_user(username="bi-api", email="bi-api@example.com", password="testpass123")
    profile = UserProfile.objects.get(user=user)
    profile.tenant_id = str(org.id)
    profile.tenant_role = "tenant_admin"
    profile.save()
    return User.objects.get(pk=user.pk)


@pytest.fixture
def authenticated_client(tenant_user):
    client = APIClient()
    client.force_authenticate(user=tenant_user)
    return client


@pytest.fixture(autouse=True)
def bypass_bi_policy_for_transport_tests(monkeypatch, request):
    if request.node.name == "test_protected_v2_collection_challenges_unauthenticated_clients":
        return
    monkeypatch.setattr(bi_api._BIViewMixin, "get_permissions", lambda self: [], raising=False)


def response_payload(response):
    payload = response.json()
    return payload.get("data", payload) if isinstance(payload, dict) else payload


@pytest.mark.django_db
def test_protected_v2_collection_challenges_unauthenticated_clients() -> None:
    response = APIClient().get("/api/v2/business-intelligence/queries/")
    assert response.status_code == 401
    assert "Session" in response.headers["WWW-Authenticate"]


@pytest.mark.django_db
def test_health_is_public_and_sanitized() -> None:
    response = APIClient().get("/api/v2/business-intelligence/health/")
    assert response.status_code in {200, 503}
    rendered = response.content.decode()
    assert "Traceback" not in rendered
    assert "password" not in rendered.lower()


def test_all_resource_routers_are_mounted_under_v2() -> None:
    for path in ("datasets/", "queries/", "reports/", "dashboards/", "executions/"):
        match = resolve(f"/api/v2/business-intelligence/{path}")
        assert match.url_name.endswith("-list")


def test_dataset_detail_route_preserves_dotted_catalog_keys() -> None:
    match = resolve("/api/v2/business-intelligence/datasets/business_intelligence.execution_audit/")

    assert match.url_name == "dataset-detail"
    assert match.kwargs["pk"] == "business_intelligence.execution_audit"


def test_legacy_v1_mount_is_removed() -> None:
    from django.urls import Resolver404

    with pytest.raises(Resolver404):
        resolve("/api/v1/business-intelligence/reports/")


@pytest.mark.django_db
def test_dataset_api_filters_orders_and_rejects_bad_query(authenticated_client, monkeypatch) -> None:
    rows = [
        {
            "key": "z.dataset",
            "module": "core",
            "label": "Zulu",
            "description": "Last",
            "version": "1",
            "dimensions": (),
            "measures": (),
            "locked": False,
        },
        {
            "key": "a.dataset",
            "module": "core",
            "label": "Alpha",
            "description": "First",
            "version": "1",
            "dimensions": (),
            "measures": (),
            "locked": False,
        },
    ]
    monkeypatch.setattr(bi_api.DatasetCatalogService, "list_datasets", lambda *args: rows)
    monkeypatch.setattr(bi_api.DatasetCatalogService, "get_dataset", lambda *args: rows[0])

    listed = authenticated_client.get(f"{PREFIX}/datasets/?ordering=label&search=a")
    assert listed.status_code == 200
    payload = response_payload(listed)
    values = payload.get("results", payload) if isinstance(payload, dict) else payload
    assert [item["label"] for item in values] == ["Alpha", "Zulu"]

    assert authenticated_client.get(f"{PREFIX}/datasets/?locked=sometimes").status_code == 400
    assert authenticated_client.get(f"{PREFIX}/datasets/?ordering=module").status_code == 400
    detail = authenticated_client.get(f"{PREFIX}/datasets/z.dataset/")
    assert detail.status_code == 200
    assert response_payload(detail)["key"] == "z.dataset"


@pytest.mark.django_db
def test_bi_view_mixin_fails_closed_for_invalid_tenant_and_idempotency(tenant_user) -> None:
    view = bi_api.QueryViewSet()
    view.request = SimpleNamespace(
        tenant_id="not-a-uuid",
        user=tenant_user,
        headers={"Idempotency-Key": "create-1"},
        query_params={},
        data={},
    )

    with pytest.raises(NotFound):
        _ = view.tenant_id
    assert view.actor_id == str(tenant_user.pk)
    assert view.idempotency_key() == "create-1"

    view.request.headers = {}
    with pytest.raises(ValidationError):
        view.idempotency_key()
    view.request.headers = {"Idempotency-Key": "x" * 256}
    with pytest.raises(ValidationError):
        view.idempotency_key()
    with pytest.raises(MethodNotAllowed):
        view.update(view.request)


@pytest.mark.django_db
def test_definition_and_execution_viewsets_reject_unsupported_filters(tenant_user) -> None:
    tenant_id = get_user_tenant_id(tenant_user)
    query_view = bi_api.QueryViewSet()
    query_view.request = SimpleNamespace(
        tenant_id=tenant_id,
        user=tenant_user,
        headers={},
        query_params={"ordering": "dataset_key"},
        data={},
    )

    with pytest.raises(ValidationError):
        query_view.get_queryset()

    report_view = bi_api.ReportViewSet()
    report_view.request = SimpleNamespace(
        tenant_id=tenant_id,
        user=tenant_user,
        headers={},
        query_params={"report_type": "spreadsheet"},
        data={},
    )
    with pytest.raises(ValidationError):
        report_view.get_queryset()

    execution_view = bi_api.ExecutionViewSet()
    execution_view.request = SimpleNamespace(
        tenant_id=tenant_id,
        user=tenant_user,
        headers={},
        query_params={"status": "complete"},
        data={},
    )
    with pytest.raises(ValidationError):
        execution_view.get_queryset()
    execution_view.request.query_params = {"query": "not-a-uuid"}
    with pytest.raises(ValidationError):
        execution_view.get_queryset()
    execution_view.request.query_params = {"created_from": "not-a-date"}
    with pytest.raises(ValidationError):
        execution_view.get_queryset()
    execution_view.request.query_params = {"ordering": "dataset_key"}
    with pytest.raises(ValidationError):
        execution_view.get_queryset()


@pytest.mark.django_db
def test_dashboard_queryset_enforces_owner_share_and_access_filters(tenant_user) -> None:
    tenant_id = get_user_tenant_id(tenant_user)
    actor_id = str(tenant_user.pk)
    owned = Dashboard.objects.create(
        tenant_id=tenant_id,
        dashboard_code="OWNED_DASH",
        dashboard_name="Owned dashboard",
        created_by_id=actor_id,
        updated_by_id=actor_id,
    )
    shared = Dashboard.objects.create(
        tenant_id=tenant_id,
        dashboard_code="SHARED_DASH",
        dashboard_name="Shared dashboard",
        created_by_id="owner",
        updated_by_id="owner",
    )
    hidden = Dashboard.objects.create(
        tenant_id=tenant_id,
        dashboard_code="HIDDEN_DASH",
        dashboard_name="Hidden dashboard",
        created_by_id="owner",
        updated_by_id="owner",
    )
    DashboardShare.objects.create(
        tenant_id=tenant_id,
        dashboard=shared,
        subject_type="user",
        subject_id=actor_id,
        access_level="edit",
        shared_by_id="owner",
    )

    view = bi_api.DashboardViewSet()
    view.action = "list"
    view.request = SimpleNamespace(tenant_id=tenant_id, user=tenant_user, query_params={}, headers={}, data={})

    assert set(view.get_queryset()) == {owned, shared}
    view.request.query_params = {"access": "owned"}
    assert list(view.get_queryset()) == [owned]
    view.request.query_params = {"access": "shared"}
    assert list(view.get_queryset()) == [shared]
    view.request.query_params = {"access": "public"}
    with pytest.raises(ValidationError):
        view.get_queryset()

    view.request.query_params = {}
    view.action = "partial_update"
    assert set(view.get_queryset()) == {owned, shared}
    view.action = "destroy"
    assert list(view.get_queryset()) == [owned]

    view._require_access(shared.id)
    with pytest.raises(PermissionDenied):
        view._require_access(shared.id, owner_only=True)
    with pytest.raises(PermissionDenied):
        view._require_access(hidden.id)
    with pytest.raises(NotFound):
        view._require_access(uuid.uuid4())


@pytest.mark.django_db
def test_query_report_dashboard_and_execution_api_workflow(authenticated_client, tenant_user) -> None:
    tenant_id = get_user_tenant_id(tenant_user)
    missing_key = authenticated_client.post(f"{PREFIX}/queries/", query_payload(), format="json")
    assert missing_key.status_code == 400

    created = authenticated_client.post(
        f"{PREFIX}/queries/",
        query_payload("API_QUERY_WORKFLOW"),
        format="json",
        HTTP_IDEMPOTENCY_KEY="query-api-create",
        HTTP_X_CORRELATION_ID=str(uuid.uuid4()),
    )
    assert created.status_code == 201, created.json()
    query = response_payload(created)
    query_id = query["id"]

    assert authenticated_client.get(f"{PREFIX}/queries/?state=invalid").status_code == 400
    listed = authenticated_client.get(f"{PREFIX}/queries/?ordering=query_code")
    assert listed.status_code == 200
    assert authenticated_client.get(f"{PREFIX}/queries/{query_id}/").status_code == 200

    stale = authenticated_client.patch(
        f"{PREFIX}/queries/{query_id}/",
        {"version": 99, "name": "stale"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="query-api-stale",
    )
    assert stale.status_code == 409
    updated = authenticated_client.patch(
        f"{PREFIX}/queries/{query_id}/",
        {"version": 1, "name": "API query updated"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="query-api-update",
    )
    assert updated.status_code == 200
    updated_payload = response_payload(updated)
    published = authenticated_client.post(
        f"{PREFIX}/queries/{query_id}/publish/",
        {"version": updated_payload["version"], "reason": "ready"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="query-api-publish",
    )
    assert published.status_code == 200
    assert response_payload(published)["state"] == "published"
    validate = authenticated_client.post(f"{PREFIX}/queries/{query_id}/validate/", {"parameters": {}}, format="json")
    assert response_payload(validate)["valid"]

    report = authenticated_client.post(
        f"{PREFIX}/reports/",
        {
            "report_code": "API_REPORT",
            "report_name": "API report",
            "report_type": "table",
            "query_definition_id": query_id,
            "visualization": {"type": "table"},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="report-api-create",
    )
    assert report.status_code == 201, report.json()
    report_payload = response_payload(report)
    report_id = report_payload["id"]
    report_published = authenticated_client.post(
        f"{PREFIX}/reports/{report_id}/publish/",
        {"version": report_payload["version"]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="report-api-publish",
    )
    assert report_published.status_code == 200
    assert (
        authenticated_client.get(f"{PREFIX}/reports/?dataset_key=business_intelligence.execution_audit").status_code
        == 200
    )

    dashboard = authenticated_client.post(
        f"{PREFIX}/dashboards/",
        {"dashboard_code": "API_DASH", "dashboard_name": "API dashboard"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="dash-api-create",
    )
    assert dashboard.status_code == 201, dashboard.json()
    dashboard_payload = response_payload(dashboard)
    dashboard_id = dashboard_payload["id"]
    widget = authenticated_client.post(
        f"{PREFIX}/dashboards/{dashboard_id}/widgets/",
        {
            "query_definition_id": query_id,
            "widget_type": "table",
            "title": "Status",
            "x": 0,
            "y": 0,
            "width": 6,
            "height": 4,
            "visualization": {"type": "table"},
            "filters": [],
            "display_order": 0,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="widget-api-create",
    )
    assert widget.status_code == 201, widget.json()
    widget_payload = response_payload(widget)
    widget_id = widget_payload["id"]
    assert authenticated_client.get(f"{PREFIX}/dashboards/{dashboard_id}/widgets/").status_code == 200
    patched_widget = authenticated_client.patch(
        f"{PREFIX}/dashboards/{dashboard_id}/widgets/{widget_id}/",
        {"version": widget_payload["version"], "title": "Status table"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="widget-api-update",
    )
    assert patched_widget.status_code == 200
    reordered = authenticated_client.post(
        f"{PREFIX}/dashboards/{dashboard_id}/widgets/reorder/",
        {
            "version": dashboard_payload["version"] + 2,
            "widgets": [{"id": widget_id, "x": 0, "y": 4, "width": 6, "height": 4}],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="widget-api-reorder",
    )
    assert reordered.status_code == 200, reordered.json()

    share = authenticated_client.post(
        f"{PREFIX}/dashboards/{dashboard_id}/shares/",
        {"subject_type": "user", "subject_id": "reader", "access_level": "view"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="share-api-create",
    )
    assert share.status_code == 201, share.json()
    share_payload = response_payload(share)
    share_id = share_payload["id"]
    assert authenticated_client.get(f"{PREFIX}/dashboards/{dashboard_id}/shares/").status_code == 200
    assert (
        authenticated_client.patch(
            f"{PREFIX}/dashboards/{dashboard_id}/shares/{share_id}/",
            {"access_level": "edit"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="share-api-update",
        ).status_code
        == 200
    )

    dashboard_current = DashboardService.publish(
        tenant_id,
        dashboard_id,
        str(tenant_user.id),
        response_payload(reordered)["version"],
        "correlation",
        "dash-service-publish",
    )
    execution = DashboardService.enqueue_execution(
        tenant_id,
        dashboard_current.id,
        str(tenant_user.id),
        {},
        "correlation",
        "dash-service-exec",
    )[0]
    QueryExecution.objects.filter(pk=execution.id).update(
        status="succeeded",
        result_columns=[{"key": "status"}],
        result_rows=[{"status": "queued"}],
        row_count=1,
    )
    assert authenticated_client.get(f"{PREFIX}/executions/?status=succeeded").status_code == 200
    assert authenticated_client.get(f"{PREFIX}/executions/{execution.id}/").status_code == 200
    assert authenticated_client.get(f"{PREFIX}/executions/{execution.id}/result/").status_code == 200
    assert (
        authenticated_client.post(
            f"{PREFIX}/executions/{execution.id}/cancel/",
            HTTP_IDEMPOTENCY_KEY="execution-api-cancel",
        ).status_code
        == 200
    )

    assert (
        authenticated_client.delete(
            f"{PREFIX}/dashboards/{dashboard_id}/shares/{share_id}/",
            HTTP_IDEMPOTENCY_KEY="share-api-delete",
        ).status_code
        == 204
    )
    assert (
        authenticated_client.delete(
            f"{PREFIX}/dashboards/{dashboard_id}/widgets/{widget_id}/",
            HTTP_IDEMPOTENCY_KEY="widget-api-delete",
        ).status_code
        == 204
    )
