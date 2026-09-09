"""Branch-complete protected-endpoint authorization adapter tests."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.core.access import AccessDecision, AccessReasonCode, PolicyEvaluation
from src.core.access.permissions import RequiresAccess
from src.modules.security_access_control.api import GovernedSecurityViewSet
from src.modules.security_access_control.models import Permission, Role
from src.modules.security_access_control.permissions import (
    PermissionCatalogAccess,
    SecurityAdministrationPipeline,
    _identity_tenant,
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


def test_identity_tenant_reads_direct_attribute_uuid_and_string() -> None:
    tenant = uuid.uuid4()
    assert _identity_tenant(SimpleNamespace(tenant_id=tenant)) == tenant
    assert _identity_tenant(SimpleNamespace(tenant_id=str(tenant))) == tenant


def test_identity_tenant_falls_back_to_profile_when_direct_attribute_missing() -> None:
    tenant = uuid.uuid4()
    identity_with_profile_uuid = SimpleNamespace(tenant_id=None, profile=SimpleNamespace(tenant_id=tenant))
    assert _identity_tenant(identity_with_profile_uuid) == tenant
    identity_with_profile_str = SimpleNamespace(tenant_id=None, profile=SimpleNamespace(tenant_id=str(tenant)))
    assert _identity_tenant(identity_with_profile_str) == tenant


def test_identity_tenant_returns_none_when_no_tenant_available_anywhere() -> None:
    assert _identity_tenant(SimpleNamespace(tenant_id=None)) is None
    assert _identity_tenant(SimpleNamespace(tenant_id=None, profile=SimpleNamespace(tenant_id=None))) is None
    assert _identity_tenant(SimpleNamespace()) is None


def test_identity_tenant_returns_none_for_unparseable_value() -> None:
    assert _identity_tenant(SimpleNamespace(tenant_id="not-a-uuid")) is None
    assert _identity_tenant(SimpleNamespace(tenant_id=object())) is None


def test_pipeline_accepts_string_tenant_id_matching_string_identity_tenant() -> None:
    tenant = uuid.uuid4()
    principal = SimpleNamespace(id=uuid.uuid4(), tenant_id=str(tenant), is_authenticated=True, profile=None)
    result = SecurityAdministrationPipeline().decide(str(tenant), principal, None)
    assert not result.allowed and result.reason_code == AccessReasonCode.DENY_DEFAULT
    assert result.tenant_id == tenant


def test_pipeline_passes_exact_arguments_to_evaluation_service(monkeypatch) -> None:
    tenant = uuid.uuid4()
    principal = identity(tenant_id=tenant)
    captured: dict[str, object] = {}

    def fake_evaluate(tenant_arg, identity_arg, permission_arg, *, request=None):
        captured["tenant"] = tenant_arg
        captured["identity"] = identity_arg
        captured["permission"] = permission_arg
        captured["request"] = request
        return PolicyEvaluation(True, ("ALLOW",), ("policy-3",))

    monkeypatch.setattr(
        "src.modules.security_access_control.permissions.AccessEvaluationService.evaluate",
        fake_evaluate,
    )
    marker_request = SimpleNamespace(correlation_id="corr-exact")
    SecurityAdministrationPipeline().decide(tenant, principal, "security.roles:read", request=marker_request)
    assert captured == {
        "tenant": tenant,
        "identity": principal,
        "permission": "security.roles:read",
        "request": marker_request,
    }


def test_pipeline_defaults_request_to_none_when_not_provided(monkeypatch) -> None:
    tenant = uuid.uuid4()
    principal = identity(tenant_id=tenant)
    captured: dict[str, object] = {}

    def fake_evaluate(tenant_arg, identity_arg, permission_arg, *, request=None):
        captured["request"] = request
        return PolicyEvaluation(True, ("ALLOW",), ())

    monkeypatch.setattr(
        "src.modules.security_access_control.permissions.AccessEvaluationService.evaluate",
        fake_evaluate,
    )
    SecurityAdministrationPipeline().decide(tenant, principal, "security.roles:read")
    assert captured["request"] is None


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
    non_catalog = requires_access("security.roles:read")
    assert type(non_catalog) is RequiresAccess
    assert type(non_catalog) is not PermissionCatalogAccess
    assert non_catalog.required_permission == "security.roles:read"
    assert isinstance(non_catalog.pipeline, SecurityAdministrationPipeline)

    catalog = requires_access("security.permissions:read", catalog=True)
    assert type(catalog) is PermissionCatalogAccess
    assert catalog.required_permission == "security.permissions:read"
    assert isinstance(catalog.pipeline, SecurityAdministrationPipeline)

    default_catalog_flag = requires_access("security.roles:read")
    assert type(default_catalog_flag) is RequiresAccess


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
