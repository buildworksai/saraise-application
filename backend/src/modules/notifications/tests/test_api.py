"""Governed API contract tests using real sessions, grants, and quotas."""

import copy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.urls import resolve
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.test import APIRequestFactory

from src.core.access.decision import PolicyEvaluation
from src.core.access.entitlements import Entitlement, Quota
from src.modules.notifications.api import (
    ConfigurationAPIView,
    ConfigurationExportAPIView,
    ConfigurationHistoryAPIView,
    ConfigurationImportAPIView,
    ConfigurationRollbackAPIView,
    ConfigurationSimulateAPIView,
    Conflict,
    DeliveryViewSet,
    EndpointViewSet,
    InboxViewSet,
    LivenessAPIView,
    PreferenceAPIView,
    PreferenceResetAPIView,
    ProviderCallbackAPIView,
    ReadinessAPIView,
    ServiceUnavailable,
    TemplateViewSet,
    _pk,
    _preference_matrix,
    _translate,
)
from src.modules.notifications.models import NotificationDelivery, NotificationPreference
from src.modules.notifications.services import (
    CapabilityUnavailable,
    NotificationConfigurationService,
    NotificationDispatchService,
    NotificationPreferenceService,
    NotificationService,
    NotificationServiceError,
)
from src.modules.security_access_control.services import SecurityPolicyEvaluator


def _request(method, path, data=None):
    factory = APIRequestFactory()
    builder = getattr(factory, method)
    return builder(path, data=data, format="json")


def _bind_view(view, request, tenant_id, actor_id):
    if isinstance(view, (InboxViewSet, TemplateViewSet, DeliveryViewSet, EndpointViewSet)):
        view.action_map = {request.method.lower(): request.method.lower()}
    view.request = view.initialize_request(request)
    view.args = ()
    view.kwargs = {}
    view._identity = lambda: (tenant_id, actor_id)
    return view.request


def _bound(view, method, path, tenant_id, actor_id, data=None):
    request = _request(method, path, data)
    _bind_view(view, request, tenant_id, actor_id)
    return view


def _allow_policy_engine(monkeypatch, settings):
    """Allow policy without bypassing entitlement and quota checks."""

    settings.SARAISE_POLICY_ENGINE_URL = "https://policy.example.test"
    calls = []

    def evaluate(self, tenant_id, identity, required_permission, request=None):
        del self
        calls.append(
            (
                "local",
                {
                    "tenant_id": str(tenant_id),
                    "actor_id": str(getattr(identity, "id", "")),
                    "action": required_permission,
                    "path": getattr(request, "path", ""),
                },
                None,
            )
        )
        return PolicyEvaluation(
            allowed=True,
            reason_codes=("TEST_POLICY_ALLOW",),
            applied_policies=("notifications-test-policy",),
        )

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

    monkeypatch.setattr(SecurityPolicyEvaluator, "evaluate", evaluate)
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
def test_entitlement_denial_occurs_after_real_policy_allow(authenticated_tenant_a_client, monkeypatch, settings):
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
    assert calls[0][0] == "local"
    assert calls[0][1]["action"] == "notifications.inbox:read"
    assert Quota.objects.get(tenant_id=tenant_a.id, resource="notifications.api_reads").remaining == 9


@pytest.mark.django_db
def test_invalid_filter_has_stable_error_envelope(authenticated_tenant_a_client, tenant_a, monkeypatch, settings):
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
    response = client.post(
        "/api/v2/notifications/inbox/mark-all-read/", {"transition_key": "csrf-proof"}, format="json"
    )
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
        (
            f"/api/v2/notifications/templates/{uuid4()}/",
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"},
        ),
        (f"/api/v2/notifications/templates/{uuid4()}/versions/", {"get": "versions", "post": "versions"}),
        (f"/api/v2/notifications/templates/{uuid4()}/activate/", {"post": "activate"}),
        ("/api/v2/notifications/deliveries/", {"get": "list", "post": "create"}),
        ("/api/v2/notifications/deliveries/bulk/", {"post": "bulk"}),
        (f"/api/v2/notifications/deliveries/{uuid4()}/attempts/", {"get": "attempts"}),
        ("/api/v2/notifications/endpoints/", {"get": "list", "post": "create"}),
        (
            f"/api/v2/notifications/endpoints/{uuid4()}/",
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"},
        ),
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


