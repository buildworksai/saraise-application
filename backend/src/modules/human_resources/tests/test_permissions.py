"""Fail-closed permission metadata tests for every governed HR action."""

from types import MappingProxyType

import pytest
from rest_framework.test import APIRequestFactory

from ..permissions import (
    ACTION_ACCESS,
    ATTENDANCE_ACTION_PERMISSIONS,
    CONFIGURATION_ACTION_PERMISSIONS,
    DEPARTMENT_ACTION_PERMISSIONS,
    EMPLOYEE_ACTION_PERMISSIONS,
    ENTITLEMENT,
    HEALTH_ACTION_PERMISSIONS,
    LEAVE_BALANCE_ACTION_PERMISSIONS,
    LEAVE_REQUEST_ACTION_PERMISSIONS,
    PERMISSIONS,
    AccessRequirement,
    GovernedSessionAuthentication,
    requirement_for,
)

# Exact expected metadata for every governed action, keyed by
# (resource, action) -> (permission, quota_resource, quota_cost).
# This is the ground truth the source module must reproduce exactly;
# any swapped literal, wrong key, or altered default cost must fail here.
EXPECTED_ACCESS: dict[tuple[str, str], tuple[str, str, int]] = {
    ("department", "list"): ("hr.department:read", "human_resources.department_reads", 1),
    ("department", "retrieve"): ("hr.department:read", "human_resources.department_reads", 1),
    ("department", "tree"): ("hr.department:read", "human_resources.department_reads", 1),
    ("department", "create"): ("hr.department:create", "human_resources.department_writes", 1),
    ("department", "partial_update"): ("hr.department:update", "human_resources.department_writes", 1),
    ("department", "activate"): ("hr.department:update", "human_resources.department_writes", 1),
    ("department", "deactivate"): ("hr.department:update", "human_resources.department_writes", 1),
    ("department", "destroy"): ("hr.department:delete", "human_resources.department_writes", 1),
    ("employee", "list"): ("hr.employee:read", "human_resources.employee_reads", 1),
    ("employee", "retrieve"): ("hr.employee:read", "human_resources.employee_reads", 1),
    ("employee", "reporting_tree"): ("hr.employee:read", "human_resources.employee_reads", 1),
    ("employee", "create"): ("hr.employee:create", "human_resources.employee_writes", 1),
    ("employee", "partial_update"): ("hr.employee:update", "human_resources.employee_writes", 1),
    ("employee", "destroy"): ("hr.employee:delete", "human_resources.employee_writes", 1),
    ("employee", "activate"): ("hr.employee:transition", "human_resources.employee_transitions", 1),
    ("employee", "deactivate"): ("hr.employee:transition", "human_resources.employee_transitions", 1),
    ("employee", "place_on_leave"): ("hr.employee:transition", "human_resources.employee_transitions", 1),
    ("employee", "return_from_leave"): ("hr.employee:transition", "human_resources.employee_transitions", 1),
    ("employee", "terminate"): ("hr.employee:transition", "human_resources.employee_transitions", 1),
    ("attendance", "list"): ("hr.attendance:read", "human_resources.attendance_reads", 1),
    ("attendance", "retrieve"): ("hr.attendance:read", "human_resources.attendance_reads", 1),
    ("attendance", "create"): ("hr.attendance:create", "human_resources.attendance_writes", 1),
    ("attendance", "partial_update"): ("hr.attendance:update", "human_resources.attendance_writes", 1),
    ("attendance", "destroy"): ("hr.attendance:delete", "human_resources.attendance_writes", 1),
    ("attendance", "clock_in"): ("hr.attendance:clock", "human_resources.attendance_clock", 1),
    ("attendance", "clock_out"): ("hr.attendance:clock", "human_resources.attendance_clock", 1),
    ("leave-balance", "list"): ("hr.leave_balance:read", "human_resources.leave_balance_reads", 1),
    ("leave-balance", "retrieve"): ("hr.leave_balance:read", "human_resources.leave_balance_reads", 1),
    ("leave-balance", "create"): ("hr.leave_balance:create", "human_resources.leave_balance_writes", 1),
    (
        "leave-balance",
        "partial_update",
    ): ("hr.leave_balance:adjust", "human_resources.leave_balance_adjustments", 1),
    ("leave-balance", "destroy"): ("hr.leave_balance:delete", "human_resources.leave_balance_writes", 1),
    ("leave-request", "list"): ("hr.leave_request:read", "human_resources.leave_request_reads", 1),
    ("leave-request", "retrieve"): ("hr.leave_request:read", "human_resources.leave_request_reads", 1),
    ("leave-request", "create"): ("hr.leave_request:create", "human_resources.leave_request_writes", 1),
    ("leave-request", "partial_update"): ("hr.leave_request:update", "human_resources.leave_request_writes", 1),
    ("leave-request", "approve"): ("hr.leave_request:approve", "human_resources.leave_request_approvals", 1),
    ("leave-request", "reject"): ("hr.leave_request:reject", "human_resources.leave_request_approvals", 1),
    ("leave-request", "cancel"): ("hr.leave_request:cancel", "human_resources.leave_request_transitions", 1),
    ("leave-request", "destroy"): ("hr.leave_request:delete", "human_resources.leave_request_writes", 1),
    ("configuration", "list"): ("hr.configuration:read", "human_resources.configuration_reads", 1),
    ("configuration", "partial_update"): ("hr.configuration:update", "human_resources.configuration_writes", 1),
    ("configuration", "preview"): ("hr.configuration:read", "human_resources.configuration_reads", 1),
    ("configuration", "history"): ("hr.configuration:read", "human_resources.configuration_reads", 1),
    ("configuration", "audit"): ("hr.configuration:audit", "human_resources.configuration_reads", 1),
    ("configuration", "rollback"): ("hr.configuration:rollback", "human_resources.configuration_writes", 1),
    (
        "configuration",
        "import_configuration",
    ): ("hr.configuration:import", "human_resources.configuration_writes", 1),
    (
        "configuration",
        "export_configuration",
    ): ("hr.configuration:export", "human_resources.configuration_reads", 1),
    ("health", "get"): ("hr.health:read", "human_resources.health_reads", 1),
}

