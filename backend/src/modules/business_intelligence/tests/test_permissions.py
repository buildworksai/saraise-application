"""Fail-closed BI access metadata tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

from src.core.access import AccessDecision, AccessReasonCode
from src.modules.business_intelligence.permissions import (
    CORE_ENTITLEMENT,
    EXECUTION_QUOTA,
    BIActionPermission,
    StrictSessionAuthentication,
    _NonConsumingQuota,
    _NonConsumingQuotaResult,
)


def test_unknown_action_denies_by_default() -> None:
    pipeline = Mock()
    pipeline.decide.return_value = AccessDecision.deny(AccessReasonCode.DENY_DEFAULT, "missing")
    permission = BIActionPermission(pipeline=pipeline)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True), tenant_id=None)
    view = SimpleNamespace(action="unmapped", permission_map={})
    assert permission.has_permission(request, view) is False
    assert view.required_permission is None


def test_object_tenant_mismatch_is_denied() -> None:
    permission = BIActionPermission()
    request = SimpleNamespace(
        access_decision=AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="ok",
            tenant_id=__import__("uuid").uuid4(),
        )
    )
    assert (
        permission.has_object_permission(request, object(), SimpleNamespace(tenant_id=__import__("uuid").uuid4()))
        is False
    )


def test_permission_sets_request_tenant_before_pipeline(monkeypatch) -> None:
    tenant_id = UUID("11111111-1111-4111-8111-111111111111")
    monkeypatch.setattr("src.modules.business_intelligence.permissions.get_user_tenant_id", lambda user: tenant_id)
    pipeline = Mock()
    pipeline.quota_service = object()
    pipeline.decide.return_value = AccessDecision(
        allowed=True,
        reason_code=AccessReasonCode.ALLOW,
        reason="ok",
        tenant_id=tenant_id,
    )
    permission = BIActionPermission(pipeline=pipeline)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True), tenant_id=None)
    view = SimpleNamespace(action="list", permission_map={"list": "bi.dataset:read"})

    assert permission.has_permission(request, view) is True

    assert request.tenant_id == tenant_id
    assert pipeline.decide.call_args.args[:3] == (tenant_id, request.user, "bi.dataset:read")


def test_invalid_tenant_value_falls_back_to_none(monkeypatch) -> None:
    """A tenant identifier that cannot become a UUID must deny fail-closed, not raise."""

    monkeypatch.setattr(
        "src.modules.business_intelligence.permissions.get_user_tenant_id",
        lambda user: "not-a-valid-uuid",
    )
    pipeline = Mock()
    pipeline.decide.return_value = AccessDecision.deny(AccessReasonCode.DENY_DEFAULT, "no tenant")
    permission = BIActionPermission(pipeline=pipeline)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True), tenant_id="unset")
    view = SimpleNamespace(action="list", permission_map={"list": "bi.dataset:read"})

    assert permission.has_permission(request, view) is False
    assert request.tenant_id is None


def test_falsy_tenant_skips_uuid_coercion(monkeypatch) -> None:
    """An empty/falsy tenant must resolve to None directly, without attempting UUID()."""

    monkeypatch.setattr("src.modules.business_intelligence.permissions.get_user_tenant_id", lambda user: "")
    pipeline = Mock()
    pipeline.decide.return_value = AccessDecision.deny(AccessReasonCode.DENY_DEFAULT, "no tenant")
    permission = BIActionPermission(pipeline=pipeline)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True), tenant_id="unset")
    view = SimpleNamespace(action="list", permission_map={"list": "bi.dataset:read"})

    assert permission.has_permission(request, view) is False
    assert request.tenant_id is None


def test_non_dict_permission_map_yields_no_required_permission() -> None:
    """A malformed (non-dict) permission_map must not raise; required permission is None."""

    pipeline = Mock()
    pipeline.decide.return_value = AccessDecision.deny(AccessReasonCode.DENY_DEFAULT, "missing")
    permission = BIActionPermission(pipeline=pipeline)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True), tenant_id=None)
    view = SimpleNamespace(action="list", permission_map=["not", "a", "dict"])

    assert permission.has_permission(request, view) is False
    assert permission.required_permission is None
    assert view.required_permission is None


def test_action_falls_back_to_permission_action_attribute() -> None:
    """When `view.action` is absent/falsy, `view.permission_action` is used instead."""

    pipeline = Mock()
    pipeline.quota_service = object()
    pipeline.decide.return_value = AccessDecision(
        allowed=True,
        reason_code=AccessReasonCode.ALLOW,
        reason="ok",
        tenant_id=None,
    )
    permission = BIActionPermission(pipeline=pipeline)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True), tenant_id=None)
    view = SimpleNamespace(action=None, permission_action="list", permission_map={"list": "bi.dataset:read"})

    assert permission.has_permission(request, view) is True
    assert permission.required_permission == "bi.dataset:read"


def test_execute_action_uses_execution_quota_and_real_pipeline_quota_service() -> None:
    """The execute action must consume the execution quota via the real pipeline (no swap)."""

    real_quota_service = object()
    pipeline = Mock()
    pipeline.quota_service = real_quota_service
    pipeline.decide.return_value = AccessDecision(
        allowed=True,
        reason_code=AccessReasonCode.ALLOW,
        reason="ok",
        tenant_id=None,
    )
    permission = BIActionPermission(pipeline=pipeline)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True), tenant_id=None)
    view = SimpleNamespace(action="execute", permission_map={"execute": "bi.dataset:execute"})

    assert permission.has_permission(request, view) is True
    # Compare against literal strings, not the imported constants, so a mutation
    # of the constant's value inside permissions.py is actually observable here.
    assert view.quota_resource == "business_intelligence.executions"
    assert view.quota_resource == EXECUTION_QUOTA
    assert view.required_entitlement == "business_intelligence.core"
    assert view.required_entitlement == CORE_ENTITLEMENT
    # Non-consuming substitution must never happen on the execute path.
    assert pipeline.quota_service is real_quota_service


def test_non_execute_action_with_required_permission_uses_it_as_quota_resource() -> None:
    """Reads/definition mutations use the resolved permission string as the quota resource."""

    pipeline = Mock()
    pipeline.quota_service = object()
    pipeline.decide.return_value = AccessDecision(
        allowed=True,
        reason_code=AccessReasonCode.ALLOW,
        reason="ok",
        tenant_id=None,
    )
    permission = BIActionPermission(pipeline=pipeline)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True), tenant_id=None)
    view = SimpleNamespace(action="retrieve", permission_map={"retrieve": "bi.dataset:read"})

    assert permission.has_permission(request, view) is True
    assert view.quota_resource == "bi.dataset:read"
    assert view.required_entitlement == "business_intelligence.core"


def test_action_resembling_execute_is_not_treated_as_execute() -> None:
    """Only the exact string 'execute' triggers the execution-quota path."""

    pipeline = Mock()
    pipeline.quota_service = object()
    pipeline.decide.return_value = AccessDecision(
        allowed=True,
        reason_code=AccessReasonCode.ALLOW,
        reason="ok",
        tenant_id=None,
    )
    permission = BIActionPermission(pipeline=pipeline)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True), tenant_id=None)
    view = SimpleNamespace(action="executed", permission_map={"executed": "bi.dataset:executed"})

    assert permission.has_permission(request, view) is True
    # Must use the required-permission-derived resource, never the execution quota constant.
    assert view.quota_resource == "bi.dataset:executed"
    assert view.quota_resource != EXECUTION_QUOTA


def test_non_execute_action_without_required_permission_uses_non_consuming_fallback() -> None:
    """When no permission maps to the action, the non-consuming fallback resource name is used."""

    pipeline = Mock()
    pipeline.quota_service = object()
    pipeline.decide.return_value = AccessDecision.deny(AccessReasonCode.DENY_DEFAULT, "missing")
    permission = BIActionPermission(pipeline=pipeline)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True), tenant_id=None)
    view = SimpleNamespace(action="unmapped", permission_map={})

    assert permission.has_permission(request, view) is False
    assert view.quota_resource == "business_intelligence.non_consuming"


def test_non_execute_action_swaps_and_restores_quota_service() -> None:
    """The pipeline's quota_service must be swapped to the non-consuming adapter and restored after."""

    original_quota_service = object()
    pipeline = Mock()
    pipeline.quota_service = original_quota_service
    observed_quota_service_during_decide = {}

    def _capture_decide(*args, **kwargs):
        observed_quota_service_during_decide["value"] = pipeline.quota_service
        return AccessDecision(allowed=True, reason_code=AccessReasonCode.ALLOW, reason="ok", tenant_id=None)

    pipeline.decide.side_effect = _capture_decide
    permission = BIActionPermission(pipeline=pipeline)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True), tenant_id=None)
    view = SimpleNamespace(action="list", permission_map={"list": "bi.dataset:read"})

    assert permission.has_permission(request, view) is True
    # During the decision, the pipeline must be using the non-consuming adapter.
    assert isinstance(observed_quota_service_during_decide["value"], _NonConsumingQuota)
    # After has_permission returns, the original quota service must be restored.
    assert pipeline.quota_service is original_quota_service


