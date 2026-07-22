"""Configuration-driven lifecycle state machines for durable process-mining work."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from django.db import models

from src.core.state_machine import StateMachine, StateMachineConfigurationError, Transition

ModelT = TypeVar("ModelT", bound=models.Model)

# Commands are platform protocol, while the permitted edges and terminal states are
# tenant policy.  Keeping this interpreter in code avoids turning configuration into
# executable code while leaving every business workflow edge versioned and reversible.
_COMMAND_FOR_TARGET = {
    "running": "start",
    "cancelled": "cancel",
    "completed": "complete",
    "failed": "fail",
    "timed_out": "timeout",
    "queued": "retry",
    "expired": "expire",
}


class AuditedStateMachine(StateMachine[ModelT]):
    """Enforce the complete transition evidence contract."""

    def apply(self, *args: Any, metadata: Mapping[str, Any] | None = None, **kwargs: Any) -> ModelT:
        audit = dict(metadata or {})
        missing = [key for key in ("actor_id", "reason", "correlation_id") if not audit.get(key)]
        if missing:
            raise StateMachineConfigurationError(f"Transition audit metadata is missing: {', '.join(missing)}")
        audit.update({key: str(audit[key]) for key in ("actor_id", "reason", "correlation_id")})
        return super().apply(*args, metadata=audit, **kwargs)


def configured_state_machine(
    *,
    name: str,
    model: type[ModelT],
    states: Sequence[str],
    workflow: Mapping[str, Sequence[str]],
    terminal_states: Sequence[str],
) -> AuditedStateMachine[ModelT]:
    """Build a validated machine from a tenant's versioned workflow document."""
    transitions: list[Transition] = []
    for source, targets in workflow.items():
        for target in targets:
            command = _COMMAND_FOR_TARGET.get(target)
            if command is None:
                raise StateMachineConfigurationError(f"No command protocol exists for workflow target {target!r}")
            transitions.append(Transition(command, source, target))
    return AuditedStateMachine(
        name=name,
        model=model,
        states=states,
        terminal_states=terminal_states,
        transitions=transitions,
    )


__all__ = ["AuditedStateMachine", "configured_state_machine"]
