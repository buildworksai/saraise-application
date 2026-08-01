"""Fail-closed BI access metadata tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

from src.core.access import AccessDecision, AccessReasonCode
from src.modules.business_intelligence.permissions import BIActionPermission


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