def test_non_execute_action_restores_quota_service_even_when_decide_raises() -> None:
    """The finally block must restore quota_service even if the pipeline raises."""

    original_quota_service = object()
    pipeline = Mock()
    pipeline.quota_service = original_quota_service
    pipeline.decide.side_effect = RuntimeError("boom")
    permission = BIActionPermission(pipeline=pipeline)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True), tenant_id=None)
    view = SimpleNamespace(action="list", permission_map={"list": "bi.dataset:read"})

    try:
        permission.has_permission(request, view)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError to propagate")

    assert pipeline.quota_service is original_quota_service


def test_strict_session_authentication_header_is_stable() -> None:
    auth = StrictSessionAuthentication()
    assert auth.authenticate_header(SimpleNamespace()) == 'Session realm="api"'


def test_non_consuming_quota_accepts_tenant_id_and_resource_as_keywords() -> None:
    """`cost` is keyword-only; `tenant_id`/`resource` must remain callable by keyword too.

    This pins the exact signature shape `(self, tenant_id, resource, *, cost=1)` —
    a mutation that turns the bare `*` into a positional-only `/` marker would make
    `tenant_id`/`resource` positional-only and this call would raise TypeError.
    """

    quota = _NonConsumingQuota()
    result = quota.consume(tenant_id=uuid4(), resource="business_intelligence.executions", cost=1)
    assert result.allowed is True
    assert result.remaining == 0


