"""Declarative lifecycle authorities for accounting aggregates."""

from __future__ import annotations

from typing import Any, Final, cast

from django.utils import timezone

from src.core.state_machine import JSONFieldTransitionRecorder, StateMachine, TransitionRecord, registry

from .models import (
    APInvoice,
    APInvoiceStatus,
    ARInvoice,
    ARInvoiceStatus,
    JournalEntry,
    JournalEntryStatus,
    Payment,
    PaymentStatus,
    PostingPeriod,
    PostingPeriodStatus,
)

POSTING_PERIOD_MACHINE_NAME: Final = "accounting_finance.posting_period"
JOURNAL_ENTRY_MACHINE_NAME: Final = "accounting_finance.journal_entry"
AP_INVOICE_MACHINE_NAME: Final = "accounting_finance.ap_invoice"
AR_INVOICE_MACHINE_NAME: Final = "accounting_finance.ar_invoice"
PAYMENT_MACHINE_NAME: Final = "accounting_finance.payment"


def _actor(record: TransitionRecord) -> str:
    return str(record.metadata.get("actor_id") or "").strip()


class VersionedRecorder(JSONFieldTransitionRecorder[Any]):
    """Append transition evidence and advance aggregate audit metadata."""

    def record(self, aggregate: Any, record: TransitionRecord) -> None:
        super().record(aggregate, record)
        actor_id = _actor(record)
        if hasattr(aggregate, "updated_by") and actor_id:
            aggregate.updated_by = actor_id
        if hasattr(aggregate, "version"):
            aggregate.version += 1

    def aggregate_update_fields(self) -> tuple[str, ...]:
        return ("transition_history", "updated_by", "version", "updated_at")


class PostingPeriodRecorder(VersionedRecorder):
    def record(self, aggregate: PostingPeriod, record: TransitionRecord) -> None:
        super().record(aggregate, record)
        occurred_at = timezone.now()
        actor_id = _actor(record)
        if record.command == "close":
            aggregate.closed_at = occurred_at
            aggregate.closed_by = actor_id
        elif record.command == "reopen":
            aggregate.closed_at = None
            aggregate.closed_by = None
        elif record.command == "lock":
            aggregate.locked_at = occurred_at
            aggregate.locked_by = actor_id

    def aggregate_update_fields(self) -> tuple[str, ...]:
        return (*super().aggregate_update_fields(), "closed_at", "closed_by", "locked_at", "locked_by")


class JournalEntryRecorder(VersionedRecorder):
    def record(self, aggregate: JournalEntry, record: TransitionRecord) -> None:
        super().record(aggregate, record)
        occurred_at = timezone.now()
        actor_id = _actor(record)
        if record.command == "post":
            aggregate.posted_at = occurred_at
            aggregate.posted_by = actor_id
        elif record.command == "reverse":
            aggregate.reversed_at = occurred_at
            aggregate.reversed_by = actor_id

    def aggregate_update_fields(self) -> tuple[str, ...]:
        return (*super().aggregate_update_fields(), "posted_at", "posted_by", "reversed_at", "reversed_by")


class APInvoiceRecorder(VersionedRecorder):
    def record(self, aggregate: APInvoice, record: TransitionRecord) -> None:
        super().record(aggregate, record)
        occurred_at = timezone.now()
        actor_id = _actor(record)
        if record.command == "approve":
            aggregate.approved_at = occurred_at
            aggregate.approved_by = actor_id
        elif record.command == "reject":
            aggregate.approved_at = None
            aggregate.approved_by = None
        elif record.command == "post":
            aggregate.posted_at = occurred_at
            aggregate.posted_by = actor_id
        elif record.command == "cancel":
            aggregate.cancelled_at = occurred_at
            aggregate.cancelled_by = actor_id

    def aggregate_update_fields(self) -> tuple[str, ...]:
        return (
            *super().aggregate_update_fields(),
            "approved_at",
            "approved_by",
            "posted_at",
            "posted_by",
            "cancelled_at",
            "cancelled_by",
        )


class ARInvoiceRecorder(VersionedRecorder):
    def record(self, aggregate: ARInvoice, record: TransitionRecord) -> None:
        super().record(aggregate, record)
        occurred_at = timezone.now()
        actor_id = _actor(record)
        if record.command == "post":
            aggregate.posted_at = occurred_at
            aggregate.posted_by = actor_id
        elif record.command == "cancel":
            aggregate.cancelled_at = occurred_at
            aggregate.cancelled_by = actor_id

    def aggregate_update_fields(self) -> tuple[str, ...]:
        return (*super().aggregate_update_fields(), "posted_at", "posted_by", "cancelled_at", "cancelled_by")


class PaymentRecorder(JSONFieldTransitionRecorder[Payment]):
    def record(self, aggregate: Payment, record: TransitionRecord) -> None:
        super().record(aggregate, record)
        aggregate.voided_at = timezone.now()
        aggregate.voided_by = _actor(record)
        aggregate.void_reason = str(record.metadata.get("reason") or "").strip()

    def aggregate_update_fields(self) -> tuple[str, ...]:
        return ("transition_history", "voided_at", "voided_by", "void_reason", "updated_at")


