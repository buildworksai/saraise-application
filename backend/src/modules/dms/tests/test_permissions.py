"""Complete evidence for the DMS deny-by-default route boundary."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.authentication import SessionAuthentication

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.core.access.permissions import RequiresAccess
from src.modules.dms import permissions as permission_contract
from src.modules.dms.permissions import (
    ActionAccessMixin,
    DOCUMENT_ACTION_PERMISSIONS,
    DOCUMENT_PERMISSION_ACTION_PERMISSIONS,
    FOLDER_ACTION_PERMISSIONS,
    HEALTH_ACTION_PERMISSIONS,
    PERMISSIONS,
    PERMISSION_QUOTAS,
    PRINCIPAL_ACTION_PERMISSIONS,
    SHARE_ACTION_PERMISSIONS,
    VERSION_ACTION_PERMISSIONS,
    SessionAuthentication401,
)

pytest_plugins = ["src.core.testing"]


def test_permission_catalog_exactly_matches_v2_manifest_contract() -> None:
    expected = {
        "dms.folder:read",
        "dms.folder:create",
        "dms.folder:update",
        "dms.folder:delete",
        "dms.document:read",
        "dms.document:create",
        "dms.document:update",
        "dms.document:move",
        "dms.document:download",
        "dms.document:delete",
        "dms.version:read",
        "dms.version:create",
        "dms.version:restore",
        "dms.permission:read",
        "dms.permission:grant",
        "dms.permission:update",
        "dms.permission:revoke",
        "dms.share:read",
        "dms.share:create",
        "dms.share:revoke",
        "dms.health:read",
    }
    assert set(PERMISSIONS) == expected
    assert len(PERMISSIONS) == len(expected)
    assert all("resource:" not in permission for permission in PERMISSIONS)


def test_all_declared_actions_map_to_manifest_permissions_and_explicit_quotas() -> None:
    maps = (
        FOLDER_ACTION_PERMISSIONS,
        DOCUMENT_ACTION_PERMISSIONS,
        VERSION_ACTION_PERMISSIONS,
        DOCUMENT_PERMISSION_ACTION_PERMISSIONS,
        SHARE_ACTION_PERMISSIONS,
        HEALTH_ACTION_PERMISSIONS,
        PRINCIPAL_ACTION_PERMISSIONS,
    )
    declared = {permission for action_map in maps for permission in action_map.values()}
    assert declared == set(PERMISSIONS)
    assert set(PERMISSION_QUOTAS) == set(PERMISSIONS)
    assert set(PERMISSION_QUOTAS.values()) == {"dms.api_reads", "dms.api_writes"}


def test_strict_session_authentication_never_uses_relaxed_csrf() -> None:
    assert issubclass(SessionAuthentication401, SessionAuthentication)
    assert ActionAccessMixin.authentication_classes == (SessionAuthentication401,)
    assert all(
        authentication.__name__ != "RelaxedCsrfSessionAuthentication"
        for authentication in ActionAccessMixin.authentication_classes
    )


class _View(ActionAccessMixin):
    action_permissions = {"list": "dms.document:read"}


def test_authenticated_profile_is_the_only_tenant_source(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    spoofed = uuid.uuid4()
    view = _View()
    view.action = "list"
    view.request = SimpleNamespace(
        tenant_id=spoofed,
        headers={"X-Tenant-ID": str(spoofed)},
        data={"tenant_id": str(spoofed)},
        user=SimpleNamespace(profile=SimpleNamespace(tenant_id=str(tenant_id))),
    )
    monkeypatch.setattr(permission_contract, "RequiresAccess", lambda: object())
    view.get_permissions()
    assert view.request.tenant_id == tenant_id
    assert view.required_permission == "dms.document:read"
    assert view.required_entitlement == "dms.document:read"
    assert view.quota_resource == "dms.api_reads"


def test_invalid_profile_tenant_clears_any_injected_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    view = _View()
    view.action = "list"
    view.request = SimpleNamespace(
        tenant_id=uuid.uuid4(),
        user=SimpleNamespace(profile=SimpleNamespace(tenant_id="not-a-uuid")),
    )
    monkeypatch.setattr(permission_contract, "RequiresAccess", lambda: object())
    view.get_permissions()
    assert view.request.tenant_id is None


def test_undeclared_action_retains_no_access_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    view = _View()
    view.action = "put"
    view.request = SimpleNamespace(
        user=SimpleNamespace(profile=SimpleNamespace(tenant_id=str(uuid.uuid4()))),
    )
    monkeypatch.setattr(permission_contract, "RequiresAccess", lambda: object())
    view.get_permissions()
    assert view.required_permission is None
    assert view.required_entitlement is None
    assert view.quota_resource is None


class _Pipeline:
    def __init__(self, decision: AccessDecision) -> None:
        self.decision = decision

    def decide(self, *args: object, **kwargs: object) -> AccessDecision:
        del args, kwargs
        return self.decision


@pytest.mark.parametrize(
    "reason",
    [
        AccessReasonCode.DENY_DEFAULT,
        AccessReasonCode.POLICY_CONFIG_MISSING,
        AccessReasonCode.ENGINE_TIMEOUT,
        AccessReasonCode.ENGINE_UNAVAILABLE,
        AccessReasonCode.ENTITLEMENT_REQUIRED,
        AccessReasonCode.QUOTA_EXCEEDED,
        AccessReasonCode.DEPENDENCY_UNAVAILABLE,
    ],
)
def test_policy_entitlement_quota_timeout_and_circuit_failures_deny(reason: AccessReasonCode) -> None:
    decision = AccessDecision.deny(reason, "sanitized denial")
    permission = RequiresAccess(pipeline=_Pipeline(decision))
    request = SimpleNamespace(tenant_id=uuid.uuid4(), user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
    view = SimpleNamespace(
        required_permission="dms.document:read",
        required_entitlement="dms.document:read",
        quota_resource="dms.api_reads",
        quota_cost=1,
    )
    assert permission.has_permission(request, view) is False
    assert request.access_decision.reason_code == reason


def test_requires_access_denies_missing_action_mapping_without_calling_pipeline() -> None:
    class FailingPipeline:
        def decide(self, *args: object, **kwargs: object) -> AccessDecision:
            raise AssertionError("pipeline must not run without a permission declaration")

    permission = RequiresAccess(pipeline=FailingPipeline())
    request = SimpleNamespace(tenant_id=uuid.uuid4(), user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
    assert permission.has_permission(request, SimpleNamespace(required_permission=None)) is False
    assert request.access_decision.reason_code == AccessReasonCode.DENY_DEFAULT


def test_object_boundary_requires_prior_allow_and_matching_tenant() -> None:
    tenant_id = uuid.uuid4()
    permission = RequiresAccess(pipeline=_Pipeline(AccessDecision.deny(AccessReasonCode.DENY_DEFAULT, "deny")))
    allowed = AccessDecision(
        allowed=True,
        reason_code=AccessReasonCode.ALLOW,
        reason="allowed",
        tenant_id=tenant_id,
    )
    request = SimpleNamespace(access_decision=allowed)
    assert permission.has_object_permission(request, object(), SimpleNamespace(tenant_id=tenant_id)) is True
    assert permission.has_object_permission(request, object(), SimpleNamespace(tenant_id=uuid.uuid4())) is False
    assert permission.has_object_permission(request, object(), SimpleNamespace()) is False
    request.access_decision = AccessDecision.deny(AccessReasonCode.POLICY_DENIED, "deny", tenant_id=tenant_id)
    assert permission.has_object_permission(request, object(), SimpleNamespace(tenant_id=tenant_id)) is False
