"""Fail-closed BI access metadata tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

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