def test_missing_pk_is_translated_to_not_found():
    identifier = uuid4()

    assert _pk(identifier) == identifier
    with pytest.raises(NotFound, match="Resource not found"):
        _pk(None)


def test_route_action_metadata_is_not_mutated_by_drf_head_expansion():
    view = InboxViewSet.as_view({"get": "list"})

    assert view.actions == {"get": "list"}


def test_identity_and_permission_mapping_fail_closed(monkeypatch):
    user = SimpleNamespace(is_authenticated=True)
    view = TemplateViewSet()
    view.request = SimpleNamespace(user=user, method="POST")
    view.action = "versions"

    monkeypatch.setattr("src.modules.notifications.api.get_user_tenant_id", lambda request_user: None)
    with pytest.raises(PermissionDenied, match="tenant context is required"):
        view._identity()

    monkeypatch.setattr("src.modules.notifications.api.get_user_tenant_id", lambda request_user: "not-a-uuid")
    with pytest.raises(PermissionDenied, match="tenant context is invalid"):
        view._identity()

    tenant_id = uuid4()
    monkeypatch.setattr("src.modules.notifications.api.get_user_tenant_id", lambda request_user: tenant_id)
    monkeypatch.setattr("src.modules.notifications.api.get_user_id", lambda request_user: "actor")

    permissions = view.get_permissions()

    assert len(permissions) == 2
    assert view.required_permission == "notifications.template:update"
    assert view.required_entitlement == "notifications.template:update"
    assert view.quota_resource == "notifications.api_writes"


@pytest.mark.parametrize(
    ("exc", "api_exc"),
    [
        (NotificationDelivery.DoesNotExist(), NotFound),
        (CapabilityUnavailable("Provider is disabled."), ServiceUnavailable),
        (NotificationServiceError("CONFLICT", "Version conflict."), Conflict),
        (NotificationServiceError("NOT_FOUND", "Missing."), NotFound),
        (NotificationServiceError("CONFIGURATION_MISSING", "Configuration missing."), ServiceUnavailable),
        (NotificationServiceError("VALIDATION_ERROR", "Bad input.", errors={"channel": "invalid"}), ValidationError),
    ],
)
def test_domain_errors_translate_to_stable_api_exceptions(exc, api_exc):
    with pytest.raises(api_exc):
        _translate(exc)


def test_unhandled_exception_is_not_swallowed():
    exc = RuntimeError("unexpected")

    with pytest.raises(RuntimeError, match="unexpected"):
        _translate(exc)


def test_invoke_translates_domain_errors():
    view = InboxViewSet()

    with pytest.raises(Conflict):
        view._invoke(lambda: (_ for _ in ()).throw(NotificationServiceError("ILLEGAL_TRANSITION", "Bad state.")))


@pytest.mark.django_db
def test_preference_matrix_merges_persisted_preferences_with_effective_defaults(tenant_a, monkeypatch):
    user_id = uuid4()
    NotificationPreference.objects.create(
        tenant_id=tenant_a.id,
        user_id=user_id,
        channel="email",
        category="general",
        enabled=False,
        digest_mode="daily",
        timezone="America/New_York",
    )

    def effective(tenant_id, effective_user_id, channel, category):
        assert tenant_id == tenant_a.id
        assert effective_user_id == user_id
        return {
            "enabled": channel == "in_app",
            "digest_mode": "immediate",
            "quiet_hours_start": None,
            "quiet_hours_end": None,
            "timezone": "UTC",
            "is_default": True,
        }

    monkeypatch.setattr(NotificationPreferenceService, "get_effective", effective)

    matrix = _preference_matrix(tenant_a.id, user_id)

    assert matrix["channels"] == ["email", "in_app", "push", "sms", "webhook"]
    assert matrix["categories"] == ["general", "password_reset", "security_alerts"]
    persisted = next(
        item for item in matrix["preferences"] if item["channel"] == "email" and item["category"] == "general"
    )
    mandatory = next(
        item for item in matrix["preferences"] if item["channel"] == "sms" and item["category"] == "password_reset"
    )
    assert persisted["enabled"] is False
    assert persisted["digest_mode"] == "daily"
    assert persisted["source"] == "override"
    assert mandatory["mandatory"] is True
    assert mandatory["source"] == "mandatory_policy"


