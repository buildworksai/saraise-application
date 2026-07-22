"""Authoritative budget lifecycle state machine and append-only recorder."""

from __future__ import annotations

from collections.abc import Collection
from typing import Any
from uuid import UUID

from src.core.state_machine import StateMachine, Transition, TransitionRecord

from .models import Budget, BudgetTransition


class BudgetTransitionRecorder:
    """Persist core state-machine records in the module audit table."""

    def find(self, aggregate: Budget, transition_key: str) -> TransitionRecord | None:
        existing = BudgetTransition.objects.filter(
            tenant_id=aggregate.tenant_id,
            budget=aggregate,
            transition_key=transition_key,
        ).first()
        if existing is None:
            return None
        return TransitionRecord(
            transition_key=existing.transition_key,
            command=existing.command,
            from_state=existing.from_state,
            to_state=existing.to_state,
            occurred_at=existing.occurred_at.isoformat(),
            metadata=dict(existing.metadata),
        )

    def record(self, aggregate: Budget, record: TransitionRecord) -> None:
        supplied = dict(record.metadata)
        raw_actor = supplied.pop("actor_id", None)
        if raw_actor is None:
            raise ValueError("actor_id is required to record a budget transition")
        actor_id = raw_actor if isinstance(raw_actor, UUID) else UUID(str(raw_actor))
        notes = str(supplied.pop("notes", ""))
        # Lifecycle metadata and status must reach PostgreSQL in the same
        # statement because the model's check constraints reject half-applied
        # approved/rejected states.
        aggregate.updated_by = actor_id
        if record.command == "submit":
            aggregate.submitted_at = supplied.pop("_submitted_at")
            aggregate.submitted_by = actor_id
        elif record.command == "approve":
            aggregate.approved_at = supplied.pop("_approved_at")
            aggregate.approved_by = actor_id
        elif record.command == "reject":
            aggregate.rejected_at = supplied.pop("_rejected_at")
            aggregate.rejected_by = actor_id
            aggregate.rejection_reason = supplied.pop("_rejection_reason")
        BudgetTransition.objects.create(
            tenant_id=aggregate.tenant_id,
            budget=aggregate,
            transition_key=record.transition_key,
            command=record.command,
            from_state=record.from_state,
            to_state=record.to_state,
            actor_id=actor_id,
            notes=notes,
            metadata=_safe_metadata(supplied),
        )

    def aggregate_update_fields(self) -> Collection[str]:
        return (
            "updated_by",
            "submitted_at",
            "submitted_by",
            "approved_at",
            "approved_by",
            "rejected_at",
            "rejected_by",
            "rejection_reason",
        )


def _safe_metadata(value: dict[str, Any]) -> dict[str, Any]:
    """Allowlist non-sensitive transition metadata."""

    allowed = {"approval_level", "workflow_request_id", "reason_code"}
    return {
        key: str(item) if isinstance(item, UUID) else item
        for key, item in value.items()
        if key in allowed and item is not None
    }


BUDGET_STATE_MACHINE = StateMachine[Budget](
    name="budget.lifecycle",
    model=Budget,
    recorder=BudgetTransitionRecorder(),
    states=("draft", "pending_approval", "approved", "rejected", "revision", "closed"),
    transitions=(
        Transition("submit", "draft", "pending_approval"),
        Transition("submit", "revision", "pending_approval"),
        Transition("approve", "pending_approval", "approved"),
        Transition("reject", "pending_approval", "rejected"),
        Transition("revise", "rejected", "revision"),
        Transition("close", "approved", "closed"),
    ),
    terminal_states=("closed",),
)


def allowed_budget_commands(status: str) -> tuple[str, ...]:
    """Return stable command names for API presentation."""

    return BUDGET_STATE_MACHINE.allowed_commands(status)


__all__ = ["BUDGET_STATE_MACHINE", "BudgetTransitionRecorder", "allowed_budget_commands"]
