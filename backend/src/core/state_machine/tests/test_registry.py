"""Declarative registry tests."""

from __future__ import annotations

from io import StringIO

import pytest

from src.core.state_machine import StateMachine, StateMachineConfigurationError, Transition, get, register
from src.core.state_machine.registry import (
    MachineAlreadyRegisteredError,
    MachineNotRegisteredError,
    StateMachineRegistry,
    registry,
)


def machine(name: str = "document") -> StateMachine:
    return StateMachine(
        name=name,
        states=("draft", "published"),
        terminal_states=("published",),
        transitions=(Transition("publish", "draft", "published"),),
    )


def test_builtin_order_machine_is_registered() -> None:
    order_machine = registry.get("order")
    assert order_machine.allowed_commands("draft") == ("cancel", "confirm")
    assert order_machine.allowed_commands("fulfilled") == ()


def test_register_get_names_and_unregister() -> None:
    local = StateMachineRegistry()
    registered = local.register("document", machine())

    assert local.get("document") is registered
    assert local.names() == ("document",)
    assert local.unregister("document") is registered
    assert local.unregister("document") is None
    with pytest.raises(MachineNotRegisteredError, match="not registered"):
        local.get("document")


def test_duplicate_registration_requires_explicit_replacement() -> None:
    local = StateMachineRegistry()
    original = local.register("document", machine())
    replacement = machine()

    with pytest.raises(MachineAlreadyRegisteredError, match="already registered"):
        local.register("document", replacement)
    assert local.get("document") is original
    assert local.register("document", replacement, replace=True) is replacement


def test_registry_name_must_match_definition() -> None:
    local = StateMachineRegistry()
    with pytest.raises(StateMachineConfigurationError, match="does not match"):
        local.register("invoice", machine("document"))


def test_yaml_mapping_loads_named_machines_and_resolves_guards() -> None:
    local = StateMachineRegistry()

    def ready(document: object) -> bool:
        return document is not None

    loaded = local.load_yaml(
        StringIO("""
            machines:
              document:
                states: [draft, published]
                terminal_states: [published]
                transitions:
                  - command: publish
                    from: draft
                    to: published
                    guards: [ready]
              invoice:
                state_field: phase
                history_field: phase_history
                states: [open, paid]
                terminal_states: [paid]
                transitions:
                  settle:
                    from: open
                    to: paid
            """),
        guards={"ready": ready},
    )

    assert len(loaded) == 2
    assert local.names() == ("document", "invoice")
    assert local.get("invoice").state_field == "phase"


def test_single_definition_and_machine_list_are_supported() -> None:
    local = StateMachineRegistry()
    local.load_dict(
        {
            "name": "document",
            "states": ["draft", "published"],
            "transitions": [{"command": "publish", "from": "draft", "to": "published"}],
        }
    )
    loaded = local.load_dict(
        {
            "machines": [
                {
                    "name": "invoice",
                    "states": ["open", "paid"],
                    "transitions": [{"command": "pay", "from": "open", "to": "paid"}],
                }
            ]
        }
    )
    assert len(loaded) == 1
    assert local.names() == ("document", "invoice")


def test_bulk_load_is_atomic_at_registry_level() -> None:
    local = StateMachineRegistry()
    with pytest.raises(StateMachineConfigurationError, match="not registered"):
        local.load_dict(
            {
                "machines": {
                    "valid": {
                        "states": ["a", "b"],
                        "transitions": [{"command": "go", "from": "a", "to": "b"}],
                    },
                    "invalid": {
                        "states": ["a", "b"],
                        "transitions": [{"command": "go", "from": "a", "to": "b", "guards": ["missing"]}],
                    },
                }
            }
        )
    assert local.names() == ()


@pytest.mark.parametrize(
    "definition",
    [
        {},
        {"machines": []},
        {"machines": {"document": "not-a-mapping"}},
        {"machines": [{"states": ["a"]}]},
        {"machines": "not-a-collection"},
    ],
)
def test_malformed_registry_roots_fail(definition: dict) -> None:
    with pytest.raises(StateMachineConfigurationError):
        StateMachineRegistry().load_dict(definition)


def test_invalid_yaml_fails_explicitly() -> None:
    with pytest.raises(StateMachineConfigurationError, match="Invalid state-machine YAML"):
        StateMachineRegistry().load_yaml("machines: [unterminated")
    with pytest.raises(StateMachineConfigurationError, match="root must be a mapping"):
        StateMachineRegistry().load_yaml("- document")


def test_yaml_path_and_bytes_are_supported(tmp_path) -> None:
    definition = b"""
    name: document
    states: [draft, published]
    transitions:
      - {command: publish, from: draft, to: published}
    """
    path = tmp_path / "state-machines.yaml"
    path.write_bytes(definition)

    from_path = StateMachineRegistry()
    from_path.load_yaml(path)
    from_bytes = StateMachineRegistry()
    from_bytes.load_yaml(definition)

    assert from_path.names() == from_bytes.names() == ("document",)


def test_global_registry_helpers_delegate_without_fabricating_results() -> None:
    candidate = machine("test-global-document")
    try:
        assert register("test-global-document", candidate) is candidate
        assert get("test-global-document") is candidate
    finally:
        registry.unregister("test-global-document")


def test_registry_rejects_invalid_types_names_and_conflicts() -> None:
    local = StateMachineRegistry()
    with pytest.raises(TypeError, match="must be a StateMachine"):
        local.register("document", object())
    with pytest.raises(StateMachineConfigurationError, match="non-empty"):
        local.get(" ")
    with pytest.raises(TypeError, match="YAML source"):
        local.load_yaml(object())
    with pytest.raises(StateMachineConfigurationError, match="conflicts"):
        local.load_dict(
            {
                "machines": {
                    "document": {
                        "name": "invoice",
                        "states": ["draft", "published"],
                        "transitions": [{"command": "publish", "from": "draft", "to": "published"}],
                    }
                }
            }
        )


def test_bulk_duplicate_load_can_only_replace_explicitly() -> None:
    local = StateMachineRegistry()
    definition = {
        "name": "document",
        "states": ["draft", "published"],
        "transitions": [{"command": "publish", "from": "draft", "to": "published"}],
    }
    original = local.load_dict(definition)[0]
    with pytest.raises(MachineAlreadyRegisteredError, match="already registered"):
        local.load_dict(definition)
    replacement = local.load_dict(definition, replace=True)[0]
    assert replacement is not original
    assert local.get("document") is replacement