@pytest.mark.django_db
def test_configuration_api_lifecycle_conflict_history_import_export_and_simulation(tenant_a):
    actor_id = uuid4()
    get_view = ConfigurationAPIView()
    get_request = _request("get", "/api/v2/notifications/configuration/development/")
    _bind_view(get_view, get_request, tenant_a.id, actor_id)

    created = get_view.get(get_view.request, "development")
    document = copy.deepcopy(created.data["document"])
    document["batch_size"] = 12

    patch_view = ConfigurationAPIView()
    patch_request = _request(
        "patch",
        "/api/v2/notifications/configuration/development/",
        {"document": document, "change_summary": "Bound notification batches", "expected_version": 1},
    )
    _bind_view(patch_view, patch_request, tenant_a.id, actor_id)

    updated = patch_view.patch(patch_view.request, "development")

    assert updated.data["active_version"] == 2
    assert updated.data["document"]["batch_size"] == 12

    stale_patch = ConfigurationAPIView()
    stale_request = _request(
        "patch",
        "/api/v2/notifications/configuration/development/",
        {"document": document, "reason": "Stale operator update", "expected_version": 1},
    )
    _bind_view(stale_patch, stale_request, tenant_a.id, actor_id)
    with pytest.raises(Conflict):
        stale_patch.patch(stale_patch.request, "development")

    simulate_view = ConfigurationSimulateAPIView()
    simulate_request = _request(
        "post",
        "/api/v2/notifications/configuration/development/simulate/",
        {"document": document, "scenario": {"channel": "in_app"}},
    )
    _bind_view(simulate_view, simulate_request, tenant_a.id, actor_id)
    simulation = simulate_view.post(simulate_view.request, "development")
    assert simulation.data["decision"] == "dispatch"

    history_view = ConfigurationHistoryAPIView()
    history_request = _request("get", "/api/v2/notifications/configuration/development/history/")
    _bind_view(history_view, history_request, tenant_a.id, actor_id)
    history = history_view.get(history_view.request, "development")
    assert history.data[0]["audit"]["action"] == "update"

    export_view = ConfigurationExportAPIView()
    export_request = _request("get", "/api/v2/notifications/configuration/development/export/")
    _bind_view(export_view, export_request, tenant_a.id, actor_id)
    exported = export_view.get(export_view.request, "development")
    assert exported["Content-Disposition"] == 'attachment; filename="notifications-development.json"'
    assert exported.data["configuration"]["batch_size"] == 12

    dry_import = ConfigurationImportAPIView()
    dry_import_request = _request(
        "post",
        "/api/v2/notifications/configuration/development/import/",
        {"document": {"configuration": document}, "dry_run": True, "expected_version": 2},
    )
    _bind_view(dry_import, dry_import_request, tenant_a.id, actor_id)
    dry_result = dry_import.post(dry_import.request, "development")
    assert dry_result.data["valid"] is True
    assert dry_result.data["would_write"] is False

    rollback_view = ConfigurationRollbackAPIView()
    rollback_request = _request(
        "post",
        "/api/v2/notifications/configuration/development/rollback/",
        {"target_version": 1, "change_summary": "Restore baseline", "expected_version": 2},
    )
    _bind_view(rollback_view, rollback_request, tenant_a.id, actor_id)
    rolled_back = rollback_view.post(rollback_view.request, "development")
    assert rolled_back.data["active_version"] == 3
    assert rolled_back.data["document"]["batch_size"] == 100


