"""Permission catalog and deny-default proof."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml
from rest_framework.permissions import IsAuthenticated

from src.core.access import RequiresAccess

from ..permissions import (
    ACTION_ACCESS,
    PERMISSIONS,
    ActionAccessMixin,
    requirement_for,
)


def test_manifest_and_runtime_permission_catalog_are_exact() -> None:
    manifest = yaml.safe_load((Path(__file__).parents[1] / "manifest.yaml").read_text())
    assert tuple(manifest["permissions"]) == PERMISSIONS
    assert len(PERMISSIONS) == len(set(PERMISSIONS)) == 34


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


def test_requires_access_rejects_missing_metadata_without_calling_pipeline() -> None:
    class ExplodingPipeline:
        def decide(self, *args: object, **kwargs: object) -> object:
            del args, kwargs
            raise AssertionError("pipeline must not run without permission metadata")

    permission = RequiresAccess(pipeline=ExplodingPipeline())  # type: ignore[arg-type]
    request: Any = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))

    assert permission.has_permission(request, SimpleNamespace()) is False
    assert request.access_decision.allowed is False
