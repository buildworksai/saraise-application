"""Authoritative state graphs for multi-company financial aggregates.

State mutation is deliberately centralised here.  Callers must use the service
commands, which add tenant locking, concurrency checks and audit metadata.
"""

from __future__ import annotations

from src.core.state_machine import StateMachine, Transition

from .models import ConsolidationRun, IntercompanyTransaction


TRANSACTION_STATES = frozenset(
    {
        "draft", "pending_approval", "approved", "posting", "posted",
        "posting_failed", "disputed", "eliminated", "cancelled", "expired",
    }
)

TRANSACTION_TRANSITIONS = (
    Transition("submit", "draft", "pending_approval"),
    Transition("approve", "pending_approval", "approved"),
    Transition("dispute", "pending_approval", "disputed"),
    Transition("dispute", "approved", "disputed"),
    Transition("resolve", "disputed", "pending_approval"),
    Transition("post", "approved", "posting"),
    Transition("post", "posting_failed", "posting"),
    Transition("posting_succeeded", "posting", "posted"),
    Transition("posting_failed", "posting", "posting_failed"),
    Transition("eliminate", "posted", "eliminated"),
    Transition("cancel", "draft", "cancelled"),
    Transition("cancel", "pending_approval", "cancelled"),
    Transition("cancel", "approved", "cancelled"),
    Transition("cancel", "disputed", "cancelled"),
    Transition("cancel", "posting_failed", "cancelled"),
    Transition("expire", "draft", "expired"),
)

transaction_state_machine: StateMachine[IntercompanyTransaction] = StateMachine(
    name="multi_company.transaction.v1",
    model=IntercompanyTransaction,
    states=TRANSACTION_STATES,
    transitions=TRANSACTION_TRANSITIONS,
    terminal_states={"eliminated", "cancelled", "expired"},
)


CONSOLIDATION_STATES = frozenset(
    {"draft", "queued", "running", "completed", "failed", "approved", "published", "cancelled"}
)

CONSOLIDATION_TRANSITIONS = (
    Transition("queue", "draft", "queued"),
    Transition("start", "queued", "running"),
    Transition("complete", "running", "completed"),
    Transition("fail", "queued", "failed"),
    Transition("fail", "running", "failed"),
    Transition("retry", "failed", "queued"),
    Transition("approve", "completed", "approved"),
    Transition("publish", "approved", "published"),
    Transition("cancel", "draft", "cancelled"),
    Transition("cancel", "queued", "cancelled"),
    Transition("cancel", "failed", "cancelled"),
)

consolidation_state_machine: StateMachine[ConsolidationRun] = StateMachine(
    name="multi_company.consolidation.v1",
    model=ConsolidationRun,
    states=CONSOLIDATION_STATES,
    transitions=CONSOLIDATION_TRANSITIONS,
    terminal_states={"published", "cancelled"},
)


__all__ = [
    "CONSOLIDATION_STATES", "CONSOLIDATION_TRANSITIONS", "TRANSACTION_STATES",
    "TRANSACTION_TRANSITIONS", "consolidation_state_machine", "transaction_state_machine",
]
