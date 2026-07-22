"""Prevent drift between the process-mining manifest and runtime inventory."""

from pathlib import Path
import re

import pytest
import yaml

from src.modules.process_mining import models
from src.modules.process_mining.permissions import PERMISSIONS
from src.modules.process_mining.urls import router


@pytest.fixture(scope="module")
def manifest():
    path = Path(__file__).resolve().parents[1] / "manifest.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_manifest_declares_every_model_and_permission(manifest):
    def entity_name(model):
        return re.sub(r"(?<!^)(?=[A-Z])", "_", model.__name__).lower()

    model_entities = {
        entity_name(model)
        for model in models.__dict__.values()
        if isinstance(model, type)
        and hasattr(model, "_meta")
        and model._meta.app_label == "process_mining"
        and not model._meta.abstract
    }
    assert set(manifest["metadata"]["entities"]) == model_entities
    assert set(manifest["permissions"]) == set(PERMISSIONS)


def test_manifest_declares_every_router_prefix_and_health(manifest):
    paths = {entry["path"] for entry in manifest["metadata"]["endpoints"]}
    for prefix, _viewset, _basename in router.registry:
        assert any(path.startswith(f"/api/v2/process-mining/{prefix}/") for path in paths), prefix
    assert "/api/v2/process-mining/health/" in paths
    for entry in manifest["metadata"]["endpoints"]:
        assert entry.get("methods"), entry
        assert entry.get("permission") or entry.get("permissions"), entry
