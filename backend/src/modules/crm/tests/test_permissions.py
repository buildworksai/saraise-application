"""Authorization and signed-manifest contract tests."""

from pathlib import Path

import pytest
import yaml

from src.core.module_manifest_schema import manifest_validator
from src.modules.crm.permissions import (
    ACTION_PERMISSION_MAPS,
    PERMISSIONS,
    PermissionMappingError,
    permission_for_action,
    permission_for_job_command,
)


def test_manifest_permissions_exactly_match_runtime_declarations() -> None:
    manifest_path = Path(__file__).parents[1] / "manifest.yaml"
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert tuple(raw["permissions"]) == PERMISSIONS
    assert manifest_validator.validate(raw).permissions == list(PERMISSIONS)


def test_every_action_mapping_uses_a_declared_permission() -> None:
    mapped = {permission for mapping in ACTION_PERMISSION_MAPS.values() for permission in mapping.values()}
    assert mapped <= set(PERMISSIONS)
    assert permission_for_action("lead", "convert") == "crm.lead:convert"
    assert permission_for_action("opportunity", "close_won") == "crm.opportunity:close"
    assert permission_for_action("activity", "destroy") == "crm.activity:delete"


@pytest.mark.parametrize(
    ("resource", "action"),
    [("lead", "update"), ("opportunity", "update"), ("lead", "undeclared"), ("unknown", "list")],
)
def test_missing_action_mapping_denies_without_fallback(resource: str, action: str) -> None:
    with pytest.raises(PermissionMappingError):
        permission_for_action(resource, action)


def test_special_permissions_are_not_implied_by_crud() -> None:
    required = {
        "crm.lead:convert",
        "crm.lead:score",
        "crm.contact:override_domain",
        "crm.opportunity:close",
        "crm.opportunity:reopen_stage",
        "crm.activity:complete",
        "crm.forecasting:predict",
        "crm.health:read",
    }
    assert required <= set(PERMISSIONS)
    assert permission_for_action("lead", "score") != permission_for_action("lead", "partial_update")
    assert permission_for_action("activity", "destroy") != permission_for_action("activity", "partial_update")


def test_job_status_requires_the_initiating_command_permission() -> None:
    assert permission_for_job_command("crm.score_lead") == "crm.lead:score"
    assert permission_for_job_command("crm.scan_stale_deals") == "crm.opportunity:read"
    assert permission_for_job_command("crm.sync_external_activity") == "crm.activity:create"
    assert permission_for_job_command("crm.acknowledge_sales_order") == "crm.opportunity:close"
    with pytest.raises(PermissionMappingError):
        permission_for_job_command("crm.unknown")