def test_non_consuming_quota_never_denies_or_consumes() -> None:
    quota = _NonConsumingQuota()
    result = quota.consume(uuid4(), "any.resource", cost=999)
    assert result.allowed is True
    assert result.remaining == 0
    # Re-invoking with different arguments must be stable — nothing is tracked/consumed.
    result_again = quota.consume(None, "", cost=1)
    assert result_again.allowed is True
    assert result_again.remaining == 0


def test_non_consuming_quota_result_defaults() -> None:
    result = _NonConsumingQuotaResult()
    assert result.allowed is True
    assert result.remaining == 0
    custom = _NonConsumingQuotaResult(allowed=False, remaining=5)
    assert custom.allowed is False
    assert custom.remaining == 5


def test_missing_permission_map_attribute_defaults_to_empty_dict() -> None:
    """A view with no permission_map at all must default to {} (dict), not None or []."""

    pipeline = Mock()
    pipeline.decide.return_value = AccessDecision.deny(AccessReasonCode.DENY_DEFAULT, "missing")
    permission = BIActionPermission(pipeline=pipeline)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True), tenant_id=None)
    view = SimpleNamespace(action="list")

    assert permission.has_permission(request, view) is False
    assert permission.required_permission is None
    assert view.required_permission is None


def test_missing_action_attribute_falls_back_to_permission_action() -> None:
    """A view with no `action` attribute at all must still resolve via permission_action."""

    pipeline = Mock()
    pipeline.quota_service = object()
    pipeline.decide.return_value = AccessDecision(
        allowed=True,
        reason_code=AccessReasonCode.ALLOW,
        reason="ok",
        tenant_id=None,
    )
    permission = BIActionPermission(pipeline=pipeline)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True), tenant_id=None)
    view = SimpleNamespace(permission_action="list", permission_map={"list": "bi.dataset:read"})

    assert permission.has_permission(request, view) is True
    assert permission.required_permission == "bi.dataset:read"


def test_non_consuming_quota_result_is_frozen() -> None:
    """The result dataclass must be immutable — frozen=True is load-bearing."""

    result = _NonConsumingQuotaResult()
    try:
        result.allowed = False  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("expected mutation of a frozen dataclass to raise")
