"""Declarative procurement lifecycle graphs registered with the core engine."""

from __future__ import annotations

from src.core.async_jobs.models import OutboxEvent
from src.core.state_machine import StateMachine, TransitionRecord, register

from .models import PurchaseOrder, PurchaseReceipt, PurchaseRequisition, RequestForQuotation, SupplierQuote


class OutboxTransitionRecorder:
    """Persist immutable transition evidence without adding mutable JSON state."""

    def find(self, aggregate, transition_key):
        event = (
            OutboxEvent.objects.for_tenant(aggregate.tenant_id)
            .filter(
                aggregate_id=aggregate.id, event_type="purchase.transition.v1", payload__transition_key=transition_key
            )
            .first()
        )
        if not event:
            return None
        p = event.payload
        return TransitionRecord(
            p["transition_key"], p["command"], p["from_state"], p["to_state"], p["occurred_at"], p.get("metadata", {})
        )

    def record(self, aggregate, record):
        OutboxEvent.objects.create(
            tenant_id=aggregate.tenant_id,
            aggregate_type=aggregate._meta.label_lower,
            aggregate_id=aggregate.id,
            event_type="purchase.transition.v1",
            payload=record.as_dict(),
        )

    def aggregate_update_fields(self):
        return ()


RECORDER = OutboxTransitionRecorder()

DEFINITIONS = {
    "purchase_management.requisition": (
        PurchaseRequisition,
        ["draft", "pending_approval", "approved", "rejected", "converted", "cancelled"],
        [
            ("submit", "draft", "pending_approval"),
            ("approve", "pending_approval", "approved"),
            ("reject", "pending_approval", "rejected"),
            ("revise", "rejected", "draft"),
            ("convert", "approved", "converted"),
            ("cancel", "draft", "cancelled"),
            ("cancel", "pending_approval", "cancelled"),
            ("cancel", "approved", "cancelled"),
        ],
        ["converted", "cancelled"],
    ),
    "purchase_management.rfq": (
        RequestForQuotation,
        ["draft", "open", "closed", "awarded", "cancelled"],
        [
            ("publish", "draft", "open"),
            ("close", "open", "closed"),
            ("award", "closed", "awarded"),
            ("cancel", "draft", "cancelled"),
            ("cancel", "open", "cancelled"),
        ],
        ["awarded", "cancelled"],
    ),
    "purchase_management.quote": (
        SupplierQuote,
        ["draft", "submitted", "withdrawn", "accepted", "rejected"],
        [
            ("submit", "draft", "submitted"),
            ("withdraw", "submitted", "withdrawn"),
            ("accept", "submitted", "accepted"),
            ("reject", "submitted", "rejected"),
        ],
        ["withdrawn", "accepted", "rejected"],
    ),
    "purchase_management.order": (
        PurchaseOrder,
        [
            "draft",
            "pending_approval",
            "approved",
            "sent",
            "acknowledged",
            "partially_received",
            "received",
            "cancelled",
        ],
        [
            ("submit", "draft", "pending_approval"),
            ("approve", "pending_approval", "approved"),
            ("reject", "pending_approval", "draft"),
            ("dispatch", "approved", "sent"),
            ("acknowledge", "sent", "acknowledged"),
            ("record_partial_receipt", "acknowledged", "partially_received"),
            ("record_partial_receipt", "partially_received", "partially_received"),
            ("record_full_receipt", "acknowledged", "received"),
            ("record_full_receipt", "partially_received", "received"),
            ("cancel", "draft", "cancelled"),
            ("cancel", "pending_approval", "cancelled"),
            ("cancel", "approved", "cancelled"),
            ("cancel", "sent", "cancelled"),
            ("cancel", "acknowledged", "cancelled"),
        ],
        ["received", "cancelled"],
    ),
    "purchase_management.receipt": (
        PurchaseReceipt,
        ["draft", "completed", "cancelled"],
        [("complete", "draft", "completed"), ("cancel", "draft", "cancelled")],
        ["completed", "cancelled"],
    ),
}


MACHINES = {
    name: StateMachine(
        name=name,
        model=model,
        recorder=RECORDER,
        states=states,
        transitions=[{"command": command, "from": source, "to": target} for command, source, target in transitions],
        terminal_states=terminals,
    )
    for name, (model, states, transitions, terminals) in DEFINITIONS.items()
}


def register_state_machines() -> None:
    for name, machine in MACHINES.items():
        register(name, machine, replace=True)
