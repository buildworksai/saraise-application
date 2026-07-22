"""Fail-closed permission metadata tests for every governed HR action."""

from types import MappingProxyType

import pytest
from rest_framework.test import APIRequestFactory

from ..permissions import (
    ACTION_ACCESS,
    ENTITLEMENT,
    PERMISSIONS,
    AccessRequirement,
    GovernedSessionAuthentication,
    requirement_for,
)


def test_permission_catalog_is_complete_and_has_no_paid_domain_claims() -> None:
    assert set(PERMISSIONS) == {
        "hr.department:read",
        "hr.department:create",
        "hr.department:update",
        "hr.department:delete",
        "hr.employee:read",
        "hr.employee:create",
        "hr.employee:update",
        "hr.employee:delete",
        "hr.employee:transition",
        "hr.attendance:read",
        "hr.attendance:create",
        "hr.attendance:update",
        "hr.attendance:delete",
        "hr.attendance:clock",
        "hr.leave_balance:read",
        "hr.leave_balance:create",
        "hr.leave_balance:adjust",
        "hr.leave_balance:delete",
        "hr.leave_request:read",
        "hr.leave_request:create",
        "hr.leave_request:update",
        "hr.leave_request:approve",
        "hr.leave_request:reject",
        "hr.leave_request:cancel",
        "hr.leave_request:delete",
        "hr.health:read",
    }
    assert not any(
        fragment in permission
        for permission in PERMISSIONS
        for fragment in ("payroll", "recruit", "performance")
    )


def test_every_mapped_action_declares_entitlement_and_positive_quota() -> None:
    assert isinstance(ACTION_ACCESS, MappingProxyType)
    for actions in ACTION_ACCESS.values():
        assert isinstance(actions, MappingProxyType)
        for requirement in actions.values():
            assert requirement.permission in PERMISSIONS
            assert requirement.entitlement == ENTITLEMENT == "human_resources"
            assert requirement.quota_resource.startswith("human_resources.")
            assert requirement.quota_cost > 0


def test_unmapped_actions_deny_by_default() -> None:
    assert requirement_for("employee", "update") is None  # PUT is unsupported.
    assert requirement_for("employee", "new_unreviewed_action") is None
    assert requirement_for("unknown-resource", "list") is None


def test_session_authentication_advertises_a_401_challenge_without_relaxing_csrf() -> None:
    authentication = GovernedSessionAuthentication()
    request = APIRequestFactory().get("/api/v2/human-resources/employees/")
    assert authentication.authenticate_header(request) == "Session"
    # The implementation is the standard DRF SessionAuthentication subclass;
    # it deliberately does not override authenticate()/enforce_csrf().
    assert "authenticate" not in GovernedSessionAuthentication.__dict__
    assert "enforce_csrf" not in GovernedSessionAuthentication.__dict__


@pytest.mark.parametrize(
    "kwargs",
    (
        {"permission": "", "entitlement": "human_resources", "quota_resource": "reads"},
        {"permission": "hr.employee:read", "entitlement": "", "quota_resource": "reads"},
        {"permission": "hr.employee:read", "entitlement": "human_resources", "quota_resource": ""},
        {
            "permission": "hr.employee:read",
            "entitlement": "human_resources",
            "quota_resource": "reads",
            "quota_cost": 0,
        },
    ),
)
def test_access_requirement_rejects_incomplete_or_nonpositive_metadata(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        AccessRequirement(**kwargs)  # type: ignore[arg-type]
