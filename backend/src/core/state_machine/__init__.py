"""Reusable guarded state-transition foundation."""

from .machine import (
    GuardFailedError,
    IdempotencyConflictError,
    IllegalTransitionError,
    JSONFieldTransitionRecorder,
    StateMachine,
    StateMachineConfigurationError,
    StateMachineError,
    TerminalStateError,
    Transition,
    TransitionRecord,
    TransitionRecorder,
    UnknownCommandError,
)
from .registry import (
    MachineAlreadyRegisteredError,
    MachineNotRegisteredError,
    StateMachineRegistry,
    get,
    register,
    registry,
)

__all__ = [
    "GuardFailedError",
    "IdempotencyConflictError",
    "IllegalTransitionError",
    "JSONFieldTransitionRecorder",
    "MachineAlreadyRegisteredError",
    "MachineNotRegisteredError",
    "StateMachine",
    "StateMachineConfigurationError",
    "StateMachineError",
    "StateMachineRegistry",
    "TerminalStateError",
    "Transition",
    "TransitionRecord",
    "TransitionRecorder",
    "UnknownCommandError",
    "get",
    "register",
    "registry",
]
