"""Transactional command authority for Django model state transitions.

The state machine deliberately owns both validation and mutation.  Adopting
aggregates expose a state field and a JSON transition-history field (or provide
another :class:`TransitionRecorder`); callers never assign the state directly.
"""

from __future__ import annotations

import inspect
from collections import defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generic, Protocol, TypeVar, cast

from django.db import models, transaction

ModelT = TypeVar("ModelT", bound=models.Model)
RecorderModelT = TypeVar("RecorderModelT", bound=models.Model, contravariant=True)
Guard = Callable[..., bool]


class StateMachineError(RuntimeError):
    """Base class for state-machine failures."""


class StateMachineConfigurationError(StateMachineError, ValueError):
    """Raised when a machine definition cannot be executed safely."""


class UnknownCommandError(StateMachineError):
    """Raised when no transition declares the requested command."""


class IllegalTransitionError(StateMachineError):
    """Raised when a command is not legal from the aggregate's current state."""


class TerminalStateError(IllegalTransitionError):
    """Raised when a non-idempotent command targets a terminal aggregate."""


class GuardFailedError(IllegalTransitionError):
    """Raised when a transition precondition rejects the command."""


class IdempotencyConflictError(StateMachineError):
    """Raised when a transition key is reused for a different command."""


@dataclass(frozen=True, slots=True)
class Transition:
    """One command-controlled edge in a state graph."""

    command: str
    source: str
    target: str
    guards: tuple[Guard, ...] = ()


