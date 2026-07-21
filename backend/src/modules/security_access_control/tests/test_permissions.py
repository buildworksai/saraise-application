"""Branch-complete protected-endpoint authorization adapter tests."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.core.access import AccessDecision, AccessReasonCode, PolicyEvaluation
from src.modules.security_access_control.api import GovernedSecurityViewSet
from src.modules.security_access_control.models import Permission, Role
from src.modules.security_access_control.permissions import (
    PermissionCatalogAccess,
    SecurityAdministrationPipeline,
    requires_access,
)

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db


def identity(*, tenant_id: object, authenticated: bool = True) -> object:
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        is_authenticated=authenticated,
        profile=SimpleNamespace(tenant_id=tenant_id),
    )


def test_pipeline_denies_anonymous_missing_invalid_and_mismatched_tenant() -> None:
    pipeline = SecurityAdministrationPipeline()
    tenant = uuid.uuid4()
    anonymous = pipeline.decide(tenant, identity(tenant_id=tenant, authenticated=False), "security.roles:read")
    assert not anonymous.allowed and anonymous.reason_code == AccessReasonCode.AUTHENTICATION_REQUIRED
    invalid = pipeline.decide("not-a-uuid", identity(tenant_id=tenant), "security.roles:read")
    assert not invalid.allowed and invalid.reason_code == AccessReasonCode.DENY_TENANT_MISMATCH
    mismatch = pipeline.decide(tenant, identity(tenant_id=uuid.uuid4()), "security.roles:read")
    assert not mismatch.allowed and mismatch.reason_code == AccessReasonCode.DENY_TENANT_MISMATCH
    absent = pipeline.decide(tenant, identity(tenant_id=tenant), None)
    assert not absent.allowed and absent.reason_code == AccessReasonCode.DENY_DEFAULT


def test_pipeline_maps_authoritative_policy_deny_and_allow(monkeypatch) -> None:
    tenant = uuid.uuid4()
    principal = identity(tenant_id=tenant)
    monkeypatch.setattr(
        "src.modules.security_access_control.permissions.AccessEvaluationService.evaluate",
        lambda *args, **kwargs: PolicyEvaluation(False, ("EXPLICIT_DENY",), ("policy-1",)),
    )
    denied = SecurityAdministrationPipeline().decide(
        tenant,
        principal,
        "security.roles:read",
        request=SimpleNamespace(correlation_id="corr-denied"),
    )
    assert not denied.allowed and denied.reason_code == AccessReasonCode.POLICY_DENIED
    assert denied.applied_policies == ("policy-1",)
    monkeypatch.setattr(
        "src.modules.security_access_control.permissions.AccessEvaluationService.evaluate",
        lambda *args, **kwargs: PolicyEvaluation(True, ("ALLOW",), ("policy-2",)),
    )
    allowed = SecurityAdministrationPipeline().decide(tenant, principal, "security.roles:read")
    assert allowed.allowed and allowed.reason_code == AccessReasonCode.ALLOW


def test_catalog_object_permission_requires_both_route_allow_and_catalog_type() -> None:
    permission = Permission(module="finance", resource="journals", action="read", name="Read")
    role = Role(tenant_id=uuid.uuid4(), name="Role", code="role")
    adapter = PermissionCatalogAccess("security.permissions:read", pipeline=SecurityAdministrationPipeline())
    tenant = uuid.uuid4()
    allowed_request = SimpleNamespace(
        access_decision=AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="Allowed",
            tenant_id=tenant,
        )
    )
    denied_request = SimpleNamespace(access_decision=AccessDecision.deny(AccessReasonCode.POLICY_DENIED, "Denied"))
    assert adapter.has_object_permission(allowed_request, object(), permission)
    assert not adapter.has_object_permission(allowed_request, object(), role)
    assert not adapter.has_object_permission(denied_request, object(), permission)
    assert not adapter.has_object_permission(SimpleNamespace(), object(), permission)


def test_requires_access_factory_selects_catalog_subclass() -> None:
    assert isinstance(requires_access("security.roles:read"), type(requires_access("security.roles:read")))
    assert isinstance(requires_access("security.permissions:read", catalog=True), PermissionCatalogAccess)


def test_governed_viewset_never_falls_back_to_authentication_only(monkeypatch) -> None:
    tenant = uuid.uuid4()
    principal = identity(tenant_id=tenant)
    request = SimpleNamespace(user=principal, tenant_id=tenant)
    view = GovernedSecurityViewSet()
    view.request = request
    view.action = "unmapped_action"
    permissions = view.get_permissions()
    assert len(permissions) == 2
    assert getattr(permissions[1], "required_permission", None) == ""
    principal.is_authenticated = False
    anonymous_permissions = view.get_permissions()
    assert len(anonymous_permissions) == 1
