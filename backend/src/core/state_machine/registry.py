"""Named registry and safe declarative loaders for state machines."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Generic, TextIO, TypeVar

import yaml
from django.db import models

from .machine import Guard, StateMachine, StateMachineConfigurationError, TransitionRecorder

ModelT = TypeVar("ModelT", bound=models.Model)


class MachineAlreadyRegisteredError(StateMachineConfigurationError):
    """Raised when registration would silently replace a named machine."""


class MachineNotRegisteredError(LookupError):
    """Raised when a requested state machine is unavailable."""


class StateMachineRegistry(Generic[ModelT]):
    """Thread-safe collection of validated, named state machines."""

    def __init__(self) -> None:
        self._machines: dict[str, StateMachine[Any]] = {}
        self._lock = threading.RLock()

    def register(
        self,
        name: str,
        machine: StateMachine[ModelT],
        *,
        replace: bool = False,
    ) -> StateMachine[ModelT]:
        """Register ``machine`` under ``name`` without implicit replacement."""
        normalised_name = _name(name)
        if not isinstance(machine, StateMachine):
            raise TypeError("machine must be a StateMachine")
        if machine.name is not None and machine.name != normalised_name:
            raise StateMachineConfigurationError(
                f"Machine definition name {machine.name!r} does not match registry name {normalised_name!r}"
            )
        with self._lock:
            if normalised_name in self._machines and not replace:
                raise MachineAlreadyRegisteredError(f"State machine {normalised_name!r} is already registered")
            self._machines[normalised_name] = machine
        return machine

    def unregister(self, name: str) -> StateMachine[Any] | None:
        """Remove and return a machine, primarily for extension lifecycle/tests."""
        with self._lock:
            return self._machines.pop(_name(name), None)

    def get(self, name: str) -> StateMachine[Any]:
        """Return a named machine or fail explicitly."""
        normalised_name = _name(name)
        with self._lock:
            try:
                return self._machines[normalised_name]
            except KeyError as exc:
                raise MachineNotRegisteredError(f"State machine {normalised_name!r} is not registered") from exc

    def names(self) -> tuple[str, ...]:
        """Return registered names in stable order."""
        with self._lock:
            return tuple(sorted(self._machines))

    def load_dict(
        self,
        definitions: Mapping[str, Any],
        *,
        guards: Mapping[str, Guard] | None = None,
        models: Mapping[str, type[models.Model]] | None = None,
        recorders: Mapping[str, TransitionRecorder[Any]] | None = None,
        replace: bool = False,
    ) -> tuple[StateMachine[Any], ...]:
        """Validate and register one or many declarative definitions.

        Accepted roots are a single definition containing ``name`` or a
        ``machines`` mapping/list.  Every definition is validated before any is
        registered, so a malformed file cannot leave a partially loaded registry.
        """
        named_definitions = _normalise_definitions(definitions)
        built: list[tuple[str, StateMachine[Any]]] = []
        for name, definition in named_definitions:
            machine_definition = dict(definition)
            declared_name = machine_definition.setdefault("name", name)
            if declared_name != name:
                raise StateMachineConfigurationError(
                    f"Machine key {name!r} conflicts with definition name {declared_name!r}"
                )
            built.append(
                (
                    name,
                    StateMachine.from_dict(
                        machine_definition,
                        guards=guards,
                        model=(models or {}).get(name),
                        recorder=(recorders or {}).get(name),
                    ),
                )
            )

        with self._lock:
            duplicates = {name for name, _ in built if name in self._machines}
            if duplicates and not replace:
                raise MachineAlreadyRegisteredError(
                    f"State machines already registered: {', '.join(sorted(duplicates))}"
                )
            for name, machine in built:
                self._machines[name] = machine
        return tuple(machine for _, machine in built)

    def load_yaml(
        self,
        source: str | bytes | Path | TextIO,
        *,
        guards: Mapping[str, Guard] | None = None,
        models: Mapping[str, type[models.Model]] | None = None,
        recorders: Mapping[str, TransitionRecorder[Any]] | None = None,
        replace: bool = False,
    ) -> tuple[StateMachine[Any], ...]:
        """Safely load definitions from YAML content, a path, or a text stream."""
        content: str | bytes
        if hasattr(source, "read"):
            content = source.read()
        elif isinstance(source, Path):
            content = source.read_text(encoding="utf-8")
        elif isinstance(source, (str, bytes)):
            content = source
        else:
            raise TypeError("YAML source must be content, pathlib.Path, or a readable text stream")
        try:
            parsed = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise StateMachineConfigurationError(f"Invalid state-machine YAML: {exc}") from exc
        if not isinstance(parsed, Mapping):
            raise StateMachineConfigurationError("State-machine YAML root must be a mapping")
        return self.load_dict(
            parsed,
            guards=guards,
            models=models,
            recorders=recorders,
            replace=replace,
        )


def _name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateMachineConfigurationError("Machine name must be a non-empty string")
    return value.strip()


def _normalise_definitions(definitions: Mapping[str, Any]) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    if not isinstance(definitions, Mapping):
        raise StateMachineConfigurationError("State-machine definitions must be a mapping")
    if "name" in definitions:
        name = _name(definitions["name"])
        return ((name, definitions),)

    root = definitions.get("machines", definitions)
    if isinstance(root, Mapping):
        normalised: list[tuple[str, Mapping[str, Any]]] = []
        for name, definition in root.items():
            normalised_name = _name(name)
            if not isinstance(definition, Mapping):
                raise StateMachineConfigurationError(f"Definition for {normalised_name!r} must be a mapping")
            normalised.append((normalised_name, definition))
        if not normalised:
            raise StateMachineConfigurationError("No state-machine definitions were provided")
        return tuple(normalised)

    if isinstance(root, list):
        normalised = []
        for definition in root:
            if not isinstance(definition, Mapping) or "name" not in definition:
                raise StateMachineConfigurationError("Every machine in a list must be a mapping with a name")
            normalised.append((_name(definition["name"]), definition))
        if not normalised:
            raise StateMachineConfigurationError("No state-machine definitions were provided")
        return tuple(normalised)
    raise StateMachineConfigurationError("'machines' must be a mapping or list")


ORDER_MACHINE_DEFINITION: Mapping[str, Any] = {
    "name": "order",
    "states": ["draft", "confirmed", "fulfilled", "cancelled"],
    "terminal_states": ["fulfilled", "cancelled"],
    "transitions": [
        {"command": "confirm", "from": "draft", "to": "confirmed"},
        {"command": "fulfil", "from": "confirmed", "to": "fulfilled"},
        {"command": "cancel", "from": ["draft", "confirmed"], "to": "cancelled"},
    ],
}

registry: StateMachineRegistry[Any] = StateMachineRegistry()
registry.load_dict(ORDER_MACHINE_DEFINITION)


def register(name: str, machine: StateMachine[ModelT], *, replace: bool = False) -> StateMachine[ModelT]:
    """Register a machine in the process-wide extension registry."""
    return registry.register(name, machine, replace=replace)


def get(name: str) -> StateMachine[Any]:
    """Return a machine from the process-wide extension registry."""
    return registry.get(name)
