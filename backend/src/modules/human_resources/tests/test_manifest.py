"""Executable parity checks for the Human Resources module contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml
from django.apps import apps as django_apps

from src.core.module_manifest_schema import manifest_validator

from .. import health, serializers
from ..permissions import PERMISSIONS, requirement_for
from ..state_machines import EMPLOYEE_LIFECYCLE_MACHINE, LEAVE_REQUEST_MACHINE
from ..urls import router, urlpatterns


def _manifest() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "manifest.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    manifest_validator.validate(loaded)
    return loaded


def _runtime_endpoint_inventory(canonical_prefix: str) -> list[dict[str, object]]:
    inventory: list[dict[str, object]] = []
    standard_routes = (
        ("list", "GET", False),
        ("create", "POST", False),
        ("retrieve", "GET", True),
        ("partial_update", "PATCH", True),
        ("destroy", "DELETE", True),
    )
    for prefix, viewset_class, _basename in router.registry:
        viewset = viewset_class()
        requirements = viewset_class.access_requirements
        for action_name, method, detail in standard_routes:
            requirement = requirements.get(action_name)
            if requirement is None:
                continue
            if (
                viewset_class.__name__ == "HumanResourcesConfigurationViewSet"
                and action_name == "partial_update"
                and detail
            ):
                # The router synthesizes this route, but the singleton
                # controller explicitly rejects it with HTTP 405.
                continue
            viewset.action = action_name
            suffix = "{id}/" if detail else ""
            inventory.append(
                {
                    "method": method,
                    "path": f"{canonical_prefix}{prefix}/{suffix}",
                    "action": action_name,
                    "viewset": viewset_class.__name__,
                    "serializer": viewset.get_serializer_class().__name__,
                    "permission": requirement.permission,
                }
            )
        for action_method in viewset_class.get_extra_actions():
            action_name = action_method.__name__
            requirement = requirements[action_name]
            viewset.action = action_name
            detail_prefix = "{id}/" if action_method.detail else ""
            for method in action_method.mapping:
                inventory.append(
                    {
                        "method": method.upper(),
                        "path": f"{canonical_prefix}{prefix}/{detail_prefix}{action_method.url_path}/",
                        "action": action_name,
                        "viewset": viewset_class.__name__,
                        "serializer": viewset.get_serializer_class().__name__,
                        "permission": requirement.permission,
                    }
                )
    for pattern in urlpatterns:
        callback = getattr(pattern, "callback", None)
        actions = getattr(callback, "actions", None)
        viewset_class = getattr(callback, "cls", None)
        if not isinstance(actions, dict) or viewset_class is None:
            continue
        viewset = viewset_class()
        requirements = viewset_class.access_requirements
        for method, action_name in actions.items():
            if method == "head":
                continue
            requirement = requirements[action_name]
            viewset.action = action_name
            inventory.append(
                {
                    "method": method.upper(),
                    "path": f"{canonical_prefix}{pattern.pattern}",
                    "action": action_name,
                    "viewset": viewset_class.__name__,
                    "serializer": viewset.get_serializer_class().__name__,
                    "permission": requirement.permission,
                }
            )
    inventory = list({tuple(sorted(endpoint.items())): endpoint for endpoint in inventory}.values())
    return inventory


def test_manifest_declares_every_model_and_referenced_serializer() -> None:
    manifest = _manifest()
    contracts = manifest["metadata"]["api"]["entity_contracts"]
    app_config = django_apps.get_app_config("human_resources")
    runtime_entities = {(model.__name__, model._meta.db_table) for model in app_config.get_models()}
    declared_entities = {(contract["model"], contract["table"]) for contract in contracts}

    assert declared_entities == runtime_entities
    for contract in contracts:
        for field, serializer_name in contract.items():
            if field.endswith("_serializer"):
                assert getattr(serializers, serializer_name).__name__ == serializer_name


def test_manifest_endpoint_inventory_matches_router_serializers_and_permissions() -> None:
    manifest = _manifest()
    api_contract = manifest["metadata"]["api"]
    declared = [
        {key: value for key, value in endpoint.items() if key not in {"availability", "lifecycle_action"}}
        for endpoint in api_contract["endpoint_inventory"]
        if endpoint["viewset"] != "HumanResourcesHealthView"
    ]

    def sort_key(endpoint: dict[str, object]) -> tuple[str, str, str]:
        return (str(endpoint["path"]), str(endpoint["method"]), str(endpoint["action"]))

    assert sorted(declared, key=sort_key) == sorted(
        _runtime_endpoint_inventory(api_contract["canonical_prefix"]),
        key=sort_key,
    )
    assert set(manifest["permissions"]) == set(PERMISSIONS)


def test_manifest_declares_health_endpoint_and_canonical_check_names() -> None:
    manifest = _manifest()
    api_contract = manifest["metadata"]["api"]
    health_endpoints = [
        endpoint for endpoint in api_contract["endpoint_inventory"] if endpoint["viewset"] == "HumanResourcesHealthView"
    ]
    requirement = requirement_for("health", "get")

    assert requirement is not None
    assert health_endpoints == [
        {
            "method": "GET",
            "path": api_contract["health_endpoint"],
            "action": "get",
            "viewset": "HumanResourcesHealthView",
            "serializer": "HumanResourcesHealthReport",
            "permission": requirement.permission,
            "lifecycle_action": False,
        }
    ]
    runtime_checks: list[tuple[str, bool]] = []

    def capture(name: str, _probe: object, *, critical: bool = True) -> health.ReadinessCheck:
        runtime_checks.append((name, critical))
        return health.ReadinessCheck(name, True, "READY", 0.0, critical)

    with patch.object(health, "_run", side_effect=capture):
        health.get_module_health()

    declared_checks = [(check["name"], check["critical"]) for check in manifest["metadata"]["health_checks"]]
    assert declared_checks == runtime_checks
    declared_names = [name for name, _critical in declared_checks]
    assert "transactional_outbox" in declared_names
    assert "async_outbox" not in declared_names


def test_manifest_marks_every_state_machine_command_as_a_lifecycle_action() -> None:
    inventory = _manifest()["metadata"]["api"]["endpoint_inventory"]
    lifecycle_actions = {endpoint["action"] for endpoint in inventory if endpoint["lifecycle_action"]}
    state_machine_commands = {
        edge.command for machine in (EMPLOYEE_LIFECYCLE_MACHINE, LEAVE_REQUEST_MACHINE) for edge in machine.transitions
    }

    assert state_machine_commands <= lifecycle_actions
    assert all(isinstance(endpoint["lifecycle_action"], bool) for endpoint in inventory)
