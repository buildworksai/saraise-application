"""Typed integration boundary for financial dependencies.

No adapter may manufacture financial evidence.  An unconfigured dependency is
represented by :class:`CapabilityUnavailable`, giving APIs and workers a stable
``CAPABILITY_UNAVAILABLE`` failure rather than a deceptive empty response.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable
from uuid import UUID


CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"


class IntegrationError(RuntimeError):
    """Stable integration failure carrying a non-sensitive machine code."""

    code = "INTEGRATION_FAILURE"

    def __init__(self, message: str, *, dependency: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.dependency = dependency
        self.retryable = retryable


class CapabilityUnavailable(IntegrationError):
    code = CAPABILITY_UNAVAILABLE

    def __init__(self, dependency: str, capability: str) -> None:
        super().__init__(
            f"Required capability {capability!r} is unavailable for dependency {dependency!r}",
            dependency=dependency,
            retryable=False,
        )
        self.capability = capability


class PartialPostingError(IntegrationError):
    """The provider posted only one side; compensation evidence is required."""

    code = "PARTIAL_POSTING"

    def __init__(self, message: str, *, result: "DualJournalResult") -> None:
        super().__init__(message, dependency="ledger", retryable=False)
        self.result = result


@dataclass(frozen=True, slots=True)
class JournalLine:
    account: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    description: str = ""


@dataclass(frozen=True, slots=True)
class JournalRequest:
    company_id: UUID
    external_key: str
    transaction_date: date
    currency: str
    lines: tuple[JournalLine, ...]


@dataclass(frozen=True, slots=True)
class DualJournalRequest:
    transaction_id: UUID
    source: JournalRequest
    target: JournalRequest
    correlation_id: str


@dataclass(frozen=True, slots=True)
class DualJournalResult:
    source_journal_id: UUID | None
    target_journal_id: UUID | None
    source_accepted: bool
    target_accepted: bool
    provider_reference: str = ""


@dataclass(frozen=True, slots=True)
class JournalVerification:
    journal_id: UUID
    exists: bool
    balanced: bool
    posted: bool


@dataclass(frozen=True, slots=True)
class ReversalResult:
    original_journal_id: UUID
    reversal_journal_id: UUID
    verified: bool


@dataclass(frozen=True, slots=True)
class TrialBalanceLine:
    account: str
    debit: Decimal
    credit: Decimal


@dataclass(frozen=True, slots=True)
class ApprovalVerification:
    transaction_id: UUID
    source_approved: bool
    target_approved: bool
    workflow_reference: str


@runtime_checkable
class LedgerGateway(Protocol):
    def is_period_closed(self, tenant_id: UUID, company_id: UUID, period_end: date) -> bool: ...
    def get_trial_balance(
        self, tenant_id: UUID, company_id: UUID, period_start: date, period_end: date, correlation_id: str
    ) -> Sequence[TrialBalanceLine]: ...
    def post_dual_journals(self, tenant_id: UUID, request: DualJournalRequest) -> DualJournalResult: ...
    def reverse_journal(
        self, tenant_id: UUID, company_id: UUID, journal_id: UUID, reason: str, correlation_id: str
    ) -> ReversalResult: ...
    def verify_journal(
        self, tenant_id: UUID, company_id: UUID, journal_id: UUID, correlation_id: str
    ) -> JournalVerification: ...


@runtime_checkable
class ExchangeRateGateway(Protocol):
    def get_rate(
        self, tenant_id: UUID, source_currency: str, target_currency: str, effective_date: date, correlation_id: str
    ) -> Decimal: ...


@runtime_checkable
class WorkflowGateway(Protocol):
    def request_dual_approval(
        self, tenant_id: UUID, transaction_id: UUID, source_company_id: UUID,
        target_company_id: UUID, correlation_id: str
    ) -> str: ...
    def verify_dual_approval(
        self, tenant_id: UUID, transaction_id: UUID, workflow_reference: str, correlation_id: str
    ) -> ApprovalVerification: ...


@runtime_checkable
class NotificationGateway(Protocol):
    def notify(self, tenant_id: UUID, event: str, recipients: Sequence[str], context: Mapping[str, Any], correlation_id: str) -> None: ...


@runtime_checkable
class ReportGateway(Protocol):
    def render(self, tenant_id: UUID, report_type: str, snapshot: Mapping[str, Any], output_format: str, correlation_id: str) -> bytes: ...


@dataclass(slots=True)
class IntegrationRegistry:
    ledger: LedgerGateway | None = None
    exchange_rates: ExchangeRateGateway | None = None
    workflow: WorkflowGateway | None = None
    notifications: NotificationGateway | None = None
    reports: ReportGateway | None = None

    def require_ledger(self) -> LedgerGateway:
        if self.ledger is None:
            raise CapabilityUnavailable("ledger", "financial_journals")
        return self.ledger

    def require_exchange_rates(self) -> ExchangeRateGateway:
        if self.exchange_rates is None:
            raise CapabilityUnavailable("exchange_rates", "currency_translation")
        return self.exchange_rates

    def require_workflow(self) -> WorkflowGateway:
        if self.workflow is None:
            raise CapabilityUnavailable("workflow", "dual_approval")
        return self.workflow


integrations = IntegrationRegistry()


__all__ = [name for name in globals() if not name.startswith("_")]
