"""Permission catalog and deny-default proof."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest import mock

import pytest
import yaml
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request

from src.core.access import RequiresAccess

from ..api import ControlViewSet, RiskAssessmentViewSet
from ..permissions import (
    ACTION_ACCESS,
    CALENDAR_ACTIONS,
    CONFIGURATION_ACTIONS,
    CONTROL_ACTIONS,
    DASHBOARD_ACTIONS,
    ENTITLEMENT,
    HEALTH_ACTIONS,
    HEATMAP_ACTIONS,
    JOB_ACTIONS,
    PERMISSIONS,
    REMEDIATION_ACTIONS,
    REQUIREMENT_ACTIONS,
    RISK_ACTIONS,
    TEST_ACTIONS,
    AccessRequirement,
    ActionAccessMixin,
    GovernedSessionAuthentication,
    requirement_for,
)
from .. import permissions as permissions_module


def test_manifest_and_runtime_permission_catalog_are_exact() -> None:
    manifest = yaml.safe_load((Path(__file__).parents[1] / "manifest.yaml").read_text())
    assert tuple(manifest["permissions"]) == PERMISSIONS
    assert len(PERMISSIONS) == len(set(PERMISSIONS)) == 34
    assert "compliance_risk.configuration:rollback" in PERMISSIONS
    assert "compliance_risk.health:read" in PERMISSIONS


def test_session_authentication_advertises_session_challenge() -> None:
    request = SimpleNamespace()

    assert GovernedSessionAuthentication().authenticate_header(cast(Request, request)) == "Session"


def test_every_action_has_complete_access_metadata() -> None:
    for resource, actions in ACTION_ACCESS.items():
        assert actions, resource
        for action, requirement in actions.items():
            assert requirement_for(resource, action) is requirement
            assert requirement.permission in PERMISSIONS
            assert requirement.entitlement == "compliance_risk_management"
            assert requirement.quota_resource.startswith("compliance_risk.")
            assert requirement.quota_cost > 0


def test_unknown_resource_and_action_deny_by_default() -> None:
    assert requirement_for("unknown", "list") is None
    assert requirement_for("risk", "put") is None


def test_action_access_mixin_sets_trusted_tenant_and_action_metadata() -> None:
    tenant_id = uuid.uuid4()
    request = SimpleNamespace(
        user=SimpleNamespace(profile=SimpleNamespace(tenant_id=str(tenant_id))),
    )
    view = ActionAccessMixin()
    view.request = request  # type: ignore[assignment]
    view.action = "create"  # type: ignore[attr-defined]
    view.action_access = ACTION_ACCESS["risk"]

    permissions = view.get_permissions()

    assert request.tenant_id == tenant_id
    assert view.required_permission == "compliance_risk.risk:create"
    assert view.required_entitlement == "compliance_risk_management"
    assert view.quota_resource == "compliance_risk.risk_writes"
    assert [type(permission) for permission in permissions] == [IsAuthenticated, RequiresAccess]


def test_action_access_mixin_rejects_malformed_tenant_identifier() -> None:
    request = SimpleNamespace(
        user=SimpleNamespace(profile=SimpleNamespace(tenant_id="not-a-uuid")),
    )
    view = ActionAccessMixin()
    view.request = request  # type: ignore[assignment]
    view.action = "create"  # type: ignore[attr-defined]
    view.action_access = ACTION_ACCESS["risk"]

    permissions = view.get_permissions()

    assert request.tenant_id is None
    assert view.required_permission == "compliance_risk.risk:create"
    assert [type(permission) for permission in permissions] == [IsAuthenticated, RequiresAccess]


def test_score_preview_is_read_authorized_and_non_write_quota() -> None:
    requirement = requirement_for("risk", "score_preview")

    assert requirement is not None
    assert requirement.permission == "compliance_risk.risk:read"
    assert requirement.entitlement == "compliance_risk_management"
    assert requirement.quota_resource == "compliance_risk.score_previews"


def test_risk_viewset_uses_declared_score_preview_quota() -> None:
    request: Any = SimpleNamespace(
        user=SimpleNamespace(profile=SimpleNamespace(tenant_id=str(uuid.uuid4()))),
        method="POST",
    )
    view = RiskAssessmentViewSet()
    view.request = request
    view.action = "score_preview"

    view.get_permissions()

    assert view.required_permission == "compliance_risk.risk:read"
    assert view.required_entitlement == "compliance_risk_management"
    assert view.quota_resource == "compliance_risk.score_previews"


def test_nested_post_actions_use_declared_write_quota() -> None:
    tenant_id = str(uuid.uuid4())
    request: Any = SimpleNamespace(user=SimpleNamespace(profile=SimpleNamespace(tenant_id=tenant_id)), method="POST")
    risk_view = RiskAssessmentViewSet()
    risk_view.request = request
    risk_view.action = "controls"

    risk_view.get_permissions()

    assert risk_view.required_permission == "compliance_risk.control:create"
    assert risk_view.quota_resource == "compliance_risk.control_writes"

    control_view = ControlViewSet()
    control_view.request = request
    control_view.action = "tests"

    control_view.get_permissions()

    assert control_view.required_permission == "compliance_risk.test:schedule"
    assert control_view.quota_resource == "compliance_risk.test_schedules"


def test_action_access_mixin_leaves_unknown_action_without_access_metadata() -> None:
    request: Any = SimpleNamespace(
        user=SimpleNamespace(profile=SimpleNamespace(tenant_id=str(uuid.uuid4()))),
    )
    view = ActionAccessMixin()
    view.request = request
    view.action = "not_declared"  # type: ignore[attr-defined]
    view.action_permissions = {"list": "compliance_risk.risk:read"}

    view.get_permissions()

    assert view.required_permission is None
    assert view.required_entitlement is None
    assert view.quota_resource is None


def test_action_access_mixin_supports_legacy_permission_metadata() -> None:
    request: Any = SimpleNamespace(
        user=SimpleNamespace(profile=SimpleNamespace(tenant_id=str(uuid.uuid4()))),
    )
    view = ActionAccessMixin()
    view.request = request
    view.action = "list"  # type: ignore[attr-defined]
    view.action_permissions = {"list": "compliance_risk.risk:read"}

    view.get_permissions()

    assert view.required_permission == "compliance_risk.risk:read"
    assert view.required_entitlement == "compliance_risk_management"
    assert view.quota_resource == "compliance_risk.list"
    assert view.quota_cost == 1


def test_access_requirement_rejects_incomplete_or_invalid_metadata() -> None:
    for kwargs in (
        {"permission": "", "entitlement": "entitlement", "quota_resource": "quota"},
        {"permission": "permission", "entitlement": "", "quota_resource": "quota"},
        {"permission": "permission", "entitlement": "entitlement", "quota_resource": ""},
        {"permission": "permission", "entitlement": "entitlement", "quota_resource": "quota", "quota_cost": 0},
        {"permission": "permission", "entitlement": "entitlement", "quota_resource": "quota", "quota_cost": True},
    ):
        with pytest.raises(ValueError):
            AccessRequirement(**kwargs)


def test_requires_access_rejects_missing_metadata_without_calling_pipeline() -> None:
    class ExplodingPipeline:
        def decide(self, *args: object, **kwargs: object) -> object:
            del args, kwargs
            raise AssertionError("pipeline must not run without permission metadata")

    permission = RequiresAccess(pipeline=ExplodingPipeline())  # type: ignore[arg-type]
    request: Any = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))

    assert permission.has_permission(request, SimpleNamespace()) is False
    assert request.access_decision.allowed is False


def test_action_access_mixin_returns_authenticated_only_when_action_is_none() -> None:
    """DRF leaves ``action`` unset/None for unsupported HTTP verbs (e.g. 405s)."""

    request: Any = SimpleNamespace(
        user=SimpleNamespace(profile=SimpleNamespace(tenant_id=str(uuid.uuid4()))),
    )
    view = ActionAccessMixin()
    view.request = request
    view.action = None  # type: ignore[attr-defined]
    view.action_access = ACTION_ACCESS["risk"]

    permissions = view.get_permissions()

    assert [type(permission) for permission in permissions] == [IsAuthenticated]
    assert not hasattr(view, "required_permission")
    assert not hasattr(view, "quota_resource")


def test_action_access_mixin_returns_authenticated_only_when_action_is_empty_string() -> None:
    request: Any = SimpleNamespace(
        user=SimpleNamespace(profile=SimpleNamespace(tenant_id=str(uuid.uuid4()))),
    )
    view = ActionAccessMixin()
    view.request = request
    view.action = ""  # type: ignore[attr-defined]
    view.action_access = ACTION_ACCESS["risk"]

    permissions = view.get_permissions()

    assert [type(permission) for permission in permissions] == [IsAuthenticated]


def test_action_access_mixin_leaves_tenant_none_when_user_has_no_profile() -> None:
    """A user with no profile at all takes the ``raw_tenant is None`` branch,
    which must short-circuit before ever constructing a ``UUID`` -- unlike the
    malformed-UUID case, which reaches the ``except`` clause.
    """

    request: Any = SimpleNamespace(user=SimpleNamespace())  # no .profile attribute
    view = ActionAccessMixin()
    view.request = request
    view.action = "create"  # type: ignore[attr-defined]
    view.action_access = ACTION_ACCESS["risk"]

    with mock.patch.object(permissions_module, "UUID") as mock_uuid:
        view.get_permissions()

    mock_uuid.assert_not_called()
    assert request.tenant_id is None
    assert view.required_permission == "compliance_risk.risk:create"


def test_action_access_mixin_leaves_tenant_none_when_user_is_none() -> None:
    request: Any = SimpleNamespace(user=None)
    view = ActionAccessMixin()
    view.request = request
    view.action = "list"  # type: ignore[attr-defined]
    view.action_access = ACTION_ACCESS["risk"]

    view.get_permissions()

    assert request.tenant_id is None


def test_action_quotas_explicit_override_wins_over_default_quota_resource() -> None:
    request: Any = SimpleNamespace(
        user=SimpleNamespace(profile=SimpleNamespace(tenant_id=str(uuid.uuid4()))),
    )
    view = ActionAccessMixin()
    view.request = request
    view.action = "list"  # type: ignore[attr-defined]
    view.action_permissions = {"list": "compliance_risk.risk:read"}
    view.action_quotas = {"list": "compliance_risk.custom_override_quota"}

    view.get_permissions()

    assert view.required_permission == "compliance_risk.risk:read"
    assert view.quota_resource == "compliance_risk.custom_override_quota"
    assert view.quota_resource != "compliance_risk.list"


def test_rule_rejects_unknown_permission() -> None:
    with pytest.raises(ValueError, match="Unknown compliance-risk permission: bogus:permission"):
        permissions_module._rule("bogus:permission", "compliance_risk.some_resource")


def test_risk_actions_are_pinned_exactly() -> None:
    expected = {
        "list": ("compliance_risk.risk:read", "compliance_risk.risk_reads", 1),
        "retrieve": ("compliance_risk.risk:read", "compliance_risk.risk_reads", 1),
        "create": ("compliance_risk.risk:create", "compliance_risk.risk_writes", 1),
        "partial_update": ("compliance_risk.risk:update", "compliance_risk.risk_writes", 1),
        "destroy": ("compliance_risk.risk:delete", "compliance_risk.risk_writes", 1),
        "transition": ("compliance_risk.risk:transition", "compliance_risk.risk_transitions", 1),
        "score_preview": ("compliance_risk.risk:read", "compliance_risk.score_previews", 1),
        "controls": ("compliance_risk.control:read", "compliance_risk.control_reads", 1),
        "remediations": ("compliance_risk.remediation:read", "compliance_risk.remediation_reads", 1),
    }
    assert set(RISK_ACTIONS.keys()) == set(expected.keys())
    for action, (permission, quota_resource, quota_cost) in expected.items():
        requirement = RISK_ACTIONS[action]
        assert requirement.permission == permission, action
        assert requirement.quota_resource == quota_resource, action
        assert requirement.quota_cost == quota_cost, action
        assert requirement.entitlement == ENTITLEMENT, action


def test_control_actions_are_pinned_exactly() -> None:
    expected = {
        "list": ("compliance_risk.control:read", "compliance_risk.control_reads"),
        "retrieve": ("compliance_risk.control:read", "compliance_risk.control_reads"),
        "create": ("compliance_risk.control:create", "compliance_risk.control_writes"),
        "partial_update": ("compliance_risk.control:update", "compliance_risk.control_writes"),
        "destroy": ("compliance_risk.control:delete", "compliance_risk.control_writes"),
        "transition": ("compliance_risk.control:transition", "compliance_risk.control_transitions"),
        "tests": ("compliance_risk.test:read", "compliance_risk.test_reads"),
    }
    assert set(CONTROL_ACTIONS.keys()) == set(expected.keys())
    for action, (permission, quota_resource) in expected.items():
        requirement = CONTROL_ACTIONS[action]
        assert requirement.permission == permission, action
        assert requirement.quota_resource == quota_resource, action
        assert requirement.quota_cost == 1, action


def test_test_actions_are_pinned_exactly() -> None:
    expected = {
        "list": ("compliance_risk.test:read", "compliance_risk.test_reads"),
        "retrieve": ("compliance_risk.test:read", "compliance_risk.test_reads"),
        "create": ("compliance_risk.test:schedule", "compliance_risk.test_schedules"),
        "partial_update": ("compliance_risk.test:schedule", "compliance_risk.test_schedules"),
        "start": ("compliance_risk.test:execute", "compliance_risk.test_executions"),
        "result": ("compliance_risk.test:execute", "compliance_risk.test_executions"),
        "cancel": ("compliance_risk.test:execute", "compliance_risk.test_executions"),
    }
    assert set(TEST_ACTIONS.keys()) == set(expected.keys())
    for action, (permission, quota_resource) in expected.items():
        requirement = TEST_ACTIONS[action]
        assert requirement.permission == permission, action
        assert requirement.quota_resource == quota_resource, action
        assert requirement.quota_cost == 1, action


def test_requirement_actions_are_pinned_exactly() -> None:
    expected = {
        "list": ("compliance_risk.requirement:read", "compliance_risk.requirement_reads"),
        "retrieve": ("compliance_risk.requirement:read", "compliance_risk.requirement_reads"),
        "create": ("compliance_risk.requirement:create", "compliance_risk.requirement_writes"),
        "partial_update": ("compliance_risk.requirement:update", "compliance_risk.requirement_writes"),
        "destroy": ("compliance_risk.requirement:delete", "compliance_risk.requirement_writes"),
        "assess": ("compliance_risk.requirement:assess", "compliance_risk.requirement_assessments"),
    }
    assert set(REQUIREMENT_ACTIONS.keys()) == set(expected.keys())
    for action, (permission, quota_resource) in expected.items():
        requirement = REQUIREMENT_ACTIONS[action]
        assert requirement.permission == permission, action
        assert requirement.quota_resource == quota_resource, action
        assert requirement.quota_cost == 1, action


def test_calendar_actions_are_pinned_exactly() -> None:
    expected = {
        "list": ("compliance_risk.calendar:read", "compliance_risk.calendar_reads"),
        "retrieve": ("compliance_risk.calendar:read", "compliance_risk.calendar_reads"),
        "create": ("compliance_risk.calendar:create", "compliance_risk.calendar_writes"),
        "partial_update": ("compliance_risk.calendar:update", "compliance_risk.calendar_writes"),
        "destroy": ("compliance_risk.calendar:delete", "compliance_risk.calendar_writes"),
        "transition": ("compliance_risk.calendar:transition", "compliance_risk.calendar_transitions"),
    }
    assert set(CALENDAR_ACTIONS.keys()) == set(expected.keys())
    for action, (permission, quota_resource) in expected.items():
        requirement = CALENDAR_ACTIONS[action]
        assert requirement.permission == permission, action
        assert requirement.quota_resource == quota_resource, action
        assert requirement.quota_cost == 1, action


def test_remediation_actions_are_pinned_exactly() -> None:
    expected = {
        "list": ("compliance_risk.remediation:read", "compliance_risk.remediation_reads"),
        "retrieve": ("compliance_risk.remediation:read", "compliance_risk.remediation_reads"),
        "create": ("compliance_risk.remediation:create", "compliance_risk.remediation_writes"),
        "partial_update": ("compliance_risk.remediation:update", "compliance_risk.remediation_writes"),
        "destroy": ("compliance_risk.remediation:delete", "compliance_risk.remediation_writes"),
        "transition": ("compliance_risk.remediation:transition", "compliance_risk.remediation_transitions"),
    }
    assert set(REMEDIATION_ACTIONS.keys()) == set(expected.keys())
    for action, (permission, quota_resource) in expected.items():
        requirement = REMEDIATION_ACTIONS[action]
        assert requirement.permission == permission, action
        assert requirement.quota_resource == quota_resource, action
        assert requirement.quota_cost == 1, action


def test_dashboard_and_heatmap_actions_are_pinned_exactly() -> None:
    assert set(DASHBOARD_ACTIONS.keys()) == {"get"}
    requirement = DASHBOARD_ACTIONS["get"]
    assert requirement.permission == "compliance_risk.dashboard:read"
    assert requirement.quota_resource == "compliance_risk.dashboard_reads"
    assert requirement.quota_cost == 1
    assert HEATMAP_ACTIONS is DASHBOARD_ACTIONS


def test_configuration_actions_are_pinned_exactly() -> None:
    expected = {
        "retrieve": ("compliance_risk.configuration:read", "compliance_risk.configuration_reads"),
        "list": ("compliance_risk.configuration:read", "compliance_risk.configuration_reads"),
        "update": ("compliance_risk.configuration:manage", "compliance_risk.configuration_writes"),
        "preview": ("compliance_risk.configuration:manage", "compliance_risk.configuration_previews"),
        "versions": ("compliance_risk.configuration:read", "compliance_risk.configuration_reads"),
        "version_detail": ("compliance_risk.configuration:read", "compliance_risk.configuration_reads"),
        "rollback": ("compliance_risk.configuration:rollback", "compliance_risk.configuration_rollbacks"),
        "export": ("compliance_risk.configuration:read", "compliance_risk.configuration_exports"),
        "import_document": ("compliance_risk.configuration:manage", "compliance_risk.configuration_imports"),
    }
    assert set(CONFIGURATION_ACTIONS.keys()) == set(expected.keys())
    for action, (permission, quota_resource) in expected.items():
        requirement = CONFIGURATION_ACTIONS[action]
        assert requirement.permission == permission, action
        assert requirement.quota_resource == quota_resource, action
        assert requirement.quota_cost == 1, action


def test_job_and_health_actions_are_pinned_exactly() -> None:
    assert set(JOB_ACTIONS.keys()) == {"retrieve"}
    job_requirement = JOB_ACTIONS["retrieve"]
    assert job_requirement.permission == "compliance_risk.dashboard:read"
    assert job_requirement.quota_resource == "compliance_risk.job_reads"
    assert job_requirement.quota_cost == 1

    assert set(HEALTH_ACTIONS.keys()) == {"get"}
    health_requirement = HEALTH_ACTIONS["get"]
    assert health_requirement.permission == "compliance_risk.health:read"
    assert health_requirement.quota_resource == "compliance_risk.health_reads"
    assert health_requirement.quota_cost == 1
