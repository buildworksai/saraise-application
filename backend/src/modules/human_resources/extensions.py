"""Stable typed extension ports for optional paid-domain integrations.

Core HR never imports an adapter. Implementations are resolved by the owning
paid module and failures must be returned explicitly rather than silently
falling back after an adapter has accepted a command.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExtensionContext:
    tenant_id: UUID
    actor_id: str
    correlation_id: str
    schema_version: str = "1.0"


@dataclass(frozen=True, slots=True)
class MasterDataEmployeeReference:
    employee_id: UUID
    master_record_id: str
    source_version: str


@runtime_checkable
class MasterDataEmployeePort(Protocol):
    schema_version: str

    def resolve_employee(
        self, context: ExtensionContext, *, employee_id: UUID
    ) -> MasterDataEmployeeReference | None: ...


@dataclass(frozen=True, slots=True)
class ApprovalSubmission:
    external_request_id: str
    state: str


@runtime_checkable
class WorkflowApprovalPort(Protocol):
    schema_version: str

    def submit_leave_approval(
        self,
        context: ExtensionContext,
        *,
        leave_request_id: UUID,
        idempotency_key: str,
    ) -> ApprovalSubmission: ...

    def cancel_leave_approval(
        self,
        context: ExtensionContext,
        *,
        leave_request_id: UUID,
        idempotency_key: str,
    ) -> None: ...


@runtime_checkable
class BusinessCalendarPort(Protocol):
    schema_version: str

    def calculate_leave_days(
        self,
        context: ExtensionContext,
        *,
        employee_id: UUID,
        start_date: date,
        end_date: date,
    ) -> Decimal: ...


@runtime_checkable
class HumanResourcesEventSubscriber(Protocol):
    schema_version: str
    subscribed_event_types: frozenset[str]

    def handle(self, context: ExtensionContext, *, event: Mapping[str, object]) -> None: ...


__all__ = [
    "ApprovalSubmission",
    "BusinessCalendarPort",
    "ExtensionContext",
    "HumanResourcesEventSubscriber",
    "MasterDataEmployeePort",
    "MasterDataEmployeeReference",
    "WorkflowApprovalPort",
]
