"""Action permission declarations and fail-closed access semantics."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import Mock

from rest_framework.permissions import IsAuthenticated
from rest_framework.test import APIRequestFactory

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.core.access.permissions import RequiresAccess
from src.modules.document_intelligence.permissions import PERMISSIONS, ActionAccessMixin, SessionAuthentication401

EXPECTED_PERMISSIONS = {
    "document_intelligence.extraction:read",
    "document_intelligence.extraction:create",
    "document_intelligence.extraction:cancel",
    "document_intelligence.extraction:retry",
    "document_intelligence.extraction:delete",
    "document_intelligence.classification:read",
    "document_intelligence.classification:create",
    "document_intelligence.classification:review",
    "document_intelligence.classification:cancel",
    "document_intelligence.classification:retry",
    "document_intelligence.classification:delete",
    "document_intelligence.template:read",
    "document_intelligence.template:create",
    "document_intelligence.template:update",
    "document_intelligence.template:delete",
    "document_intelligence.template:activate",
    "document_intelligence.training:read",
    "document_intelligence.training:create",
    "document_intelligence.training:cancel",
    "document_intelligence.training:retry",
    "document_intelligence.model:read",
    "document_intelligence.model:activate",
    "document_intelligence.model:rollback",
    "document_intelligence.configuration:read",
    "document_intelligence.configuration:update",
    "document_intelligence.health:read",
}


def test_manifest_permission_surface_is_exact_and_has_no_legacy_resource_actions() -> None:
    assert set(PERMISSIONS) == EXPECTED_PERMISSIONS
    assert len(PERMISSIONS) == len(set(PERMISSIONS))
    assert not any(".resource:" in permission for permission in PERMISSIONS)


def test_session_authentication_is_csrf_enforcing_and_advertises_401() -> None:
    authentication = SessionAuthentication401()
    assert authentication.authenticate_header(object()) == "Session"
    assert SessionAuthentication401.__mro__[1].__name__ == "SessionAuthentication"


def test_action_access_mixin_selects_action_permission_and_bounded_quota() -> None:
    view = ActionAccessMixin()
    view.action = "create"
    view.action_permissions = {"create": "document_intelligence.template:create"}
    view.action_quotas = {"create": "document_intelligence.api_writes"}
    view.request = SimpleNamespace(user=SimpleNamespace(tenant_id=uuid.uuid4()))

    permissions = view.get_permissions()

    assert view.required_permission == "document_intelligence.template:create"
    assert view.required_entitlement == "document_intelligence.template:create"
    assert view.quota_resource == "document_intelligence.api_writes"
    assert [type(item).__name__ for item in permissions] == ["IsAuthenticated", "RequiresAccess"]


def test_missing_action_metadata_fails_closed_before_pipeline_call() -> None:
    request = APIRequestFactory().get("/")
    request.user = SimpleNamespace(is_authenticated=True)
    pipeline = Mock()

    allowed = RequiresAccess(pipeline=pipeline).has_permission(request, SimpleNamespace())

    assert allowed is False
    assert request.access_decision.reason_code == AccessReasonCode.DENY_DEFAULT
    pipeline.decide.assert_not_called()


def test_exactly_once_access_decision_is_reused_for_object_tenant_check() -> None:
    tenant_id = uuid.uuid4()
    request = APIRequestFactory().post("/", {}, format="json")
    request.user = SimpleNamespace(is_authenticated=True)
    request.tenant_id = tenant_id
    decision = AccessDecision(
        allowed=True,
        reason_code=AccessReasonCode.ALLOW,
        reason="Explicit policy, entitlement, and quota allow",
        tenant_id=tenant_id,
        remaining_quota=9,
    )
    pipeline = Mock()
    pipeline.decide.return_value = decision
    permission = RequiresAccess(pipeline=pipeline)
    view = SimpleNamespace(
        required_permission="document_intelligence.extraction:create",
        required_entitlement="document_intelligence.extraction:create",
        quota_resource="document_intelligence.processing_requests",
        quota_cost=1,
    )

    assert permission.has_permission(request, view) is True
    assert permission.has_object_permission(request, view, SimpleNamespace(tenant_id=tenant_id)) is True
    assert permission.has_object_permission(request, view, SimpleNamespace(tenant_id=uuid.uuid4())) is False
    pipeline.decide.assert_called_once()


def test_get_permissions_defaults_action_to_empty_string_when_unset() -> None:
    view = ActionAccessMixin()
    view.request = SimpleNamespace(user=SimpleNamespace())

    view.get_permissions()

    assert view.required_permission is None
    assert view.required_entitlement is None
    assert view.quota_resource == "document_intelligence.api_writes"


def test_get_permissions_leaves_tenant_id_unset_when_user_has_no_tenant() -> None:
    view = ActionAccessMixin()
    view.action = "list"
    request = SimpleNamespace(user=SimpleNamespace())
    view.request = request

    view.get_permissions()

    assert not hasattr(request, "tenant_id")


def test_get_permissions_converts_valid_tenant_id_string_to_uuid() -> None:
    tenant_id = uuid.uuid4()
    view = ActionAccessMixin()
    view.action = "list"
    view.request = SimpleNamespace(user=SimpleNamespace(profile=SimpleNamespace(tenant_id=str(tenant_id))))

    view.get_permissions()

    assert view.request.tenant_id == tenant_id


def test_get_permissions_fails_closed_to_none_on_invalid_tenant_id() -> None:
    view = ActionAccessMixin()
    view.action = "list"
    view.request = SimpleNamespace(user=SimpleNamespace(profile=SimpleNamespace(tenant_id="not-a-uuid")))

    view.get_permissions()

    assert view.request.tenant_id is None


def test_quota_resource_defaults_to_reads_for_every_declared_read_action() -> None:
    for action in ("list", "retrieve", "pages", "scores"):
        view = ActionAccessMixin()
        view.action = action
        view.request = SimpleNamespace(user=SimpleNamespace())

        view.get_permissions()

        assert view.quota_resource == "document_intelligence.api_reads", action


def test_quota_resource_defaults_to_writes_for_non_read_actions() -> None:
    for action in ("create", "update", "partial_update", "destroy", "cancel", "retry"):
        view = ActionAccessMixin()
        view.action = action
        view.request = SimpleNamespace(user=SimpleNamespace())

        view.get_permissions()

        assert view.quota_resource == "document_intelligence.api_writes", action


def test_required_permission_and_entitlement_are_none_when_action_unmapped() -> None:
    view = ActionAccessMixin()
    view.action = "update"
    view.action_permissions = {}
    view.request = SimpleNamespace(user=SimpleNamespace())

    view.get_permissions()

    assert view.required_permission is None
    assert view.required_entitlement is None


def test_get_permissions_returns_is_authenticated_then_requires_access_instances() -> None:
    view = ActionAccessMixin()
    view.action = "list"
    view.request = SimpleNamespace(user=SimpleNamespace())

    permissions = view.get_permissions()

    assert isinstance(permissions[0], IsAuthenticated)
    assert isinstance(permissions[1], RequiresAccess)
    assert len(permissions) == 2


def test_action_access_mixin_class_attributes_are_wired_for_fail_closed_access() -> None:
    assert ActionAccessMixin.authentication_classes == (SessionAuthentication401,)
    assert ActionAccessMixin.permission_classes == (IsAuthenticated, RequiresAccess)


def test_dependency_and_quota_denials_remain_machine_distinguishable() -> None:
    tenant_id = uuid.uuid4()
    for reason in (AccessReasonCode.QUOTA_EXCEEDED, AccessReasonCode.DEPENDENCY_UNAVAILABLE):
        request = APIRequestFactory().get("/")
        request.user = SimpleNamespace(is_authenticated=True)
        request.tenant_id = tenant_id
        pipeline = Mock()
        pipeline.decide.return_value = AccessDecision.deny(reason, "Safe denial", tenant_id=tenant_id)
        permission = RequiresAccess(pipeline=pipeline)

        assert (
            permission.has_permission(request, SimpleNamespace(required_permission="document_intelligence.health:read"))
            is False
        )
        assert request.access_decision.reason_code == reason
