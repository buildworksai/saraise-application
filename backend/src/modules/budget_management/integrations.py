"""Typed extension ports for budget-management integrations.

The open-source domain depends only on these protocols.  Accounting, workflow,
notification, procurement, expense, and industry modules can register adapters
without importing or replacing the budget models.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable
from uuid import UUID

if False:  # pragma: no cover - imports used only by static type checkers
    from .models import Budget


class IntegrationError(RuntimeError):
    """Base class for stable, non-sensitive dependency failures."""

    code = "DEPENDENCY_FAILURE"
    retryable = False

    def __init__(self, message: str, *, dependency: str, retryable: bool | None = None) -> None:
        super().__init__(message)
        self.dependency = dependency
        if retryable is not None:
            self.retryable = retryable


class CapabilityUnavailable(IntegrationError):
    """Raised when an optional adapter is required but not configured."""

    code = "CAPABILITY_UNAVAILABLE"


class IntegrationUnavailable(IntegrationError):
    """Raised for timeout, open-circuit, or transport unavailability."""

    code = "DEPENDENCY_UNAVAILABLE"
    retryable = True


class InvalidIntegrationResponse(IntegrationError):
    """Raised when an adapter returns a payload that cannot be trusted."""

    code = "INVALID_DEPENDENCY_RESPONSE"


@dataclass(frozen=True, slots=True)
class ApprovalStep:
    """One approver assignment returned by a workflow adapter."""

    approver_id: UUID
    approval_level: int


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """External workflow identity and its in-core approval assignments."""

    workflow_request_id: UUID
    steps: tuple[ApprovalStep, ...]


@dataclass(frozen=True, slots=True)
class ActualsSnapshot:
    """Validated adapter output; ``evidence`` is persisted only as an opaque ID."""

    lines: tuple[Mapping[str, Any], ...]
    evidence: str


@runtime_checkable
class AccountingBudgetPort(Protocol):
    """Accounting contract used by allocations and actual synchronization."""

    def validate_accounts(self, tenant_id: UUID, account_codes: Sequence[str]) -> None:
        """Raise a typed integration error when any account is invalid."""

    def fetch_actuals(
        self,
        tenant_id: UUID,
        budget: "Budget",
        periods: Sequence[Mapping[str, Any]],
    ) -> ActualsSnapshot:
        """Return a complete, evidenced actuals snapshot for requested periods."""

    def health_state(self) -> str:
        """Return ``closed``, ``open``, or ``half_open`` without network traffic."""


@runtime_checkable
class ApprovalWorkflowPort(Protocol):
    """Optional approval-policy/workflow contract."""

    def create_approval_request(
        self,
        tenant_id: UUID,
        *,
        budget: "Budget",
        submitter_id: UUID,
        idempotency_key: str,
    ) -> ApprovalRequest:
        """Create or return the idempotent external workflow request."""

    def get_approval_status(self, tenant_id: UUID, workflow_request_id: UUID) -> str:
        """Return the external request's governed status."""

    def health_state(self) -> str:
        """Return circuit state without forcing an external request."""


@runtime_checkable
class NotificationPort(Protocol):
    """Optional notification delivery contract used by durable workers only."""

    def enqueue_budget_notification(
        self,
        tenant_id: UUID,
        *,
        notification_type: str,
        aggregate_id: UUID,
        recipient_ids: Sequence[UUID],
        idempotency_key: str,
    ) -> str:
        """Queue an idempotent notification and return provider evidence."""

    def health_state(self) -> str:
        """Return circuit state without external traffic."""


@dataclass(frozen=True, slots=True)
class IntegrationRegistry:
    accounting: AccountingBudgetPort | None = None
    workflow: ApprovalWorkflowPort | None = None
    notification: NotificationPort | None = None


_registry = IntegrationRegistry()
_registry_lock = RLock()


def configure_integrations(
    *,
    accounting: AccountingBudgetPort | None = None,
    workflow: ApprovalWorkflowPort | None = None,
    notification: NotificationPort | None = None,
) -> IntegrationRegistry:
    """Atomically replace adapter registrations and return the prior registry.

    Application startup and tests use this explicit hook; services never import
    another module's models or probe for modules by import side effects.
    """

    global _registry
    with _registry_lock:
        previous = _registry
        _registry = IntegrationRegistry(accounting, workflow, notification)
        return previous


def get_integrations() -> IntegrationRegistry:
    """Return the immutable current adapter registry."""

    with _registry_lock:
        return _registry


def require_accounting() -> AccountingBudgetPort:
    adapter = get_integrations().accounting
    if adapter is None:
        raise CapabilityUnavailable(
            "Accounting actual synchronization is not configured",
            dependency="accounting",
        )
    return adapter


def require_workflow() -> ApprovalWorkflowPort:
    adapter = get_integrations().workflow
    if adapter is None:
        raise CapabilityUnavailable(
            "Approval workflow is not configured",
            dependency="workflow",
        )
    return adapter


def require_notification() -> NotificationPort:
    adapter = get_integrations().notification
    if adapter is None:
        raise CapabilityUnavailable(
            "Budget notifications are not configured",
            dependency="notification",
        )
    return adapter


__all__ = [
    "AccountingBudgetPort",
    "ActualsSnapshot",
    "ApprovalRequest",
    "ApprovalStep",
    "ApprovalWorkflowPort",
    "CapabilityUnavailable",
    "IntegrationError",
    "IntegrationRegistry",
    "IntegrationUnavailable",
    "InvalidIntegrationResponse",
    "NotificationPort",
    "configure_integrations",
    "get_integrations",
    "require_accounting",
    "require_notification",
    "require_workflow",
]