POSTING_PERIOD_MACHINE: Final[StateMachine[PostingPeriod]] = StateMachine(
    name=POSTING_PERIOD_MACHINE_NAME,
    model=PostingPeriod,
    states=PostingPeriodStatus.values,
    terminal_states=(PostingPeriodStatus.LOCKED,),
    recorder=PostingPeriodRecorder(),
    transitions=(
        {"command": "close", "from": PostingPeriodStatus.OPEN, "to": PostingPeriodStatus.CLOSED},
        {"command": "reopen", "from": PostingPeriodStatus.CLOSED, "to": PostingPeriodStatus.OPEN},
        {"command": "lock", "from": PostingPeriodStatus.CLOSED, "to": PostingPeriodStatus.LOCKED},
    ),
)

JOURNAL_ENTRY_MACHINE: Final[StateMachine[JournalEntry]] = StateMachine(
    name=JOURNAL_ENTRY_MACHINE_NAME,
    model=JournalEntry,
    states=JournalEntryStatus.values,
    terminal_states=(JournalEntryStatus.REVERSED,),
    recorder=JournalEntryRecorder(),
    transitions=(
        {"command": "post", "from": JournalEntryStatus.DRAFT, "to": JournalEntryStatus.POSTED},
        {"command": "reverse", "from": JournalEntryStatus.POSTED, "to": JournalEntryStatus.REVERSED},
    ),
)

AP_INVOICE_MACHINE: Final[StateMachine[APInvoice]] = StateMachine(
    name=AP_INVOICE_MACHINE_NAME,
    model=APInvoice,
    states=APInvoiceStatus.values,
    terminal_states=(APInvoiceStatus.PAID, APInvoiceStatus.CANCELLED),
    recorder=APInvoiceRecorder(),
    transitions=(
        {"command": "submit", "from": APInvoiceStatus.DRAFT, "to": APInvoiceStatus.SUBMITTED},
        {"command": "approve", "from": APInvoiceStatus.SUBMITTED, "to": APInvoiceStatus.APPROVED},
        {"command": "reject", "from": APInvoiceStatus.SUBMITTED, "to": APInvoiceStatus.DRAFT},
        {"command": "post", "from": APInvoiceStatus.APPROVED, "to": APInvoiceStatus.POSTED},
        {"command": "record_partial_payment", "from": APInvoiceStatus.POSTED, "to": APInvoiceStatus.PARTIALLY_PAID},
        {"command": "record_full_payment", "from": (APInvoiceStatus.POSTED, APInvoiceStatus.PARTIALLY_PAID), "to": APInvoiceStatus.PAID},
        {"command": "cancel", "from": (APInvoiceStatus.DRAFT, APInvoiceStatus.SUBMITTED, APInvoiceStatus.APPROVED), "to": APInvoiceStatus.CANCELLED},
    ),
)

AR_INVOICE_MACHINE: Final[StateMachine[ARInvoice]] = StateMachine(
    name=AR_INVOICE_MACHINE_NAME,
    model=ARInvoice,
    states=ARInvoiceStatus.values,
    terminal_states=(ARInvoiceStatus.PAID, ARInvoiceStatus.CANCELLED),
    recorder=ARInvoiceRecorder(),
    transitions=(
        {"command": "post", "from": ARInvoiceStatus.DRAFT, "to": ARInvoiceStatus.POSTED},
        {"command": "record_partial_payment", "from": ARInvoiceStatus.POSTED, "to": ARInvoiceStatus.PARTIALLY_PAID},
        {"command": "record_full_payment", "from": (ARInvoiceStatus.POSTED, ARInvoiceStatus.PARTIALLY_PAID, ARInvoiceStatus.OVERDUE), "to": ARInvoiceStatus.PAID},
        {"command": "mark_overdue", "from": (ARInvoiceStatus.POSTED, ARInvoiceStatus.PARTIALLY_PAID), "to": ARInvoiceStatus.OVERDUE},
        {"command": "cancel", "from": ARInvoiceStatus.DRAFT, "to": ARInvoiceStatus.CANCELLED},
    ),
)

PAYMENT_MACHINE: Final[StateMachine[Payment]] = StateMachine(
    name=PAYMENT_MACHINE_NAME,
    model=Payment,
    states=PaymentStatus.values,
    terminal_states=(PaymentStatus.VOIDED,),
    recorder=PaymentRecorder(),
    transitions=({"command": "void", "from": PaymentStatus.RECORDED, "to": PaymentStatus.VOIDED},),
)


def register_state_machines() -> None:
    """Register accounting machines idempotently and reject collisions."""

    for name, machine in (
        (POSTING_PERIOD_MACHINE_NAME, POSTING_PERIOD_MACHINE),
        (JOURNAL_ENTRY_MACHINE_NAME, JOURNAL_ENTRY_MACHINE),
        (AP_INVOICE_MACHINE_NAME, AP_INVOICE_MACHINE),
        (AR_INVOICE_MACHINE_NAME, AR_INVOICE_MACHINE),
        (PAYMENT_MACHINE_NAME, PAYMENT_MACHINE),
    ):
        try:
            current = registry.get(name)
        except LookupError:
            current = None
        if current is None:
            registry.register(name, cast(StateMachine[Any], machine))
        elif current is not machine:
            raise RuntimeError(f"A different state machine is already registered as {name!r}")


__all__ = [
    "AP_INVOICE_MACHINE", "AR_INVOICE_MACHINE", "JOURNAL_ENTRY_MACHINE", "PAYMENT_MACHINE",
    "POSTING_PERIOD_MACHINE", "register_state_machines",
]