RESOURCE_SUBMAPS: dict[str, MappingProxyType] = {
    "department": DEPARTMENT_ACTION_PERMISSIONS,
    "employee": EMPLOYEE_ACTION_PERMISSIONS,
    "attendance": ATTENDANCE_ACTION_PERMISSIONS,
    "leave-balance": LEAVE_BALANCE_ACTION_PERMISSIONS,
    "leave-request": LEAVE_REQUEST_ACTION_PERMISSIONS,
    "configuration": CONFIGURATION_ACTION_PERMISSIONS,
    "health": HEALTH_ACTION_PERMISSIONS,
}


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
        "hr.configuration:read",
        "hr.configuration:update",
        "hr.configuration:audit",
        "hr.configuration:rollback",
        "hr.configuration:import",
        "hr.configuration:export",
        "hr.health:read",
    }
    assert not any(
        fragment in permission for permission in PERMISSIONS for fragment in ("payroll", "recruit", "performance")
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


def test_action_access_top_level_keys_are_exactly_the_seven_governed_resources() -> None:
    assert set(ACTION_ACCESS.keys()) == {
        "department",
        "employee",
        "attendance",
        "leave-balance",
        "leave-request",
        "configuration",
        "health",
    }
    assert len(ACTION_ACCESS) == 7


@pytest.mark.parametrize("resource,action", sorted(EXPECTED_ACCESS.keys()))
def test_every_governed_action_matches_its_pinned_access_requirement_exactly(resource: str, action: str) -> None:
    expected_permission, expected_quota_resource, expected_quota_cost = EXPECTED_ACCESS[(resource, action)]
    requirement = requirement_for(resource, action)
    assert requirement is not None
    assert requirement.permission == expected_permission
    assert requirement.entitlement == "human_resources"
    assert requirement.quota_resource == expected_quota_resource
    assert requirement.quota_cost == expected_quota_cost
    # requirement_for() must delegate to the exact same object stored in ACTION_ACCESS.
    assert requirement is ACTION_ACCESS[resource][action]


@pytest.mark.parametrize(
    "resource,expected_actions",
    (
        (
            "department",
            {"list", "retrieve", "tree", "create", "partial_update", "activate", "deactivate", "destroy"},
        ),
        (
            "employee",
            {
                "list",
                "retrieve",
                "reporting_tree",
                "create",
                "partial_update",
                "destroy",
                "activate",
                "deactivate",
                "place_on_leave",
                "return_from_leave",
                "terminate",
            },
        ),
        (
            "attendance",
            {"list", "retrieve", "create", "partial_update", "destroy", "clock_in", "clock_out"},
        ),
        (
            "leave-balance",
            {"list", "retrieve", "create", "partial_update", "destroy"},
        ),
        (
            "leave-request",
            {
                "list",
                "retrieve",
                "create",
                "partial_update",
                "approve",
                "reject",
                "cancel",
                "destroy",
            },
        ),
        (
            "configuration",
            {
                "list",
                "partial_update",
                "preview",
                "history",
                "audit",
                "rollback",
                "import_configuration",
                "export_configuration",
            },
        ),
        ("health", {"get"}),
    ),
)
def test_each_resource_submap_declares_exactly_its_expected_action_keys(
    resource: str, expected_actions: set[str]
) -> None:
    submap = RESOURCE_SUBMAPS[resource]
    assert set(submap.keys()) == expected_actions
    assert len(submap) == len(expected_actions)
    # Every submap must also be reachable, unmodified, from ACTION_ACCESS.
    assert ACTION_ACCESS[resource] is submap


def test_entitlement_constant_is_pinned() -> None:
    assert ENTITLEMENT == "human_resources"


def test_rule_helper_defaults_quota_cost_to_exactly_one() -> None:
    # Every declared action above uses the default cost; explicitly re-derive
    # one to pin the default value of the `cost` keyword itself (not just the
    # values already baked into ACTION_ACCESS).
    from ..permissions import _rule  # noqa: PLC0415 - deliberate internal import for default-arg pin

    default_rule = _rule("hr.employee:read", "human_resources.employee_reads")
    assert default_rule.quota_cost == 1
    explicit_rule = _rule("hr.employee:read", "human_resources.employee_reads", cost=3)
    assert explicit_rule.quota_cost == 3
    assert default_rule.entitlement == ENTITLEMENT
    assert default_rule.permission == "hr.employee:read"
    assert default_rule.quota_resource == "human_resources.employee_reads"


def test_access_requirement_accepts_quota_cost_of_exactly_one_boundary() -> None:
    # Pin the boundary: quota_cost == 1 must succeed (not just >1), and
    # quota_cost == 0 must fail (already covered above) -- together these
    # pin the `<= 0` boundary precisely rather than merely `< 0`.
    requirement = AccessRequirement(
        permission="hr.employee:read",
        entitlement="human_resources",
        quota_resource="human_resources.employee_reads",
        quota_cost=1,
    )
    assert requirement.quota_cost == 1
    with pytest.raises(ValueError):
        AccessRequirement(
            permission="hr.employee:read",
            entitlement="human_resources",
            quota_resource="human_resources.employee_reads",
            quota_cost=-1,
        )


def test_requirement_for_returns_none_for_known_resource_with_wrong_action_case() -> None:
    # Guards against a mutant that changes `.get(resource, {})` to always miss
    # or always hit -- exercising a resource that exists but an action that
    # does not, plus the reverse (action that exists on a different resource).
    assert requirement_for("department", "clock_in") is None
    assert requirement_for("health", "list") is None
    assert requirement_for("", "") is None


def test_governed_session_authentication_header_ignores_request_argument() -> None:
    authentication = GovernedSessionAuthentication()
    # Calling with two different requests (including None-like empty factory
    # requests) must always return the same fixed challenge string, proving
    # the implementation does not branch on `request` at all.
    request_one = APIRequestFactory().get("/api/v2/human-resources/departments/")
    request_two = APIRequestFactory().post("/api/v2/human-resources/employees/")
    assert authentication.authenticate_header(request_one) == "Session"
    assert authentication.authenticate_header(request_two) == "Session"


def test_permissions_tuple_is_sorted_and_deduplicated() -> None:
    assert list(PERMISSIONS) == sorted(set(PERMISSIONS))
    assert len(PERMISSIONS) == len(set(PERMISSIONS))
    assert isinstance(PERMISSIONS, tuple)


def test_access_requirement_is_frozen_and_mutation_is_rejected() -> None:
    import dataclasses

    requirement = AccessRequirement(
        permission="hr.employee:read",
        entitlement="human_resources",
        quota_resource="human_resources.employee_reads",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        requirement.permission = "hr.employee:update"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        requirement.quota_cost = 99  # type: ignore[misc]


def test_access_requirement_uses_slots_and_rejects_arbitrary_attributes() -> None:
    requirement = AccessRequirement(
        permission="hr.employee:read",
        entitlement="human_resources",
        quota_resource="human_resources.employee_reads",
    )
    # `slots=True` means there is no per-instance __dict__, so assigning any
    # attribute outside the declared dataclass fields must raise -- this is
    # independent of (and in addition to) the frozen=True check above, since
    # a non-frozen, non-slotted dataclass would silently accept this.
    assert not hasattr(requirement, "__dict__")
    # frozen=True's custom __setattr__ would intercept a normal assignment
    # before slots ever gets a say, so bypass it via object.__setattr__ (the
    # same mechanism the dataclass's own generated __init__ uses) to isolate
    # the slots=True behavior specifically: with real __slots__ there is no
    # per-instance __dict__ to fall back on, so setting an undeclared name
    # raises AttributeError; without slots (the mutated behavior) it would
    # silently succeed by populating a regular instance __dict__.
    with pytest.raises(AttributeError):
        object.__setattr__(requirement, "brand_new_attribute", "unexpected")


def test_access_requirement_quota_cost_field_default_is_exactly_one() -> None:
    # Omit quota_cost entirely so the dataclass field default (line 33) is
    # what's exercised, distinct from the `_rule` helper's own `cost=1`
    # keyword default pinned separately above.
    requirement = AccessRequirement(
        permission="hr.employee:read",
        entitlement="human_resources",
        quota_resource="human_resources.employee_reads",
    )
    assert requirement.quota_cost == 1


def test_rule_helper_rejects_cost_supplied_positionally() -> None:
    # `cost` is declared keyword-only (`*, cost: int = 1`); calling it
    # positionally must raise TypeError. This pins the `*` keyword-only
    # marker itself, distinguishing it from a `/` positional-only marker
    # which would silently accept a positional `cost` argument instead.
    from ..permissions import _rule  # noqa: PLC0415 - deliberate internal import for signature pin

    with pytest.raises(TypeError):
        _rule("hr.employee:read", "human_resources.employee_reads", 5)  # type: ignore[misc]
