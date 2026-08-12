"""Extension registry contract tests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest

from src.modules.ai_agent_management.registries import (
    AgentRunner,
    ExtensionRegistry,
    evaluation_registry,
    runner_registry,
)


def _runner(
    *,
    tenant_id: str,
    execution_id: str,
    task: Mapping[str, Any],
) -> Mapping[str, Any]:
    return {
        "tenant_id": tenant_id,
        "execution_id": execution_id,
        "task": dict(task),
    }


def _other_runner(
    *,
    tenant_id: str,
    execution_id: str,
    task: Mapping[str, Any],
) -> Mapping[str, Any]:
    return {
        "tenant_id": tenant_id,
        "execution_id": execution_id,
        "task": dict(task),
        "other": True,
    }


def test_registry_requires_configured_policy_before_key_use() -> None:
    kind = "agent runner"
    registry: ExtensionRegistry[AgentRunner] = ExtensionRegistry(kind)

    with pytest.raises(RuntimeError) as exc_info:
        registry.get("runner")
    assert str(exc_info.value) == "Extension registry policy is not configured"


def test_registry_configures_positive_key_limit_boundary() -> None:
    kind = "agent runner"
    registry: ExtensionRegistry[AgentRunner] = ExtensionRegistry(kind)

    with pytest.raises(ValueError) as exc_info:
        registry.configure(0)
    assert str(exc_info.value) == "Registry key limit must be positive"

    registry.configure(1)
    registry.register("a", _runner)

    assert registry.require("a") is _runner


def test_registry_normalizes_and_rejects_invalid_keys() -> None:
    registry: ExtensionRegistry[AgentRunner] = ExtensionRegistry(
        "agent runner",
        maximum_key_length=6,
    )

    registry.register("  abc123  ", _runner)

    assert registry.keys() == ("abc123",)
    assert registry.get("abc123") is _runner
    message_start = "Extension key must be a non-empty string"
    message_end = "of at most 6 characters"
    message = f"{message_start} {message_end}"
    with pytest.raises(ValueError) as exc_info:
        registry.register("abcdefg", _runner)
    assert str(exc_info.value) == message
    with pytest.raises(ValueError) as exc_info:
        registry.register("   ", _runner)
    assert str(exc_info.value) == message
    with pytest.raises(ValueError) as exc_info:
        registry.register(cast(str, 42), _runner)
    assert str(exc_info.value) == message


def test_registry_rejects_noncallable_and_duplicate_handlers() -> None:
    registry: ExtensionRegistry[AgentRunner] = ExtensionRegistry(
        "agent runner",
        maximum_key_length=20,
    )

    with pytest.raises(TypeError) as type_error:
        registry.register("runner", cast(AgentRunner, object()))
    assert str(type_error.value) == "agent runner handler must be callable"

    assert registry.register("runner", _runner) is _runner
    assert registry.register("runner", _runner) is _runner
    with pytest.raises(ValueError) as duplicate_error:
        registry.register("runner", _other_runner)
    message = "agent runner 'runner' is already registered"
    assert str(duplicate_error.value) == message


def test_registry_require_and_global_kinds_are_stable() -> None:
    registry: ExtensionRegistry[AgentRunner] = ExtensionRegistry(
        "agent runner",
        maximum_key_length=20,
    )

    with pytest.raises(LookupError) as exc_info:
        registry.require("missing")
    assert str(exc_info.value) == "agent runner 'missing' is unavailable"
    assert runner_registry.kind == "agent runner"
    assert evaluation_registry.kind == "evaluation suite"