@pytest.mark.django_db
def test_template_viewset_lifecycle_uses_governed_services(tenant_a):
    actor_id = uuid4()
    template_payload = {
        "code": "invoice_ready",
        "name": "Invoice ready",
        "category": "workflow",
        "channel": "in_app",
        "locale": "en",
        "subject_template": "Invoice {{ invoice_id }}",
        "body_template": "Invoice {{ invoice_id }} is ready",
        "variables_schema": {"invoice_id": {"required": True}},
        "content_type": "text/plain",
        "idempotency_key": "template-create-api",
    }
    create_view = _bound(
        TemplateViewSet(),
        "post",
        "/api/v2/notifications/templates/",
        tenant_a.id,
        actor_id,
        template_payload,
    )
    created = create_view.create(create_view.request)
    template_id = created.data["id"]

    list_view = _bound(TemplateViewSet(), "get", "/api/v2/notifications/templates/", tenant_a.id, actor_id)
    assert list_view.list(list_view.request).data[0]["code"] == "invoice_ready"

    retrieve_view = _bound(
        TemplateViewSet(),
        "get",
        f"/api/v2/notifications/templates/{template_id}/",
        tenant_a.id,
        actor_id,
    )
    assert retrieve_view.retrieve(retrieve_view.request, template_id).data["latest_version"]["version"] == 1

    missing_key_payload = {**template_payload, "code": "missing_key"}
    missing_key_payload.pop("idempotency_key")
    missing_key_view = _bound(
        TemplateViewSet(),
        "post",
        "/api/v2/notifications/templates/",
        tenant_a.id,
        actor_id,
        missing_key_payload,
    )
    with pytest.raises(ValidationError) as exc:
        missing_key_view.create(missing_key_view.request)
    assert exc.value.detail["idempotency_key"] == "X-Idempotency-Key is required."

    version_post_view = _bound(
        TemplateViewSet(),
        "post",
        f"/api/v2/notifications/templates/{template_id}/versions/",
        tenant_a.id,
        actor_id,
        {"body_template": "Invoice {{ invoice_id }} has been approved", "name": "Invoice approved"},
    )
    version_two = version_post_view.versions(version_post_view.request, template_id)
    assert version_two.status_code == status.HTTP_201_CREATED
    assert version_two.data["version"] == 2

    versions_view = _bound(
        TemplateViewSet(),
        "get",
        f"/api/v2/notifications/templates/{template_id}/versions/",
        tenant_a.id,
        actor_id,
    )
    assert [item["version"] for item in versions_view.versions(versions_view.request, template_id).data] == [2, 1]

    preview_draft_view = _bound(
        TemplateViewSet(),
        "post",
        "/api/v2/notifications/templates/preview-draft/",
        tenant_a.id,
        actor_id,
        {
            "draft": {
                "subject_template": "Invoice {{ invoice_id }}",
                "body_template": "Draft {{ invoice_id }}",
                "variables_schema": {"invoice_id": {"required": True}},
            },
            "context": {"invoice_id": "INV-1"},
        },
    )
    assert preview_draft_view.preview_draft(preview_draft_view.request).data["valid"] is True

    activate_view = _bound(
        TemplateViewSet(),
        "post",
        f"/api/v2/notifications/templates/{template_id}/activate/",
        tenant_a.id,
        actor_id,
        {"version": 2, "transition_key": "activate-v2"},
    )
    activated = activate_view.activate(activate_view.request, template_id)
    assert activated.data["status"] == "active"
    assert activated.data["active_version"]["version"] == 2

    preview_view = _bound(
        TemplateViewSet(),
        "post",
        f"/api/v2/notifications/templates/{template_id}/preview/",
        tenant_a.id,
        actor_id,
        {"context": {"invoice_id": "INV-2"}},
    )
    assert "INV-2" in preview_view.preview(preview_view.request, template_id).data["body"]

    rollback_view = _bound(
        TemplateViewSet(),
        "post",
        f"/api/v2/notifications/templates/{template_id}/rollback/",
        tenant_a.id,
        actor_id,
        {"version": 1, "transition_key": "rollback-v1"},
    )
    assert rollback_view.rollback(rollback_view.request, template_id).data["active_version"]["version"] == 1

    destroy_view = _bound(
        TemplateViewSet(),
        "delete",
        f"/api/v2/notifications/templates/{template_id}/",
        tenant_a.id,
        actor_id,
        {"transition_key": "archive-template"},
    )
    assert destroy_view.destroy(destroy_view.request, template_id).data["status"] == "archived"

    restore_view = _bound(
        TemplateViewSet(),
        "post",
        f"/api/v2/notifications/templates/{template_id}/restore/",
        tenant_a.id,
        actor_id,
        {"transition_key": "restore-template"},
    )
    restored = restore_view.restore(restore_view.request, template_id)
    assert restored.data["status"] == "draft"
    assert restored.data["active_version"] is None


