"""Executable proof that manifest claims cannot drift from runtime policy."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from django.apps import apps as django_apps
from django.core.exceptions import ImproperlyConfigured

from src.modules.blockchain_traceability import apps as module_apps
from src.modules.blockchain_traceability.apps import validate_manifest_runtime_contract
from src.modules.blockchain_traceability.permissions import PERMISSIONS, SOD_ACTIONS
from src.modules.blockchain_traceability.urls import STANDALONE_ENDPOINTS, router


@pytest.fixture
def manifest_data() -> dict[str, object]:
    path = Path(module_apps.__file__).with_name("manifest.yaml")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _install_manifest(monkeypatch: pytest.MonkeyPatch, data: dict[str, object]) -> None:
    rendered = yaml.safe_dump(data, sort_keys=False)
    monkeypatch.setattr(module_apps.Path, "read_text", lambda self, encoding=None: rendered)


def test_manifest_contract_matches_every_runtime_registration(manifest_data) -> None:
    metadata = manifest_data["metadata"]
    assert isinstance(metadata, dict)

    assert set(manifest_data["permissions"]) == set(PERMISSIONS)
    declared_pairs = tuple(tuple(pair["actions"]) for pair in metadata["sod_pairs"])
    assert declared_pairs == SOD_ACTIONS
    assert tuple(manifest_data["sod_actions"]) == tuple(action for pair in SOD_ACTIONS for action in pair)
    assert manifest_data["ai_tools"] == []

    app_config = django_apps.get_app_config("blockchain_traceability")
    assert set(metadata["entities"]) == {model._meta.db_table for model in app_config.get_models()}
    declared_router = {
        endpoint["prefix"]: (endpoint["basename"], endpoint["viewset"])
        for endpoint in metadata["endpoints"]
        if endpoint["registration"] == "router"
    }
    assert declared_router == {prefix: (basename, viewset.__name__) for prefix, viewset, basename in router.registry}
    declared_paths = {
        endpoint["route"]: endpoint["name"] for endpoint in metadata["endpoints"] if endpoint["registration"] == "path"
    }
    assert declared_paths == STANDALONE_ENDPOINTS
    validate_manifest_runtime_contract(app_config)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda data: data["metadata"]["sod_pairs"][0].__setitem__(
                "actions",
                ["blockchain_traceability.network:manage", "blockchain_traceability.credential:revoke"],
            ),
            "SoD pairs",
        ),
        (
            lambda data: data["metadata"]["entities"].append("blockchain_traceability_phantom"),
            "entities",
        ),
        (
            lambda data: data["metadata"]["endpoints"][0].__setitem__("basename", "wrong"),
            "router endpoints",
        ),
        (
            lambda data: data.__setitem__("ai_tools", ["blockchain_traceability.unregistered"]),
            "AI tools",
        ),
    ],
)
def test_startup_validation_fails_closed_on_manifest_drift(
    monkeypatch: pytest.MonkeyPatch,
    manifest_data,
    mutation,
    message: str,
) -> None:
    altered = deepcopy(manifest_data)
    mutation(altered)
    _install_manifest(monkeypatch, altered)

    with pytest.raises(ImproperlyConfigured, match=message):
        validate_manifest_runtime_contract(django_apps.get_app_config("blockchain_traceability"))


def test_startup_validation_rejects_permission_policy_drift(monkeypatch, manifest_data) -> None:
    altered = deepcopy(manifest_data)
    altered["permissions"].remove(PERMISSIONS[-1])
    _install_manifest(monkeypatch, altered)

    with pytest.raises(ImproperlyConfigured, match="permissions"):
        validate_manifest_runtime_contract(django_apps.get_app_config("blockchain_traceability"))
