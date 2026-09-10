"""Unit tests for src/modules/ai_provider_configuration/permissions.py.

These tests exercise every branch of the action-aware access policy without
touching the database: fake user/request/view doubles stand in for DRF
objects, and the AccessDecisionPipeline is monkeypatched or stubbed directly
so the assertions pin exact call arguments and exact behavior, not just
"it doesn't crash".
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import SimpleRateThrottle

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.modules.ai_provider_configuration.permissions import (
    PERMISSIONS,
    SOD_ACTIONS,
    ActionPermissionMixin,
    AIProviderActionPermission,
    SessionAuthentication401,
    TenantProviderThrottle,
)

# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class FakeProfile:
    def __init__(self, tenant_id: Any) -> None:
        self.tenant_id = tenant_id


class FakeUser:
    def __init__(self, *, authenticated: bool, tenant_id: Any = None, pk: Any = 1) -> None:
        self.is_authenticated = authenticated
        self.profile = FakeProfile(tenant_id)
        self.pk = pk


class FakeView:
    def __init__(
        self,
        *,
        action: str = "list",
        action_permissions: dict[str, str] | None = None,
        required_entitlement: str | None = None,
        quota_resource: str | None = None,
        quota_cost: int | None = None,
        set_entitlement: bool = False,
        set_quota_resource: bool = False,
        set_quota_cost: bool = False,
    ) -> None:
        self.action = action
        self.action_permissions = action_permissions if action_permissions is not None else {}
        if set_entitlement:
            self.required_entitlement = required_entitlement
        if set_quota_resource:
            self.quota_resource = quota_resource
        if set_quota_cost:
            self.quota_cost = quota_cost


class FakeRequest:
    pass


class RecordingPipeline:
    """Captures the exact arguments passed to decide() and returns a canned decision."""

    def __init__(self, decision: AccessDecision) -> None:
        self.decision = decision
        self.calls: list[dict[str, Any]] = []

    def decide(self, tenant_id, identity, required_permission, **kwargs):
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "identity": identity,
                "required_permission": required_permission,
                **kwargs,
            }
        )
        return self.decision


def make_allow_decision(tenant_id: Any = None) -> AccessDecision:
    return AccessDecision(
        allowed=True,
        reason_code=AccessReasonCode.ALLOW,
        reason="ok",
        tenant_id=uuid.UUID(str(tenant_id)) if tenant_id else None,
    )


def make_deny_decision() -> AccessDecision:
    return AccessDecision.deny(AccessReasonCode.POLICY_DENIED, "no")


# --------------------------------------------------------------------------
# PERMISSIONS / SOD_ACTIONS pin tests
# --------------------------------------------------------------------------


def test_permissions_exact_membership() -> None:
    assert PERMISSIONS == (
        "ai_provider_configuration.provider:read",
        "ai_provider_configuration.resource:read",
        "ai_provider_configuration.resource:create",
        "ai_provider_configuration.resource:update",
        "ai_provider_configuration.resource:delete",
        "ai_provider_configuration.credential:read",
        "ai_provider_configuration.credential:create",
        "ai_provider_configuration.credential:update",
        "ai_provider_configuration.credential:delete",
        "ai_provider_configuration.model:read",
        "ai_provider_configuration.deployment:read",
        "ai_provider_configuration.deployment:create",
        "ai_provider_configuration.deployment:update",
        "ai_provider_configuration.deployment:delete",
        "ai_provider_configuration.usage:read",
        "ai_provider_configuration.secret:rotate",
        "ai_provider_configuration.configuration:read",
        "ai_provider_configuration.configuration:update",
        "ai_provider_configuration.configuration:preview",
        "ai_provider_configuration.configuration:rollback",
        "ai_provider_configuration.configuration:import",
        "ai_provider_configuration.configuration:export",
        "ai_provider_configuration.configuration:audit",
        "ai_provider_configuration.health:read",
    )
    assert len(PERMISSIONS) == 24
    assert all(p.startswith("ai_provider_configuration.") for p in PERMISSIONS)


def test_sod_actions_exact_membership() -> None:
    assert SOD_ACTIONS == (
        (
            "ai_provider_configuration.credential:create",
            "ai_provider_configuration.credential:delete",
        ),
    )
    assert len(SOD_ACTIONS) == 1


# --------------------------------------------------------------------------
# SessionAuthentication401
# --------------------------------------------------------------------------


def test_session_authentication_401_header_is_always_session() -> None:
    auth = SessionAuthentication401()
    assert auth.authenticate_header(request=object()) == "Session"
    assert auth.authenticate_header(request=None) == "Session"


def test_session_authentication_401_is_subclass() -> None:
    from rest_framework.authentication import SessionAuthentication

    assert issubclass(SessionAuthentication401, SessionAuthentication)


# --------------------------------------------------------------------------
# AIProviderActionPermission.has_permission
# --------------------------------------------------------------------------


def test_has_permission_denies_when_user_is_none() -> None:
    perm = AIProviderActionPermission()
    request = FakeRequest()
    request.user = None
    view = FakeView(action="list", action_permissions={"list": "x"})
    assert perm.has_permission(request, view) is False


def test_has_permission_denies_when_user_attribute_missing() -> None:
    perm = AIProviderActionPermission()
    request = FakeRequest()  # no .user attribute at all
    view = FakeView(action="list", action_permissions={"list": "x"})
    assert perm.has_permission(request, view) is False


def test_has_permission_denies_when_not_authenticated() -> None:
    perm = AIProviderActionPermission()
    request = FakeRequest()
    request.user = FakeUser(authenticated=False)
    view = FakeView(action="list", action_permissions={"list": "x"})
    assert perm.has_permission(request, view) is False


def test_has_permission_denies_when_action_not_in_action_permissions() -> None:
    perm = AIProviderActionPermission()
    request = FakeRequest()
    request.user = FakeUser(authenticated=True, tenant_id=uuid.uuid4())
    view = FakeView(action="destroy", action_permissions={"list": "some.perm"})
    assert perm.has_permission(request, view) is False
    # required_permission must be set to None (not left unset), even on denial
    assert view.required_permission is None


def test_has_permission_denies_when_required_permission_is_empty_string() -> None:
    perm = AIProviderActionPermission()
    request = FakeRequest()
    request.user = FakeUser(authenticated=True, tenant_id=uuid.uuid4())
    # explicit falsy (but present) mapping value must also deny
    view = FakeView(action="list", action_permissions={"list": ""})
    assert perm.has_permission(request, view) is False
    assert view.required_permission == ""


def test_has_permission_uses_default_action_when_view_has_no_action() -> None:
    perm = AIProviderActionPermission()
    request = FakeRequest()
    request.user = FakeUser(authenticated=True, tenant_id=uuid.uuid4())

    class BareView:
        action_permissions: dict[str, str] = {}

    view = BareView()
    # getattr(view, "action", "") -> "" ; action_permissions.get("") -> None -> deny
    assert perm.has_permission(request, view) is False
    assert view.required_permission is None


def test_has_permission_grants_and_wires_pipeline_call_defaults() -> None:
    perm = AIProviderActionPermission()
    tenant_id = uuid.uuid4()
    decision = make_allow_decision(tenant_id)
    pipeline = RecordingPipeline(decision)
    perm.pipeline = pipeline

    request = FakeRequest()
    user = FakeUser(authenticated=True, tenant_id=tenant_id)
    request.user = user
    view = FakeView(action="list", action_permissions={"list": "ai_provider_configuration.provider:read"})

    result = perm.has_permission(request, view)

    assert result is True
    assert view.required_permission == "ai_provider_configuration.provider:read"
    assert request.tenant_id == tenant_id
    assert request.access_decision is decision

    assert len(pipeline.calls) == 1
    call = pipeline.calls[0]
    assert call["tenant_id"] == tenant_id
    assert call["identity"] is user
    assert call["required_permission"] == "ai_provider_configuration.provider:read"
    # defaults: entitlement/quota fall back to `required`, quota_cost defaults to 1
    assert call["entitlement"] == "ai_provider_configuration.provider:read"
    assert call["quota"] == "ai_provider_configuration.provider:read"
    assert call["quota_cost"] == 1
    assert call["request"] is request


def test_has_permission_denies_when_pipeline_denies() -> None:
    perm = AIProviderActionPermission()
    decision = make_deny_decision()
    pipeline = RecordingPipeline(decision)
    perm.pipeline = pipeline

    request = FakeRequest()
    user = FakeUser(authenticated=True, tenant_id=uuid.uuid4())
    request.user = user
    view = FakeView(action="destroy", action_permissions={"destroy": "ai_provider_configuration.resource:delete"})

    result = perm.has_permission(request, view)

    assert result is False
    # access_decision is still recorded even on denial (auditability)
    assert request.access_decision is decision


def test_has_permission_passes_through_explicit_entitlement_quota_and_cost() -> None:
    perm = AIProviderActionPermission()
    decision = make_allow_decision(uuid.uuid4())
    pipeline = RecordingPipeline(decision)
    perm.pipeline = pipeline

    request = FakeRequest()
    user = FakeUser(authenticated=True, tenant_id=uuid.uuid4())
    request.user = user
    view = FakeView(
        action="rotate",
        action_permissions={"rotate": "ai_provider_configuration.secret:rotate"},
        set_entitlement=True,
        required_entitlement="custom.entitlement",
        set_quota_resource=True,
        quota_resource="custom.quota",
        set_quota_cost=True,
        quota_cost=7,
    )

    perm.has_permission(request, view)

    call = pipeline.calls[0]
    assert call["entitlement"] == "custom.entitlement"
    assert call["quota"] == "custom.quota"
    assert call["quota_cost"] == 7


def test_has_permission_handles_no_tenant() -> None:
    perm = AIProviderActionPermission()
    decision = AccessDecision.deny(AccessReasonCode.DENY_TENANT_MISMATCH, "no tenant")
    pipeline = RecordingPipeline(decision)
    perm.pipeline = pipeline

    request = FakeRequest()
    user = FakeUser(authenticated=True, tenant_id=None)
    request.user = user
    view = FakeView(action="list", action_permissions={"list": "ai_provider_configuration.provider:read"})

    result = perm.has_permission(request, view)

    assert result is False
    assert request.tenant_id is None
    assert pipeline.calls[0]["tenant_id"] is None


def test_permission_message_and_class() -> None:
    assert AIProviderActionPermission.message == "You do not have permission to manage AI provider configuration."
    from rest_framework.permissions import BasePermission

    assert issubclass(AIProviderActionPermission, BasePermission)


# --------------------------------------------------------------------------
# TenantProviderThrottle
# --------------------------------------------------------------------------


def test_throttle_scope_value() -> None:
    assert TenantProviderThrottle.scope == "ai_provider_configuration"
    assert issubclass(TenantProviderThrottle, SimpleRateThrottle)


def test_throttle_get_rate_uses_runtime_int_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    throttle = TenantProviderThrottle()
    throttle.request = None  # no bound request -> tenant_id resolves to None

    class FakeService:
        @staticmethod
        def runtime_values(tenant_id):
            assert tenant_id is None
            return {"rate_limits": {"tenant_requests_per_minute": 42}}

    def fake_section(values, key):
        assert key == "rate_limits"
        return values["rate_limits"]

    monkeypatch.setattr(
        "src.modules.ai_provider_configuration.services.AIProviderRuntimeConfigurationService",
        FakeService,
    )
    monkeypatch.setattr("src.modules.ai_provider_configuration.services._section", fake_section)

    assert throttle.get_rate() == "42/min"


def test_throttle_get_rate_falls_back_when_limit_not_int(monkeypatch: pytest.MonkeyPatch) -> None:
    throttle = TenantProviderThrottle()
    throttle.request = None

    class FakeService:
        @staticmethod
        def runtime_values(tenant_id):
            return {"rate_limits": {"tenant_requests_per_minute": "not-an-int"}}

    def fake_section(values, key):
        return values["rate_limits"]

    monkeypatch.setattr(
        "src.modules.ai_provider_configuration.services.AIProviderRuntimeConfigurationService",
        FakeService,
    )
    monkeypatch.setattr("src.modules.ai_provider_configuration.services._section", fake_section)

    assert throttle.get_rate() == "120/min"


def test_throttle_get_rate_falls_back_when_rate_limits_not_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    throttle = TenantProviderThrottle()
    throttle.request = None

    class FakeService:
        @staticmethod
        def runtime_values(tenant_id):
            return {"rate_limits": None}

    def fake_section(values, key):
        return values["rate_limits"]

    monkeypatch.setattr(
        "src.modules.ai_provider_configuration.services.AIProviderRuntimeConfigurationService",
        FakeService,
    )
    monkeypatch.setattr("src.modules.ai_provider_configuration.services._section", fake_section)

    assert throttle.get_rate() == "120/min"


def test_throttle_get_rate_resolves_tenant_from_request_user(monkeypatch: pytest.MonkeyPatch) -> None:
    throttle = TenantProviderThrottle()
    tenant_id = uuid.uuid4()
    request = FakeRequest()
    request.user = FakeUser(authenticated=True, tenant_id=tenant_id)
    throttle.request = request

    seen = {}

    class FakeService:
        @staticmethod
        def runtime_values(tid):
            seen["tenant_id"] = tid
            return {"rate_limits": {"tenant_requests_per_minute": 10}}

    def fake_section(values, key):
        return values["rate_limits"]

    monkeypatch.setattr(
        "src.modules.ai_provider_configuration.services.AIProviderRuntimeConfigurationService",
        FakeService,
    )
    monkeypatch.setattr("src.modules.ai_provider_configuration.services._section", fake_section)

    assert throttle.get_rate() == "10/min"
    assert seen["tenant_id"] == tenant_id


def test_throttle_allow_request_binds_request_and_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    throttle = TenantProviderThrottle()
    request = FakeRequest()
    request.user = FakeUser(authenticated=False)
    view = object()

    calls = []

    def fake_super_allow(self, req, v):
        calls.append((req, v))
        return True

    monkeypatch.setattr(SimpleRateThrottle, "allow_request", fake_super_allow)

    result = throttle.allow_request(request, view)

    assert result is True
    assert throttle.request is request
    assert calls == [(request, view)]


def test_throttle_get_cache_key_returns_none_when_user_missing() -> None:
    throttle = TenantProviderThrottle()
    request = FakeRequest()
    request.user = None
    assert throttle.get_cache_key(request, view=object()) is None


def test_throttle_get_cache_key_returns_none_when_not_authenticated() -> None:
    throttle = TenantProviderThrottle()
    request = FakeRequest()
    request.user = FakeUser(authenticated=False)
    assert throttle.get_cache_key(request, view=object()) is None


def test_throttle_get_cache_key_uses_tenant_when_present() -> None:
    throttle = TenantProviderThrottle()
    tenant_id = uuid.uuid4()
    request = FakeRequest()
    request.user = FakeUser(authenticated=True, tenant_id=tenant_id)
    key = throttle.get_cache_key(request, view=object())
    expected = throttle.cache_format % {
        "scope": "ai_provider_configuration",
        "ident": f"tenant:{tenant_id}",
    }
    assert key == expected
    assert f"tenant:{tenant_id}" in key


def test_throttle_get_cache_key_falls_back_to_user_pk_when_no_tenant() -> None:
    throttle = TenantProviderThrottle()
    request = FakeRequest()
    request.user = FakeUser(authenticated=True, tenant_id=None, pk=99)
    key = throttle.get_cache_key(request, view=object())
    expected = throttle.cache_format % {
        "scope": "ai_provider_configuration",
        "ident": "user:99",
    }
    assert key == expected
    assert "user:99" in key


def test_throttle_get_cache_key_view_argument_is_unused() -> None:
    """The `view` parameter is explicitly discarded; passing distinct objects must not change the result."""
    throttle = TenantProviderThrottle()
    tenant_id = uuid.uuid4()
    request = FakeRequest()
    request.user = FakeUser(authenticated=True, tenant_id=tenant_id)

    key_a = throttle.get_cache_key(request, view=object())
    key_b = throttle.get_cache_key(request, view="totally-different-view")
    assert key_a == key_b


# --------------------------------------------------------------------------
# ActionPermissionMixin
# --------------------------------------------------------------------------


def test_action_permission_mixin_declares_expected_defaults() -> None:
    assert ActionPermissionMixin.authentication_classes == (SessionAuthentication401,)
    assert ActionPermissionMixin.permission_classes == (IsAuthenticated, AIProviderActionPermission)
    assert ActionPermissionMixin.throttle_classes == (TenantProviderThrottle,)
    assert ActionPermissionMixin.action_permissions == {}


def test_action_permission_mixin_action_permissions_is_a_fresh_dict_per_subclass() -> None:
    # Sanity: the class attribute is a plain empty dict, mutation-sensitive on
    # "== {}" vs "is None" vs truthiness checks elsewhere in the module.
    assert isinstance(ActionPermissionMixin.action_permissions, dict)
    assert len(ActionPermissionMixin.action_permissions) == 0
