"""Fail-closed route authorization metadata tests."""

from __future__ import annotations

import pytest
from rest_framework.authentication import SessionAuthentication

from ..api import StrictSessionAuthentication
from ..permissions import ACTION_ACCESS, MODULE_ENTITLEMENT, PERMISSIONS, SOD_ACTIONS, access_metadata


EXPECTED_PERMISSIONS = {
    "workflow_automation.workflow:read",
    "workflow_automation.workflow:create",
    "workflow_automation.workflow:update",
    "workflow_automation.workflow:delete",
    "workflow_automation.workflow:publish",
    "workflow_automation.workflow:archive",
    "workflow_automation.instance:read",
    "workflow_automation.instance:start",
    "workflow_automation.instance:cancel",
    "workflow_automation.task:read",
    "workflow_automation.task:complete",
    "workflow_automation.task:reject",
    "workflow_automation.catalog:read",
    "workflow_automation.configuration:read",
    "workflow_automation.configuration:write",
    "workflow_automation.configuration:rollback",
    "workflow_automation.configuration:import",
    "workflow_automation.configuration:export",
    "workflow_automation.health:read",
}


def test_exact_public_permission_contract() -> None:
    assert set(PERMISSIONS) == EXPECTED_PERMISSIONS
    assert MODULE_ENTITLEMENT == "module.workflow_automation"


def test_every_route_action_has_permission_and_quota_metadata() -> None:
    required_actions = {
        "workflow_list",
        "workflow_retrieve",
        "workflow_create",
        "workflow_partial_update",
        "workflow_destroy",
        "workflow_validate",
        "workflow_publish",
        "workflow_archive",
        "workflow_clone",
        "instance_list",
        "instance_retrieve",
        "instance_create",
        "instance_cancel",
        "task_list",
        "task_retrieve",
        "task_complete",
        "task_reject",
        "catalog_actions",
        "catalog_conditions",
        "catalog_subjects",
        "catalog_assignees",
        "catalog_lookup",
        "configuration_list",
        "configuration_update",
        "configuration_preview",
        "configuration_history",
        "configuration_rollback",
        "configuration_import_configuration",
        "configuration_export_configuration",
        "health",
    }
    assert required_actions.issubset(ACTION_ACCESS)
    for action in required_actions:
        permission, quota = access_metadata(action)
        assert permission in EXPECTED_PERMISSIONS
        assert quota.startswith("workflow_automation.")


def test_unknown_action_denies_by_missing_metadata() -> None:
    with pytest.raises(KeyError, match="No access metadata"):
        access_metadata("workflow_unregistered_mutation")


def test_segregation_of_duties_actions_are_explicit() -> None:
    assert set(SOD_ACTIONS) == {
        "workflow_automation.workflow:publish",
        "workflow_automation.workflow:delete",
    }


def test_strict_authentication_uses_production_session_csrf_contract() -> None:
    assert issubclass(StrictSessionAuthentication, SessionAuthentication)
    assert StrictSessionAuthentication().authenticate_header(object()) == "Session"