@dataclass(frozen=True, slots=True)
class TransitionRecord:
    """Immutable audit value written for every successful transition."""

    transition_key: str
    command: str
    from_state: str
    to_state: str
    occurred_at: str
    metadata: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSONField-compatible representation."""
        return {
            "transition_key": self.transition_key,
            "command": self.command,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "occurred_at": self.occurred_at,
            "metadata": dict(self.metadata),
        }


class TransitionRecorder(Protocol[RecorderModelT]):
    """Persistence extension point for transition audit records.

    Implementations execute inside the same transaction and while the aggregate
    row is locked.  A paid module can therefore write to its own append-only
    transition table without changing the command engine.
    """

    def find(self, aggregate: RecorderModelT, transition_key: str) -> TransitionRecord | None:
        """Return the existing record for ``transition_key``, if one exists."""

    def record(self, aggregate: RecorderModelT, record: TransitionRecord) -> None:
        """Persist or stage a new transition record."""

    def aggregate_update_fields(self) -> Collection[str]:
        """Return aggregate fields changed by :meth:`record`."""


class JSONFieldTransitionRecorder(Generic[ModelT]):
    """Store append-only transition records in a JSON list on the aggregate."""

    def __init__(self, field_name: str = "transition_history") -> None:
        self.field_name = _required_name(field_name, "history field")

    def _history(self, aggregate: ModelT) -> list[dict[str, Any]]:
        if not hasattr(aggregate, self.field_name):
            raise StateMachineConfigurationError(
                f"{aggregate._meta.label} has no {self.field_name!r} field; "
                "configure history_field or a TransitionRecorder"
            )
        value = getattr(aggregate, self.field_name)
        if not isinstance(value, list):
            raise StateMachineConfigurationError(f"{aggregate._meta.label}.{self.field_name} must contain a JSON list")
        if not all(isinstance(item, dict) for item in value):
            raise StateMachineConfigurationError(
                f"{aggregate._meta.label}.{self.field_name} contains a non-object transition record"
            )
        return cast(list[dict[str, Any]], value)

    def find(self, aggregate: ModelT, transition_key: str) -> TransitionRecord | None:
        matches = [item for item in self._history(aggregate) if item.get("transition_key") == transition_key]
        if len(matches) > 1:
            raise StateMachineConfigurationError(
                f"Duplicate transition key {transition_key!r} exists on {aggregate._meta.label} {aggregate.pk}"
            )
        if not matches:
            return None
        item = matches[0]
        try:
            metadata = item.get("metadata", {})
            if not isinstance(metadata, Mapping):
                raise TypeError("metadata is not an object")
            return TransitionRecord(
                transition_key=str(item["transition_key"]),
                command=str(item["command"]),
                from_state=str(item["from_state"]),
                to_state=str(item["to_state"]),
                occurred_at=str(item["occurred_at"]),
                metadata=dict(metadata),
            )
        except (KeyError, TypeError) as exc:
            raise StateMachineConfigurationError(
                f"Malformed transition record for key {transition_key!r} on " f"{aggregate._meta.label} {aggregate.pk}"
            ) from exc

    def record(self, aggregate: ModelT, record: TransitionRecord) -> None:
        # Copy before appending so a failed transaction cannot mutate a model
        # instance's previously loaded list by alias.
        history = list(self._history(aggregate))
        history.append(record.as_dict())
        setattr(aggregate, self.field_name, history)

    def aggregate_update_fields(self) -> Collection[str]:
        return (self.field_name,)


TransitionInput = Transition | Mapping[str, Any]


class StateMachine(Generic[ModelT]):
    """A declarative, guarded state graph for one Django aggregate type.

    ``apply`` accepts either ``apply(instance, command, ...)`` or
    ``apply(command, aggregate=instance, ...)``.  A model may instead be bound
    at construction and addressed by ``aggregate_id``.  In every form, the
    stored row is re-read with ``select_for_update`` before any decision.
    """

    def __init__(
        self,
        *,
        states: Iterable[str],
        transitions: Iterable[TransitionInput] | Mapping[Any, Any],
        terminal_states: Iterable[str] = (),
        state_field: str = "status",
        history_field: str = "transition_history",
        guards: Mapping[str, Guard] | None = None,
        model: type[ModelT] | None = None,
        recorder: TransitionRecorder[ModelT] | None = None,
        name: str | None = None,
    ) -> None:
        self.name = _required_name(name, "machine name") if name is not None else None
        self.state_field = _required_name(state_field, "state field")
        self.model = model
        self.recorder: TransitionRecorder[ModelT] = recorder or JSONFieldTransitionRecorder(history_field)
        self.states = frozenset(_normalise_states(states))
        if not self.states:
            raise StateMachineConfigurationError("A state machine must declare at least one state")

        self.terminal_states = frozenset(_normalise_states(terminal_states))
        unknown_terminals = self.terminal_states - self.states
        if unknown_terminals:
            raise StateMachineConfigurationError(
                f"Terminal states are not declared states: {', '.join(sorted(unknown_terminals))}"
            )

        parsed = _parse_transitions(transitions, guards or {})
        if not parsed:
            raise StateMachineConfigurationError("A state machine must declare at least one transition")

        by_command: dict[str, list[Transition]] = defaultdict(list)
        seen_edges: set[tuple[str, str]] = set()
        for edge in parsed:
            if edge.source not in self.states or edge.target not in self.states:
                raise StateMachineConfigurationError(
                    f"Transition {edge.command!r} references undeclared edge " f"{edge.source!r} -> {edge.target!r}"
                )
            if edge.source in self.terminal_states:
                raise StateMachineConfigurationError(
                    f"Terminal state {edge.source!r} cannot have outgoing transition {edge.command!r}"
                )
            identity = (edge.command, edge.source)
            if identity in seen_edges:
                raise StateMachineConfigurationError(
                    f"Command {edge.command!r} is ambiguous from state {edge.source!r}"
                )
            seen_edges.add(identity)
            by_command[edge.command].append(edge)

        self.transitions = tuple(parsed)
        self._by_command = {command: tuple(edges) for command, edges in by_command.items()}

    @classmethod
    def from_dict(
        cls,
        definition: Mapping[str, Any],
        *,
        guards: Mapping[str, Guard] | None = None,
        model: type[ModelT] | None = None,
        recorder: TransitionRecorder[ModelT] | None = None,
    ) -> "StateMachine[ModelT]":
        """Build and validate a machine from a JSON/YAML-compatible mapping."""
        if not isinstance(definition, Mapping):
            raise StateMachineConfigurationError("Machine definition must be a mapping")
        allowed_keys = {
            "name",
            "states",
            "transitions",
            "terminal_states",
            "state_field",
            "history_field",
        }
        unknown_keys = set(definition) - allowed_keys
        if unknown_keys:
            raise StateMachineConfigurationError(
                f"Unknown machine definition keys: {', '.join(sorted(map(str, unknown_keys)))}"
            )
        try:
            states = definition["states"]
            transitions = definition["transitions"]
        except KeyError as exc:
            raise StateMachineConfigurationError(f"Machine definition is missing {exc.args[0]!r}") from exc
        if isinstance(states, (str, bytes)):
            raise StateMachineConfigurationError("states must be a sequence, not a string")
        if not isinstance(transitions, (Mapping, Iterable)) or isinstance(transitions, (str, bytes)):
            raise StateMachineConfigurationError("transitions must be a mapping or sequence")
        return cls(
            name=definition.get("name"),
            states=states,
            transitions=transitions,
            terminal_states=definition.get("terminal_states", ()),
            state_field=definition.get("state_field", "status"),
            history_field=definition.get("history_field", "transition_history"),
            guards=guards,
            model=model,
            recorder=recorder,
        )

    def allowed_commands(self, state: str) -> tuple[str, ...]:
        """Return deterministic command names legal from ``state``."""
        normalised_state = _required_name(state, "state")
        if normalised_state not in self.states:
            raise StateMachineConfigurationError(f"Unknown state {normalised_state!r}")
        return tuple(sorted(edge.command for edge in self.transitions if edge.source == normalised_state))

    def apply(
        self,
        aggregate_or_command: ModelT | str,
        command_or_aggregate: str | ModelT | None = None,
        *,
        aggregate: ModelT | None = None,
        aggregate_id: Any | None = None,
        tenant_id: Any | None = None,
        transition_key: str,
        context: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ModelT:
        """Apply one guarded transition atomically and return the locked row.

        A repeated transition key for the same command returns the current
        aggregate without another mutation or audit record.  Reusing a key for
        another command is rejected explicitly.
        """
        command, supplied_aggregate = self._resolve_call(
            aggregate_or_command,
            command_or_aggregate,
            aggregate,
        )
        key = _required_name(transition_key, "transition key")
        guard_context = _mapping_copy(context, "context")
        audit_metadata = _mapping_copy(metadata, "metadata")

        model = self._resolve_model(supplied_aggregate)
        lookup = self._lock_lookup(model, supplied_aggregate, aggregate_id, tenant_id)

        with transaction.atomic():
            locked = model._default_manager.select_for_update().get(**lookup)
            existing = self.recorder.find(locked, key)
            if existing is not None:
                if existing.command != command:
                    raise IdempotencyConflictError(
                        f"Transition key {key!r} already belongs to command {existing.command!r}"
                    )
                self._synchronise_instance(supplied_aggregate, locked)
                return locked

            current_state = self._current_state(locked)
            if current_state in self.terminal_states:
                raise TerminalStateError(
                    f"{model._meta.label} {locked.pk} is immutable in terminal state {current_state!r}"
                )

            edges = self._by_command.get(command)
            if edges is None:
                raise UnknownCommandError(f"Machine {self.name or '<unnamed>'!r} has no command {command!r}")
            edge = next((candidate for candidate in edges if candidate.source == current_state), None)
            if edge is None:
                raise IllegalTransitionError(
                    f"Command {command!r} cannot transition {model._meta.label} {locked.pk} "
                    f"from state {current_state!r}"
                )

            self._check_guards(edge, locked, guard_context)
            record = TransitionRecord(
                transition_key=key,
                command=command,
                from_state=current_state,
                to_state=edge.target,
                occurred_at=datetime.now(timezone.utc).isoformat(),
                metadata=audit_metadata,
            )
            setattr(locked, self.state_field, edge.target)
            self.recorder.record(locked, record)
            update_fields = {self.state_field, *self.recorder.aggregate_update_fields()}
            locked.save(update_fields=sorted(update_fields))

            self._synchronise_instance(supplied_aggregate, locked)
            return locked

    def _resolve_call(
        self,
        first: ModelT | str,
        second: str | ModelT | None,
        keyword_aggregate: ModelT | None,
    ) -> tuple[str, ModelT | None]:
        if isinstance(first, str):
            command = _required_name(first, "command")
            positional_aggregate = None if second is None else cast(ModelT, second)
            if isinstance(second, str):
                raise TypeError("When the first argument is a command, the second argument must be an aggregate")
        else:
            positional_aggregate = first
            if not isinstance(second, str):
                raise TypeError("apply(instance, command, ...) requires a command string")
            command = _required_name(second, "command")

        if positional_aggregate is not None and keyword_aggregate is not None:
            raise TypeError("aggregate was supplied more than once")
        resolved_aggregate = keyword_aggregate if keyword_aggregate is not None else positional_aggregate
        if resolved_aggregate is not None and not isinstance(resolved_aggregate, models.Model):
            raise TypeError("aggregate must be a Django model instance")
        return command, resolved_aggregate

    def _resolve_model(self, aggregate: ModelT | None) -> type[ModelT]:
        if aggregate is None:
            if self.model is None:
                raise StateMachineConfigurationError(
                    "No aggregate supplied and this state machine is not bound to a model"
                )
            return self.model
        aggregate_model = type(aggregate)
        if self.model is not None and aggregate_model is not self.model:
            raise StateMachineConfigurationError(
                f"Machine expects {self.model._meta.label}, not {aggregate_model._meta.label}"
            )
        return aggregate_model

    def _lock_lookup(
        self,
        model: type[ModelT],
        aggregate: ModelT | None,
        aggregate_id: Any | None,
        tenant_id: Any | None,
    ) -> dict[str, Any]:
        if aggregate is not None:
            # UUID primary keys commonly receive a value before their first
            # save, so ``pk is None`` alone cannot identify an unsaved row.
            if aggregate._state.adding or aggregate.pk is None:
                raise StateMachineConfigurationError("Cannot transition an unsaved aggregate")
            if aggregate_id is not None and not _identifiers_equal(aggregate.pk, aggregate_id):
                raise StateMachineConfigurationError("aggregate and aggregate_id identify different rows")
            resolved_id = aggregate.pk
            instance_tenant = getattr(aggregate, "tenant_id", None)
            if (
                tenant_id is not None
                and instance_tenant is not None
                and not _identifiers_equal(tenant_id, instance_tenant)
            ):
                raise StateMachineConfigurationError("aggregate and tenant_id identify different tenants")
            resolved_tenant = instance_tenant if tenant_id is None else tenant_id
        else:
            if aggregate_id is None:
                raise StateMachineConfigurationError("aggregate_id is required when no aggregate is supplied")
            resolved_id = aggregate_id
            resolved_tenant = tenant_id

        lookup = {"pk": resolved_id}
        field_names = {field.name for field in model._meta.get_fields()}
        if "tenant_id" in field_names:
            if resolved_tenant is None:
                raise StateMachineConfigurationError(
                    f"tenant_id is required to transition tenant-scoped {model._meta.label}"
                )
            lookup["tenant_id"] = resolved_tenant
        return lookup

    def _current_state(self, aggregate: ModelT) -> str:
        if not hasattr(aggregate, self.state_field):
            raise StateMachineConfigurationError(
                f"{aggregate._meta.label} has no configured state field {self.state_field!r}"
            )
        state = str(getattr(aggregate, self.state_field))
        if state not in self.states:
            raise StateMachineConfigurationError(
                f"{aggregate._meta.label} {aggregate.pk} contains undeclared state {state!r}"
            )
        return state

    def _check_guards(self, edge: Transition, aggregate: ModelT, context: Mapping[str, Any]) -> None:
        for guard in edge.guards:
            try:
                accepted = _invoke_guard(guard, aggregate, context)
            except GuardFailedError:
                raise
            except Exception as exc:
                raise GuardFailedError(f"Guard {_callable_name(guard)!r} errored for command {edge.command!r}") from exc
            if accepted is not True:
                raise GuardFailedError(
                    f"Guard {_callable_name(guard)!r} rejected command {edge.command!r} " f"from state {edge.source!r}"
                )

    def _synchronise_instance(self, supplied: ModelT | None, locked: ModelT) -> None:
        if supplied is None or supplied is locked:
            return
        setattr(supplied, self.state_field, getattr(locked, self.state_field))
        for field_name in self.recorder.aggregate_update_fields():
            setattr(supplied, field_name, getattr(locked, field_name))


def _required_name(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise StateMachineConfigurationError(f"{label} must be a string")
    normalised = value.strip()
    if not normalised:
        raise StateMachineConfigurationError(f"{label} must not be empty")
    return normalised


def _normalise_states(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise StateMachineConfigurationError("states must be an iterable of names, not a string")
    normalised = tuple(_required_name(value, "state") for value in values)
    if len(normalised) != len(set(normalised)):
        raise StateMachineConfigurationError("State names must be unique")
    return normalised


def _mapping_copy(value: Mapping[str, Any] | None, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return dict(value)


def _identifiers_equal(left: Any, right: Any) -> bool:
    """Compare UUID-like identifiers without weakening arbitrary primary keys."""
    return left == right or str(left) == str(right)


def _parse_transitions(
    definitions: Iterable[TransitionInput] | Mapping[Any, Any],
    guards: Mapping[str, Guard],
) -> tuple[Transition, ...]:
    if isinstance(definitions, Mapping):
        items: Sequence[Any] = tuple(_expand_transition_mapping(definitions))
    elif isinstance(definitions, (str, bytes)):
        raise StateMachineConfigurationError("transitions must not be a string")
    else:
        items = tuple(definitions)

    parsed: list[Transition] = []
    for definition in items:
        if isinstance(definition, Transition):
            parsed.append(
                Transition(
                    command=_required_name(definition.command, "command"),
                    source=_required_name(definition.source, "source state"),
                    target=_required_name(definition.target, "target state"),
                    guards=_resolve_guards(definition.guards, guards),
                )
            )
            continue
        if not isinstance(definition, Mapping):
            raise StateMachineConfigurationError("Every transition must be a Transition or mapping")
        allowed_keys = {"command", "from", "source", "to", "target", "guards"}
        unknown_keys = set(definition) - allowed_keys
        if unknown_keys:
            raise StateMachineConfigurationError(
                f"Unknown transition definition keys: {', '.join(sorted(map(str, unknown_keys)))}"
            )
        try:
            command = _required_name(definition["command"], "command")
            source_value = definition.get("from", definition.get("source"))
            target_value = definition.get("to", definition.get("target"))
            if source_value is None or target_value is None:
                raise KeyError("from/to")
            sources = (
                _normalise_states(source_value)
                if not isinstance(source_value, str)
                else (_required_name(source_value, "source state"),)
            )
            target = _required_name(target_value, "target state")
            transition_guards = _resolve_guards(definition.get("guards", ()), guards)
        except KeyError as exc:
            raise StateMachineConfigurationError(
                f"Transition definition is missing required key {exc.args[0]!r}"
            ) from exc
        for source in sources:
            parsed.append(Transition(command=command, source=source, target=target, guards=transition_guards))
    return tuple(parsed)


def _expand_transition_mapping(definitions: Mapping[Any, Any]) -> Iterable[Mapping[str, Any]]:
    for key, value in definitions.items():
        if isinstance(key, tuple) and len(key) == 2:
            command, source = key
            if isinstance(value, Mapping):
                yield {"command": command, "from": source, **value}
            else:
                yield {"command": command, "from": source, "to": value}
            continue
        if not isinstance(key, str) or not isinstance(value, Mapping):
            raise StateMachineConfigurationError(
                "Transition mappings must use command names or (command, source) tuples"
            )
        if "from" in value or "source" in value:
            yield {"command": key, **value}
            continue
        # A command may map source states directly to targets.
        for source, target in value.items():
            if isinstance(target, Mapping):
                yield {"command": key, "from": source, **target}
            else:
                yield {"command": key, "from": source, "to": target}


def _resolve_guards(values: Any, guards: Mapping[str, Guard]) -> tuple[Guard, ...]:
    if values is None:
        return ()
    if callable(values) or isinstance(values, str):
        candidates = (values,)
    elif isinstance(values, Iterable):
        candidates = tuple(values)
    else:
        raise StateMachineConfigurationError("guards must be a callable, name, or sequence")

    resolved: list[Guard] = []
    for candidate in candidates:
        if isinstance(candidate, str):
            try:
                candidate = guards[candidate]
            except KeyError as exc:
                raise StateMachineConfigurationError(f"Guard {candidate!r} is not registered") from exc
        if not callable(candidate):
            raise StateMachineConfigurationError("Every guard must be callable")
        resolved.append(candidate)
    return tuple(resolved)


def _invoke_guard(guard: Guard, aggregate: ModelT, context: Mapping[str, Any]) -> bool:
    try:
        signature = inspect.signature(guard)
    except (TypeError, ValueError):
        return bool(guard(aggregate, context))
    try:
        signature.bind(aggregate, context)
    except TypeError:
        try:
            signature.bind(aggregate)
        except TypeError as exc:
            raise StateMachineConfigurationError(
                f"Guard {_callable_name(guard)!r} must accept (aggregate) or (aggregate, context)"
            ) from exc
        return bool(guard(aggregate))
    return bool(guard(aggregate, context))


def _callable_name(value: Guard) -> str:
    return getattr(value, "__name__", value.__class__.__name__)
