"""Executable consistency checks for the MDM module manifest."""

from __future__ import annotations

from pathlib import Path

import yaml
from django.apps import apps

from src.modules.master_data_management import permissions, urls
from src.modules.master_data_management.services import (
    DEDUPLICATION_SCAN_COMMAND,
    QUALITY_SCAN_COMMAND,
)


def _manifest() -> dict[str, object]:
    path = Path(__file__).resolve().parents[1] / "manifest.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_manifest_inventory_exactly_matches_module_models_and_permissions() -> None:
    manifest = _manifest()
    declared_entities = manifest["entities"]
    assert isinstance(declared_entities, list)
    declared_tables = {
        item["table"] for item in declared_entities if isinstance(item, dict)
    }
    model_tables = {
        model._meta.db_table
        for model in apps.get_app_config("master_data_management").get_models()
    }
    assert declared_tables == model_tables
    assert set(manifest["permissions"]) == set(permissions.PERMISSIONS)  # type: ignore[arg-type]


def test_manifest_covers_every_router_prefix_job_and_configured_health_interval() -> None:
    manifest = _manifest()
    endpoints = manifest["endpoints"]
    assert isinstance(endpoints, list)
    paths = {
        item["path"] for item in endpoints if isinstance(item, dict)
    }
    for prefix, _viewset, _basename in urls.router.registry:
        route = f"/api/v2/master-data-management/{prefix}/"
        assert any(
            path == route or str(path).startswith(route) for path in paths
        ), f"manifest omits router prefix {route}"

    assert set(manifest["worker_commands"]) == {  # type: ignore[arg-type]
        QUALITY_SCAN_COMMAND,
        DEDUPLICATION_SCAN_COMMAND,
    }
    health_checks = manifest["health_checks"]
    assert isinstance(health_checks, list)
    assert health_checks
    assert all(
        isinstance(check, dict)
        and check.get("interval_config") == "operational.health_check_interval_seconds"
        and "interval" not in check
        for check in health_checks
    )
