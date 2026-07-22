"""Registered, tenant-locked import and reconciliation lifecycle machines."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from django.core.exceptions import ObjectDoesNotExist
from django.db import models

from src.core.state_machine import StateMachine, StateMachineConfigurationError, Transition, register

from .models import BankStatementImport, ReconciliationSession

ModelT = TypeVar("ModelT", bound=models.Model)


class AuditedStateMachine(StateMachine[ModelT]):
    """Require actor, reason and correlation evidence for every transition."""

    def apply(self, *args: Any, metadata: Mapping[str, Any] | None = None, **kwargs: Any) -> ModelT:
        audit = dict(metadata or {})
        missing = [key for key in ("actor_id", "reason", "correlation_id") if not audit.get(key)]
        if missing:
            raise StateMachineConfigurationError(f"Transition audit metadata is missing: {', '.join(missing)}")
        audit["actor_id"] = str(audit["actor_id"])
        audit["reason"] = str(audit["reason"])[:500]
        audit["correlation_id"] = str(audit["correlation_id"])[:64]
        return super().apply(*args, metadata=audit, **kwargs)


def _import_can_succeed(aggregate: BankStatementImport, context: Mapping[str, Any]) -> bool:
    """Only persisted non-empty imports with an associated statement succeed."""
    del context
    try:
        statement_relation = getattr(aggregate, "statement", None)
        if statement_relation is None:
            statement_relation = aggregate.bank_statement
    except (AttributeError, ObjectDoesNotExist):
        return False
    return bool(statement_relation) and int(getattr(aggregate, "rows_imported", 0)) > 0


def _reconciliation_can_submit(aggregate: ReconciliationSession, context: Mapping[str, Any]) -> bool:
    """Service supplies verified aggregate facts under the same row lock."""
    return context.get("all_transactions_resolved") is True and context.get("proposed_matches") in {0, None}


def _reconciliation_can_finalize(aggregate: ReconciliationSession, context: Mapping[str, Any]) -> bool:
    try:
        within_tolerance = abs(aggregate.difference) <= aggregate.tolerance
    except (AttributeError, TypeError):
        return False
    return (
        within_tolerance
        and context.get("ledger_balance_verified") is True
        and context.get("duties_separated", True) is True
    )


import_state_machine = AuditedStateMachine(
    name="bank_reconciliation.statement_import",
    model=BankStatementImport,
    states=("pending", "running", "succeeded", "failed", "cancelled"),
    terminal_states=("succeeded", "cancelled"),
    transitions=(
        Transition("start", "pending", "running"),
        Transition("succeed", "running", "succeeded", (_import_can_succeed,)),
        Transition("fail", "running", "failed"),
        Transition("cancel", "pending", "cancelled"),
        Transition("cancel", "running", "cancelled"),
        Transition("retry", "failed", "pending"),
    ),
)

reconciliation_state_machine = AuditedStateMachine(
    name="bank_reconciliation.reconciliation",
    model=ReconciliationSession,
    states=("draft", "in_progress", "review", "finalized", "void"),
    terminal_states=("finalized", "void"),
    transitions=(
        Transition("start", "draft", "in_progress"),
        Transition("submit_review", "in_progress", "review", (_reconciliation_can_submit,)),
        Transition("return_to_work", "review", "in_progress"),
        Transition("finalize", "review", "finalized", (_reconciliation_can_finalize,)),
        Transition("void", "draft", "void"),
        Transition("void", "in_progress", "void"),
        Transition("void", "review", "void"),
    ),
)

IMPORT_STATE_MACHINE = import_state_machine
RECONCILIATION_STATE_MACHINE = reconciliation_state_machine

for _machine in (import_state_machine, reconciliation_state_machine):
    register(_machine.name or "", _machine)


__all__ = [
    "AuditedStateMachine",
    "IMPORT_STATE_MACHINE",
    "RECONCILIATION_STATE_MACHINE",
    "import_state_machine",
    "reconciliation_state_machine",
]