def test_delivery_viewset_dispatch_actions_delegate_validated_payloads(monkeypatch):
    tenant_id = uuid4()
    actor_id = uuid4()
    delivery_id = uuid4()
    service_calls = []

    class DummySerializer:
        def __init__(self, instance=None, many=False):
            self.instance = instance
            self.many = many

        @property
        def data(self):
            if self.many:
                return [{"id": str(item.id), "status": item.status} for item in self.instance]
            return {"id": str(self.instance.id), "status": self.instance.status}

    delivery = SimpleNamespace(id=delivery_id, status="queued")
    result = SimpleNamespace(object=delivery)

    monkeypatch.setattr("src.modules.notifications.api.DeliveryDetailSerializer", DummySerializer)
    monkeypatch.setattr("src.modules.notifications.api.DeliveryListSerializer", DummySerializer)

    def capture(name, return_value):
        def handler(*args):
            service_calls.append((name, args))
            return return_value

        return handler

    monkeypatch.setattr(NotificationDispatchService, "enqueue", capture("enqueue", result))
    monkeypatch.setattr(NotificationDispatchService, "enqueue_bulk", capture("bulk", [result]))
    monkeypatch.setattr(NotificationDispatchService, "preview_dispatch", capture("preview", {"will_dispatch": True}))
    monkeypatch.setattr(NotificationDispatchService, "retry", capture("retry", result))
    monkeypatch.setattr(NotificationDispatchService, "cancel", capture("cancel", delivery))
    monkeypatch.setattr(NotificationDispatchService, "confirm_delivery", capture("confirm", delivery))

    base_payload = {
        "template_id": str(uuid4()),
        "recipient_type": "email",
        "recipient": "owner@example.test",
        "context": {},
        "idempotency_key": "delivery-create",
    }
    create_view = _bound(
        DeliveryViewSet(),
        "post",
        "/api/v2/notifications/deliveries/",
        tenant_id,
        actor_id,
        base_payload,
    )
    assert create_view.create(create_view.request).status_code == status.HTTP_202_ACCEPTED

    urgent_view = _bound(
        DeliveryViewSet(),
        "post",
        "/api/v2/notifications/deliveries/urgent/",
        tenant_id,
        actor_id,
        {**base_payload, "idempotency_key": "delivery-urgent"},
    )
    assert urgent_view.urgent(urgent_view.request).status_code == status.HTTP_202_ACCEPTED

    bulk_view = _bound(
        DeliveryViewSet(),
        "post",
        "/api/v2/notifications/deliveries/bulk/",
        tenant_id,
        actor_id,
        {"requests": [{k: v for k, v in base_payload.items() if k != "idempotency_key"}], "idempotency_key": "bulk"},
    )
    assert bulk_view.bulk(bulk_view.request).status_code == status.HTTP_202_ACCEPTED

    preview_view = _bound(
        DeliveryViewSet(),
        "post",
        "/api/v2/notifications/deliveries/preview/",
        tenant_id,
        actor_id,
        {k: v for k, v in base_payload.items() if k != "idempotency_key"},
    )
    assert preview_view.preview(preview_view.request).data == {"will_dispatch": True}

    retry_view = _bound(
        DeliveryViewSet(),
        "post",
        f"/api/v2/notifications/deliveries/{delivery_id}/retry/",
        tenant_id,
        actor_id,
        {"idempotency_key": "retry"},
    )
    assert retry_view.retry(retry_view.request, delivery_id).status_code == status.HTTP_202_ACCEPTED

    cancel_view = _bound(
        DeliveryViewSet(),
        "post",
        f"/api/v2/notifications/deliveries/{delivery_id}/cancel/",
        tenant_id,
        actor_id,
        {"transition_key": "cancel"},
    )
    assert cancel_view.cancel(cancel_view.request, delivery_id).data["status"] == "queued"

    confirm_view = _bound(
        DeliveryViewSet(),
        "post",
        f"/api/v2/notifications/deliveries/{delivery_id}/confirm/",
        tenant_id,
        actor_id,
        {"provider_message_id": "provider-1", "signature_verified": True, "idempotency_key": "confirm"},
    )
    assert confirm_view.confirm(confirm_view.request, delivery_id).data["id"] == str(delivery_id)

    urgent_call = next(args for name, args in service_calls if name == "enqueue" and args[3] == "delivery-urgent")
    assert urgent_call[2]["priority"] == 1
    assert urgent_call[2]["urgent_authorized"] is True
    assert [name for name, _ in service_calls] == [
        "enqueue",
        "enqueue",
        "bulk",
        "preview",
        "retry",
        "cancel",
        "confirm",
    ]


