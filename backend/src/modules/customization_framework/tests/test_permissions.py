"""Fail-closed action metadata and access-pipeline integration tests."""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace
from unittest.mock import Mock

from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.modules.customization_framework.permissions import (
    ACTION_ACCESS,
    PERMISSIONS,
    AccessRequirement,
    requirement_for,
)


def test_action_access_is_immutable_complete_and_namespaced() -> None:
    assert isinstance(ACTION_ACCESS, MappingProxyType)
    assert ACTION_ACCESS
    assert len(PERMISSIONS) == len(set(PERMISSIONS))
    assert all(
        requirement.permission.startswith("customization_framework.")
        and requirement.entitlement.startswith("customization_framework.")
        and requirement.quota_resource.startswith("customization_framework.")
        and requirement.quota_cost > 0
        for requirement in ACTION_ACCESS.values()
    )


def test_every_required_permission_family_is_declared() -> None:
    expected = {
        "field_definition:read",
        "field_definition:create",
        "field_definition:update",
        "field_definition:delete",
        "field_definition:publish",
        "field_value:read",
        "field_value:write",
        "field_value:delete",
        "field_value:validate",
        "form:read",
        "form:create",
        "form:update",
        "form:delete",
        "form:publish",
        "form:archive",
        "rule:read",
        "rule:create",
        "rule:update",
        "rule:delete",
        "rule:publish",
        "rule:evaluate",
        "execution:read",
        "impact:read",
        "health:read",
    }
    assert {
        permission.removeprefix("customization_framework.") for permission in PERMISSIONS
    } == expected


def test_method_qualified_actions_resolve_distinct_read_and_write_access() -> None:
    read = requirement_for("form", "layout_versions", "GET")
    write = requirement_for("form", "layout_versions", "POST")
    assert isinstance(read, AccessRequirement)
    assert isinstance(write, AccessRequirement)
    assert read.permission == "customization_framework.form:read"
    assert write.permission == "customization_framework.form:update"


def test_missing_action_mapping_denies_by_returning_none() -> None:
    assert requirement_for("field-definition", "put") is None
    assert requirement_for("unknown", "list") is None


def test_rule_evaluation_has_dedicated_quota_resource_and_positive_cost() -> None:
    requirement = requirement_for("rule", "evaluate")
    assert requirement is not None
    assert requirement.permission == "customization_framework.rule:evaluate"
    assert requirement.quota_resource.endswith("rule_evaluations")
    assert requirement.quota_cost >= 1


def test_requires_access_receives_complete_action_declaration() -> None:
    pipeline = Mock()
    pipeline.decide.return_value = SimpleNamespace(allowed=True)
    permission = RequiresAccess(pipeline=pipeline)
    request = SimpleNamespace(
        tenant_id="00000000-0000-0000-0000-000000000001",
        user=SimpleNamespace(is_authenticated=True),
    )
    requirement = ACTION_ACCESS["field-definition.list"]
    view = SimpleNamespace(
        required_permission=requirement.permission,
        required_entitlement=requirement.entitlement,
        quota_resource=requirement.quota_resource,
        quota_cost=requirement.quota_cost,
    )
    assert permission.has_permission(request, view) is True
    pipeline.decide.assert_called_once()


def test_governed_viewsets_compose_authentication_and_access_permissions() -> None:
    from src.modules.customization_framework.api import GovernedTenantViewSet

    assert tuple(GovernedTenantViewSet.permission_classes) == (
        IsAuthenticated,
        RequiresAccess,
    )
