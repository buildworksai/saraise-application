from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from src.core.resilience.circuit_breaker import CircuitBreakerError
from src.modules.backup_disaster_recovery import api, health, models, serializers
from src.modules.backup_disaster_recovery.adapter_registry import (
    ProviderInvocationExecutor,
    ProviderTimeoutError,
    ResiliencePolicy,
    _active_policy,
)
from src.modules.backup_disaster_recovery.urls import router, urlpatterns


def _manifest() -> dict[str, object]:
    path = Path(__file__).parents[1] / "manifest.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_manifest_inventory_matches_models_routes_serializers_and_permissions() -> None:
    manifest = _manifest()
    entities = manifest["entities"]
    assert isinstance(entities, list)
    declared_models = {str(item["model"]).split(".")[-1] for item in entities}
    expected_models = {
        "RecoveryPoint",
        "RecoveryPointEvidence",
        "DRRunbook",
        "RunbookStep",
        "DRExercise",
        "RestoreRun",
        "DRStepExecution",
        "BDRConfiguration",
        "BDRConfigurationVersion",
    }
    assert declared_models == expected_models
    assert all(hasattr(models, name) for name in declared_models)
    assert all(
        hasattr(serializers, serializer_name) for entity in entities for serializer_name in entity["serializers"]
    )

    registered = {viewset.__name__: prefix for prefix, viewset, _ in router.registry}
    endpoints = manifest["endpoints"]
    assert isinstance(endpoints, list)
    declared_viewsets = {str(item["viewset"]): item for item in endpoints if "viewset" in item}
    assert set(declared_viewsets) == set(registered)
    for viewset_name, endpoint in declared_viewsets.items():
        viewset = getattr(api, viewset_name)
        relative_route = str(endpoint["route"]).removeprefix("/api/v2/backup-disaster-recovery/").strip("/")
        assert relative_route == registered[viewset_name]
        assert set(str(method).lower() for method in endpoint["methods"]) <= set(viewset.http_method_names)
        permissions = endpoint["permissions"]
        assert isinstance(permissions, dict)
        assert permissions == {action: rule.permission for action, rule in viewset.access_map.items()}
        for serializer_name in endpoint["serializers"]:
            assert hasattr(serializers, serializer_name)
        for action in endpoint.get("actions", []):
            assert hasattr(serializers, action["serializer"])

    health_endpoint = next(item for item in endpoints if item["name"] == "health")
    assert hasattr(health, str(health_endpoint["view"]))
    assert hasattr(health, str(health_endpoint["serializers"][0]))
    assert any(getattr(pattern, "name", None) == "health_check" for pattern in urlpatterns)
    assert health.BDRHealthView.required_permission == "backup_disaster_recovery.health:read"


def _policy(**overrides: object) -> ResiliencePolicy:
    values: dict[str, object] = {
        "timeout_seconds": 0.1,
        "max_attempts": 3,
        "initial_backoff_seconds": 0.001,
        "max_backoff_seconds": 0.002,
        "jitter_seconds": 0.001,
        "circuit_failure_threshold": 2,
        "circuit_reset_seconds": 60.0,
        "checksum_chunk_bytes": 1024,
        "local_filesystem_restore_modes": frozenset({"full"}),
    }
    values.update(overrides)
    return ResiliencePolicy(**values)  # type: ignore[arg-type]


def test_provider_executor_retries_with_a_bound_and_returns_real_result(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.modules.backup_disaster_recovery.adapter_registry._policy_for",
        lambda tenant_id: _policy(),
    )
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise OSError("transient")
        return "provider-result"

    result = ProviderInvocationExecutor().execute(uuid4(), "catalog.status", operation)
    assert result == "provider-result"
    assert attempts == 3


def test_provider_executor_propagates_validated_policy_into_invocation_thread(monkeypatch) -> None:
    expected = _policy(checksum_chunk_bytes=2048)
    monkeypatch.setattr(
        "src.modules.backup_disaster_recovery.adapter_registry._policy_for",
        lambda tenant_id: expected,
    )
    observed = ProviderInvocationExecutor().execute(
        uuid4(),
        "storage.checksum",
        _active_policy.get,
    )
    assert observed == expected


def test_provider_executor_times_out_and_opens_its_circuit(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.modules.backup_disaster_recovery.adapter_registry._policy_for",
        lambda tenant_id: _policy(
            timeout_seconds=0.001,
            max_attempts=1,
            circuit_failure_threshold=1,
        ),
    )
    executor = ProviderInvocationExecutor()
    tenant_id = uuid4()
    with pytest.raises(ProviderTimeoutError):
        executor.execute(tenant_id, "storage.restore", lambda: time.sleep(0.05))
    with pytest.raises(CircuitBreakerError):
        executor.execute(tenant_id, "storage.restore", lambda: "must-not-run")
