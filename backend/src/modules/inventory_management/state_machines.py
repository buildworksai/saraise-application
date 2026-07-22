"""Inventory aggregate state graphs.

Services call :func:`transition`; direct assignment of ``status`` is not a
supported domain operation. The core engine supplies row locking, atomic audit
history, terminal-state protection, guards, and transition-key idempotency.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from django.db import models

from src.core.state_machine.machine import JSONFieldTransitionRecorder, StateMachine, TransitionRecord

from .models import Batch, CycleCount, SerialNumber, StockEntry, StockReservation


class _VersionedTransitionRecorder(JSONFieldTransitionRecorder[Any]):
    """Append history and advance the aggregate concurrency token atomically."""

    def record(self, aggregate: Any, record: TransitionRecord) -> None:
        super().record(aggregate, record)
        aggregate.version += 1

    def aggregate_update_fields(self) -> tuple[str, ...]:
        return ("transition_history", "version")


def _machine(
    *,
    name: str,
    model: type[models.Model],
    states: tuple[str, ...],
    transitions: tuple[Mapping[str, Any], ...],
    terminal_states: tuple[str, ...],
) -> StateMachine[Any]:
    return StateMachine(
        name=name,
        model=model,
        states=states,
        transitions=transitions,
        terminal_states=terminal_states,
        recorder=_VersionedTransitionRecorder(),
    )


batch_machine = _machine(
    name="inventory.batch",
    model=Batch,
    states=("planned", "active", "quarantined", "recalled", "exhausted", "expired"),
    transitions=(
        {"command": "activate", "from": "planned", "to": "active"},
        {"command": "quarantine", "from": "active", "to": "quarantined"},
        {"command": "release", "from": "quarantined", "to": "active"},
        {"command": "recall", "from": ("active", "quarantined"), "to": "recalled"},
        {"command": "exhaust", "from": "active", "to": "exhausted"},
        {"command": "expire", "from": ("active", "quarantined"), "to": "expired"},
    ),
    terminal_states=("recalled", "exhausted", "expired"),
)

serial_number_machine = _machine(
    name="inventory.serial_number",
    model=SerialNumber,
    states=("registered", "in_stock", "reserved", "in_transit", "sold", "in_service", "scrapped"),
    transitions=(
        {"command": "receive", "from": ("registered", "in_transit"), "to": "in_stock"},
        {"command": "reserve", "from": "in_stock", "to": "reserved"},
        {"command": "release", "from": "reserved", "to": "in_stock"},
        {"command": "ship", "from": ("reserved", "in_stock"), "to": "in_transit"},
        {"command": "issue", "from": ("in_stock", "reserved"), "to": "sold"},
        {"command": "service", "from": ("in_stock", "sold"), "to": "in_service"},
        {
            "command": "scrap",
            "from": ("registered", "in_stock", "reserved", "in_transit", "sold", "in_service"),
            "to": "scrapped",
        },
    ),
    terminal_states=("scrapped",),
)

stock_entry_machine = _machine(
    name="inventory.stock_entry",
    model=StockEntry,
    states=("draft", "submitted", "approved", "posted", "rejected", "cancelled", "reversed"),
    transitions=(
        {"command": "submit", "from": ("draft", "rejected"), "to": "submitted"},
        {"command": "approve", "from": "submitted", "to": "approved"},
        {"command": "reject", "from": ("submitted", "approved"), "to": "rejected"},
        {"command": "post", "from": ("submitted", "approved"), "to": "posted"},
        {"command": "cancel", "from": ("draft", "submitted", "approved", "rejected"), "to": "cancelled"},
        {"command": "reverse", "from": "posted", "to": "reversed"},
    ),
    terminal_states=("cancelled", "reversed"),
)

reservation_machine = _machine(
    name="inventory.stock_reservation",
    model=StockReservation,
    states=("active", "released", "consumed", "expired", "cancelled"),
    transitions=(
        {"command": "release", "from": "active", "to": "released"},
        {"command": "consume", "from": "active", "to": "consumed"},
        {"command": "expire", "from": "active", "to": "expired"},
        {"command": "cancel", "from": "active", "to": "cancelled"},
    ),
    terminal_states=("released", "consumed", "expired", "cancelled"),
)

cycle_count_machine = _machine(
    name="inventory.cycle_count",
    model=CycleCount,
    states=("scheduled", "in_progress", "submitted", "approved", "posted", "cancelled"),
    transitions=(
        {"command": "start", "from": "scheduled", "to": "in_progress"},
        {"command": "submit", "from": "in_progress", "to": "submitted"},
        {"command": "approve", "from": "submitted", "to": "approved"},
        {"command": "reject", "from": ("submitted", "approved"), "to": "in_progress"},
        {"command": "post", "from": "approved", "to": "posted"},
        {"command": "cancel", "from": ("scheduled", "in_progress", "submitted", "approved"), "to": "cancelled"},
    ),
    terminal_states=("posted", "cancelled"),
)

MACHINES: Mapping[type[models.Model], StateMachine[Any]] = {
    Batch: batch_machine,
    SerialNumber: serial_number_machine,
    StockEntry: stock_entry_machine,
    StockReservation: reservation_machine,
    CycleCount: cycle_count_machine,
}

NAMED_MACHINES: Mapping[str, StateMachine[Any]] = {
    machine.name: machine for machine in MACHINES.values() if machine.name is not None
}


def get_machine(name: str) -> StateMachine[Any]:
    """Resolve a core inventory graph by its stable name."""

    try:
        return NAMED_MACHINES[name]
    except KeyError as exc:
        raise LookupError(f"inventory state machine {name!r} is not registered") from exc


def transition(
    instance: models.Model,
    command: str,
    actor_id: UUID | str | None,
    transition_key: str,
    *,
    context: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> models.Model:
    """Apply an idempotent state command and return the locked stored row."""

    try:
        machine = MACHINES[type(instance)]
    except KeyError as exc:
        raise TypeError(f"{instance._meta.label} is not a stateful inventory aggregate") from exc
    audit = dict(metadata or {})
    if actor_id is not None:
        audit["actor_id"] = str(actor_id)
    return machine.apply(
        instance,
        command,
        transition_key=transition_key,
        context=context,
        metadata=audit,
    )


__all__ = [
    "MACHINES",
    "NAMED_MACHINES",
    "batch_machine",
    "cycle_count_machine",
    "get_machine",
    "reservation_machine",
    "serial_number_machine",
    "stock_entry_machine",
    "transition",
]
