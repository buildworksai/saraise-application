"""Authorization and signed-manifest contract tests."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from rest_framework.permissions import IsAuthenticated

from src.core.access import RequiresAccess
from src.core.module_manifest_schema import manifest_validator
from src.modules.crm.api import GovernedCRMViewSet
from src.modules.crm.permissions import (
    ACTION_PERMISSION_MAPS,
    PERMISSIONS,
    PermissionMappingError,
    permission_for_action,
    permission_for_job_command,
)


def _manifest() -> dict[str, Any]:
    manifest_path = Path(__file__).parents[1] / "manifest.yaml"
    return yaml.safe_load(manifest_path.read_text(encoding="utf-8"))


def test_manifest_permissions_exactly_match_runtime_declarations() -> None:
    raw = _manifest()
    assert tuple(raw["permissions"]) == PERMISSIONS
    assert manifest_validator.validate(raw).permissions == list(PERMISSIONS)


def test_manifest_enumerates_the_actual_governed_api_surface() -> None:
    metadata = _manifest()["metadata"]
    entries = metadata["api"]["endpoints"]
    paths = [entry["path"] for entry in entries]

    assert len(paths) == len(set(paths))
    assert set(paths) == {
        "/api/v2/crm/leads/",
        "/api/v2/crm/leads/{id}/",
        "/api/v2/crm/leads/{id}/transition/",
        "/api/v2/crm/leads/{id}/convert/",
        "/api/v2/crm/leads/{id}/score/",
        "/api/v2/crm/accounts/",
        "/api/v2/crm/accounts/{id}/",
        "/api/v2/crm/accounts/{id}/hierarchy/",
        "/api/v2/crm/accounts/duplicates/",
        "/api/v2/crm/contacts/",
        "/api/v2/crm/contacts/{id}/",
        "/api/v2/crm/opportunities/",
        "/api/v2/crm/opportunities/{id}/",
        "/api/v2/crm/opportunities/{id}/transition/",
        "/api/v2/crm/opportunities/{id}/close-won/",
        "/api/v2/crm/opportunities/{id}/close-lost/",
        "/api/v2/crm/activities/",
        "/api/v2/crm/activities/{id}/",
        "/api/v2/crm/activities/{id}/complete/",
        "/api/v2/crm/forecasting/pipeline/",
        "/api/v2/crm/forecasting/win-rate/",
        "/api/v2/crm/forecasting/by-stage/",
        "/api/v2/crm/forecasting/predict/",
        "/api/v2/crm/jobs/{id}/",
        "/api/v2/crm/configuration/",
        "/api/v2/crm/configuration/preview/",
        "/api/v2/crm/configuration/versions/",
        "/api/v2/crm/configuration/rollback/",
        "/api/v2/crm/configuration/import/",
        "/api/v2/crm/configuration/export/",
        "/api/v2/crm/health/",
    }
    assert all(entry["methods"] for entry in entries)
    assert all("permissions" in entry or "command_permissions" in entry for entry in entries)


def test_manifest_declares_real_tenant_configuration_and_configured_state_machines() -> None:
    metadata = _manifest()["metadata"]
    configuration = metadata["configuration"]

    assert configuration["model"] == "src.modules.crm.models.CRMConfiguration"
    assert configuration["version_model"] == "src.modules.crm.models.CRMConfigurationVersion"
    assert configuration["audit_model"] == "src.modules.crm.models.CRMConfigurationAudit"
    assert configuration["validation_service"] == "src.modules.crm.services.CRMConfigurationService"
    assert configuration["versioned"] is True
    assert configuration["rollback_to_any_version"] is True
    assert configuration["immutable_audit"] is True
    assert configuration["correlation_id_required"] is True
    assert configuration["ui_route"] == "/crm/configuration"
    assert configuration["api_route"] == "/api/v2/crm/configuration/"
    for machine in ("crm.lead", "crm.opportunity"):
        declaration = metadata["state_machines"][machine]
        assert declaration["tenant_configurable"] is True
        assert declaration["configuration_source"].startswith("configuration.document.")


def test_every_action_mapping_uses_a_declared_permission() -> None:
    mapped = {permission for mapping in ACTION_PERMISSION_MAPS.values() for permission in mapping.values()}
    assert mapped <= set(PERMISSIONS)
    assert permission_for_action("lead", "convert") == "crm.lead:convert"
    assert permission_for_action("opportunity", "close_won") == "crm.opportunity:close"
    with pytest.raises(PermissionMappingError):
        permission_for_action("activity", "destroy")


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
    assert permission_for_action("activity", "complete") != permission_for_action("activity", "partial_update")


@pytest.mark.parametrize("mode", ["development", "self-hosted", "saas"])
def test_crm_viewset_never_bypasses_unified_access_pipeline(settings: object, mode: str) -> None:
    settings.SARAISE_MODE = mode
    permissions = GovernedCRMViewSet().get_permissions()
    assert [type(permission) for permission in permissions] == [IsAuthenticated, RequiresAccess]


def test_job_status_requires_the_initiating_command_permission() -> None:
    assert permission_for_job_command("crm.score_lead") == "crm.lead:score"
    assert permission_for_job_command("crm.scan_stale_deals") == "crm.opportunity:read"
    assert permission_for_job_command("crm.sync_external_activity") == "crm.activity:create"
    assert permission_for_job_command("crm.acknowledge_sales_order") == "crm.opportunity:close"
    with pytest.raises(PermissionMappingError):
        permission_for_job_command("crm.unknown")
