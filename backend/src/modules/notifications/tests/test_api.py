"""Governed API contract tests using real sessions, grants, and quotas."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.urls import resolve
from rest_framework import status

from src.core.access.entitlements import Entitlement, Quota
from src.modules.notifications.api import (
    ConfigurationAPIView,
    ConfigurationExportAPIView,
    ConfigurationHistoryAPIView,
    ConfigurationImportAPIView,
    ConfigurationRollbackAPIView,
    ConfigurationSimulateAPIView,
    DeliveryViewSet,
    EndpointViewSet,
    InboxViewSet,
    PreferenceAPIView,
    PreferenceResetAPIView,
    ReadinessAPIView,
    TemplateViewSet,
)


def _allow_policy_engine(monkeypatch, settings):
    """Allow policy over the real HTTP evaluator without bypassing the pipeline."""

    settings.SARAISE_POLICY_ENGINE_URL = "https://policy.example.test"
    calls = []

    def post(url, *, json, timeout):
        calls.append((url, json, timeout))
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "decision": "allow",
                "reason_codes": ["TEST_POLICY_ALLOW"],
                "applied_policies": ["notifications-test-policy"],
            },
        )

    monkeypatch.setattr("src.core.access.decision.requests.post", post)
    return calls


def _grant(tenant_id, capability, quota_resource, *, remaining=10):
    Entitlement.objects.create(tenant_id=tenant_id, capability=capability)
    Quota.objects.create(
        tenant_id=tenant_id,
        resource=quota_resource,
        limit=remaining,
        remaining=remaining,
    )


@pytest.mark.django_db
def test_missing_policy_entitlement_and_quota_fail_closed(authenticated_tenant_a_client):
    response = authenticated_tenant_a_client.get("/api/v2/notifications/inbox/")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert b"tenant_id" not in response.content


@pytest.mark.django_db
def test_entitlement_denial_occurs_after_real_policy_allow(
    authenticated_tenant_a_client, monkeypatch, settings
):
    calls = _allow_policy_engine(monkeypatch, settings)

    response = authenticated_tenant_a_client.get("/api/v2/notifications/inbox/")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "POLICY_DENIED"
    assert calls[0][1]["action"] == "notifications.inbox:read"


@pytest.mark.django_db
def test_quota_denial_occurs_after_real_policy_and_entitlement(
    authenticated_tenant_a_client, tenant_a, monkeypatch, settings
):
    _allow_policy_engine(monkeypatch, settings)
    Entitlement.objects.create(tenant_id=tenant_a.id, capability="notifications.inbox:read")

    response = authenticated_tenant_a_client.get("/api/v2/notifications/inbox/")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "POLICY_DENIED"


@pytest.mark.django_db
def test_governed_collection_envelope_and_bounded_pagination(
    authenticated_tenant_a_client, tenant_a, monkeypatch, settings
):
    calls = _allow_policy_engine(monkeypatch, settings)
    _grant(tenant_a.id, "notifications.inbox:read", "notifications.api_reads")

    response = authenticated_tenant_a_client.get("/api/v2/notifications/inbox/?page_size=999")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"] == []
    assert response.json()["meta"]["pagination"] == {
        "count": 0,
        "page": 1,
        "page_size": 100,
        "total_pages": 0,
        "has_next": False,
        "has_previous": False,
    }
    assert response.json()["meta"]["correlation_id"]
    assert response.json()["meta"]["timestamp"].endswith("Z")
    assert calls[0][0] == "https://policy.example.test/api/v1/evaluate"
    assert calls[0][2] == 2.0
    assert Quota.objects.get(tenant_id=tenant_a.id, resource="notifications.api_reads").remaining == 9


@pytest.mark.django_db
def test_invalid_filter_has_stable_error_envelope(
    authenticated_tenant_a_client, tenant_a, monkeypatch, settings
):
    _allow_policy_engine(monkeypatch, settings)
    _grant(tenant_a.id, "notifications.inbox:read", "notifications.api_reads")

    response = authenticated_tenant_a_client.get("/api/v2/notifications/inbox/?status=deleted")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    payload = response.json()["error"]
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["detail"]["status"] == "Value is not allowed."
    assert payload["correlation_id"]


@pytest.mark.django_db
def test_unauthenticated_request_is_rejected(api_client):
    response = api_client.get("/api/v2/notifications/inbox/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_unsafe_request_without_csrf_is_rejected(tenant_a_user):
    from rest_framework.test import APIClient
    from src.core.testing import TEST_PASSWORD

    client = APIClient(enforce_csrf_checks=True)
    assert client.login(username=tenant_a_user.username, password=TEST_PASSWORD)
    response = client.post("/api/v2/notifications/inbox/mark-all-read/", {"transition_key": "csrf-proof"}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.parametrize(
    ("path", "methods"),
    [
        ("/api/v2/notifications/inbox/", {"get": "list"}),
        (f"/api/v2/notifications/inbox/{uuid4()}/", {"get": "retrieve"}),
        (f"/api/v2/notifications/inbox/{uuid4()}/mark-read/", {"post": "mark_read"}),
        ("/api/v2/notifications/inbox/mark-all-read/", {"post": "mark_all_read"}),
        ("/api/v2/notifications/inbox/unread-count/", {"get": "unread_count"}),
        ("/api/v2/notifications/templates/", {"get": "list", "post": "create"}),
        (f"/api/v2/notifications/templates/{uuid4()}/", {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        (f"/api/v2/notifications/templates/{uuid4()}/versions/", {"get": "versions", "post": "versions"}),
        (f"/api/v2/notifications/templates/{uuid4()}/activate/", {"post": "activate"}),
        ("/api/v2/notifications/deliveries/", {"get": "list", "post": "create"}),
        ("/api/v2/notifications/deliveries/bulk/", {"post": "bulk"}),
        (f"/api/v2/notifications/deliveries/{uuid4()}/attempts/", {"get": "attempts"}),
        ("/api/v2/notifications/endpoints/", {"get": "list", "post": "create"}),
        (f"/api/v2/notifications/endpoints/{uuid4()}/", {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
    ],
)
def test_router_path_method_contract(path, methods):
    assert resolve(path).func.actions == methods


@pytest.mark.parametrize(
    ("path", "view_class"),
    [
        ("/api/v2/notifications/preferences/me/", PreferenceAPIView),
        ("/api/v2/notifications/preferences/me/reset/", PreferenceResetAPIView),
        ("/api/v2/notifications/configuration/development/", ConfigurationAPIView),
        ("/api/v2/notifications/configuration/development/simulate/", ConfigurationSimulateAPIView),
        ("/api/v2/notifications/configuration/development/history/", ConfigurationHistoryAPIView),
        ("/api/v2/notifications/configuration/development/rollback/", ConfigurationRollbackAPIView),
        ("/api/v2/notifications/configuration/development/import/", ConfigurationImportAPIView),
        ("/api/v2/notifications/configuration/development/export/", ConfigurationExportAPIView),
        ("/api/v2/notifications/health/ready/", ReadinessAPIView),
    ],
)
def test_api_view_route_contract(path, view_class):
    assert resolve(path).func.view_class is view_class


def test_action_specific_permission_mappings_are_complete():
    assert InboxViewSet.action_permissions == {
        "list": "notifications.inbox:read",
        "retrieve": "notifications.inbox:read",
        "mark_read": "notifications.inbox:update",
        "mark_unread": "notifications.inbox:update",
        "archive": "notifications.inbox:update",
        "mark_all_read": "notifications.inbox:update",
        "unread_count": "notifications.inbox:read",
    }
    assert TemplateViewSet.action_permissions["versions"] == "notifications.template:read"
    assert TemplateViewSet.action_permissions["versions_post"] == "notifications.template:update"
    assert DeliveryViewSet.action_entitlements == {
        "create": "notifications.delivery",
        "urgent": "notifications.delivery",
        "bulk": "notifications.delivery",
        "preview": "notifications.delivery",
        "retry": "notifications.delivery",
        "cancel": "notifications.delivery",
    }
    assert DeliveryViewSet.action_quotas == {
        "bulk": "notifications.delivery.dispatch_bulk",
        "urgent": "notifications.delivery.dispatch_urgent",
    }
    assert EndpointViewSet.action_permissions["rotate_secret"] == "notifications.endpoint:update"
    assert ConfigurationRollbackAPIView.action_permissions["post"] == "notifications.configuration:rollback"