@pytest.mark.django_db
def test_api_adapters_exercise_inbox_preferences_endpoints_health_and_callbacks(tenant_a, monkeypatch):
    actor_id = uuid4()
    NotificationConfigurationService.get_or_create_default(tenant_a.id, "development", actor_id)
    notification = NotificationService.create_notification(tenant_a.id, actor_id, "Notice", "Read me")

    inbox = _bound(
        InboxViewSet(),
        "get",
        "/api/v2/notifications/inbox/",
        tenant_a.id,
        actor_id,
    )
    inbox_page = inbox.list(inbox.request)
    assert inbox_page.data[0]["id"] == str(notification.id)

    inbox_detail = _bound(
        InboxViewSet(),
        "get",
        f"/api/v2/notifications/inbox/{notification.id}/",
        tenant_a.id,
        actor_id,
    )
    assert inbox_detail.retrieve(inbox_detail.request, notification.id).data["title"] == "Notice"

    mark_read = _bound(
        InboxViewSet(),
        "post",
        f"/api/v2/notifications/inbox/{notification.id}/mark-read/",
        tenant_a.id,
        actor_id,
        {"transition_key": "api-read"},
    )
    assert mark_read.mark_read(mark_read.request, notification.id).data["status"] == "read"

    mark_unread = _bound(
        InboxViewSet(),
        "post",
        f"/api/v2/notifications/inbox/{notification.id}/mark-unread/",
        tenant_a.id,
        actor_id,
        {"transition_key": "api-unread"},
    )
    assert mark_unread.mark_unread(mark_unread.request, notification.id).data["status"] == "unread"

    mark_all = _bound(
        InboxViewSet(),
        "post",
        "/api/v2/notifications/inbox/mark-all-read/",
        tenant_a.id,
        actor_id,
        {"transition_key": "api-all"},
    )
    assert mark_all.mark_all_read(mark_all.request).data == {"affected_count": 1}

    count_view = _bound(
        InboxViewSet(),
        "get",
        "/api/v2/notifications/inbox/unread-count/",
        tenant_a.id,
        actor_id,
    )
    assert count_view.unread_count(count_view.request).data == {"count": 0}

    archive = _bound(
        InboxViewSet(),
        "post",
        f"/api/v2/notifications/inbox/{notification.id}/archive/",
        tenant_a.id,
        actor_id,
        {"transition_key": "api-archive"},
    )
    assert archive.archive(archive.request, notification.id).data["status"] == "archived"

    preferences = _bound(
        PreferenceAPIView(),
        "get",
        "/api/v2/notifications/preferences/me/",
        tenant_a.id,
        actor_id,
    )
    assert preferences.get(preferences.request).data["channels"]

    replace_preferences = _bound(
        PreferenceAPIView(),
        "put",
        "/api/v2/notifications/preferences/me/",
        tenant_a.id,
        actor_id,
        {"preferences": [{"channel": "email", "category": "workflow", "enabled": False, "digest_mode": "daily"}]},
    )
    replaced = replace_preferences.put(replace_preferences.request)
    assert any(row["channel"] == "email" and row["source"] == "override" for row in replaced.data["preferences"])

    reset_preferences = _bound(
        PreferenceResetAPIView(),
        "post",
        "/api/v2/notifications/preferences/me/reset/",
        tenant_a.id,
        actor_id,
    )
    assert reset_preferences.post(reset_preferences.request).data["preferences"]

    endpoint_create = _bound(
        EndpointViewSet(),
        "post",
        "/api/v2/notifications/endpoints/",
        tenant_a.id,
        actor_id,
        {"kind": "push", "device_type": "web", "address": "device-token", "display_name": "Browser"},
    )
    endpoint_data = endpoint_create.create(endpoint_create.request).data

    endpoint_list = _bound(
        EndpointViewSet(),
        "get",
        "/api/v2/notifications/endpoints/",
        tenant_a.id,
        actor_id,
    )
    assert endpoint_list.list(endpoint_list.request).data[0]["display_name"] == "Browser"

    endpoint_update = _bound(
        EndpointViewSet(),
        "patch",
        f"/api/v2/notifications/endpoints/{endpoint_data['id']}/",
        tenant_a.id,
        actor_id,
        {"display_name": "Work browser", "is_active": True},
    )
    assert (
        endpoint_update.partial_update(endpoint_update.request, endpoint_data["id"]).data["display_name"]
        == "Work browser"
    )

    endpoint_rotate = _bound(
        EndpointViewSet(),
        "post",
        f"/api/v2/notifications/endpoints/{endpoint_data['id']}/rotate-secret/",
        tenant_a.id,
        actor_id,
        {"secret_ref": "vault://notifications/push-token"},  # pragma: allowlist secret
    )
    assert endpoint_rotate.rotate_secret(endpoint_rotate.request, endpoint_data["id"]).data["secret_ref"] == (
        "vault://notifications/push-token"
    )

    endpoint_detail = _bound(
        EndpointViewSet(),
        "get",
        f"/api/v2/notifications/endpoints/{endpoint_data['id']}/",
        tenant_a.id,
        actor_id,
    )
    assert endpoint_detail.retrieve(endpoint_detail.request, endpoint_data["id"]).data["id"] == endpoint_data["id"]

    endpoint_destroy = _bound(
        EndpointViewSet(),
        "delete",
        f"/api/v2/notifications/endpoints/{endpoint_data['id']}/",
        tenant_a.id,
        actor_id,
    )
    assert endpoint_destroy.destroy(endpoint_destroy.request, endpoint_data["id"]).data["is_active"] is False

    assert LivenessAPIView().get(_request("get", "/api/v2/notifications/health/live/")).data["status"] == "live"

    monkeypatch.setattr("src.modules.notifications.api.readiness", lambda tenant_id: ({"status": "ready"}, 200))
    readiness_view = _bound(
        ReadinessAPIView(),
        "get",
        "/api/v2/notifications/health/ready/",
        tenant_a.id,
        actor_id,
    )
    assert readiness_view.get(readiness_view.request).status_code == 200

    monkeypatch.setattr(
        "src.modules.notifications.api.NotificationProviderCallbackService.accept",
        lambda callback_key, headers, body: {"accepted": True, "replayed": False, "callback_key": callback_key},
    )
    callback_view = ProviderCallbackAPIView()
    callback_request = _request("post", "/api/v2/notifications/provider-callbacks/provider-a/", {"accepted": True})
    callback_view.request = callback_view.initialize_request(callback_request)
    callback = callback_view.post(callback_view.request, "provider-a")
    assert callback.status_code == status.HTTP_202_ACCEPTED
    assert callback.data["callback_key"] == "provider-a"


def test_provider_callback_replay_and_domain_error_translation(monkeypatch):
    monkeypatch.setattr(
        "src.modules.notifications.api.NotificationProviderCallbackService.accept",
        lambda callback_key, headers, body: {"accepted": True, "replayed": True, "callback_key": callback_key},
    )
    replay_view = ProviderCallbackAPIView()
    replay_request = _request("post", "/api/v2/notifications/provider-callbacks/provider-a/", {"accepted": True})
    replay_view.request = replay_view.initialize_request(replay_request)
    replay = replay_view.post(replay_view.request, "provider-a")
    assert replay.status_code == status.HTTP_200_OK

    def reject(callback_key, headers, body):
        raise NotificationServiceError("CALLBACK_NOT_FOUND", "Callback not found.")

    monkeypatch.setattr("src.modules.notifications.api.NotificationProviderCallbackService.accept", reject)
    error_view = ProviderCallbackAPIView()
    error_request = _request("post", "/api/v2/notifications/provider-callbacks/missing/", {"accepted": True})
    error_view.request = error_view.initialize_request(error_request)
    with pytest.raises(NotFound):
        error_view.post(error_view.request, "missing")
