"""Versioned, tenant-first boundary to ``workflow_automation``.

The adapter is deliberately DTO-only.  The orchestration engine never imports
workflow ORM models and a workflow implementation cannot mutate orchestration
state through this contract.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Protocol

WORKFLOW_ADAPTER_VERSION = "1.0"


@dataclass(frozen=True)
class WorkflowInvocation:
    tenant_id: uuid.UUID
    workflow_id: uuid.UUID
    actor_id: uuid.UUID
    correlation_id: str
    idempotency_token: str
    input: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowInvocationResult:
    status: str
    instance_id: uuid.UUID | None = None
    output: dict[str, object] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""

    def __post_init__(self) -> None:
        if self.status not in {"accepted", "completed", "failed", "unavailable"}:
            raise ValueError("workflow result status is invalid")
        if self.status in {"failed", "unavailable"} and not self.error_code:
            raise ValueError("failed workflow results require a stable error_code")


class WorkflowExecutionAdapter(Protocol):
    version: str

    def invoke(self, request: WorkflowInvocation) -> WorkflowInvocationResult:
        """Start a workflow idempotently for the request tenant."""

    def cancel(self, tenant_id: uuid.UUID, instance_id: uuid.UUID, idempotency_token: str) -> bool:
        """Request cancellation without exposing workflow persistence."""

    def available(self) -> bool:
        """Return whether the implementation can currently accept work."""


_lock = threading.RLock()
_adapter: WorkflowExecutionAdapter | None = None


def register_workflow_adapter(adapter: WorkflowExecutionAdapter, *, replace: bool = False) -> None:
    if getattr(adapter, "version", None) != WORKFLOW_ADAPTER_VERSION:
        raise ValueError(f"workflow adapter must implement SPI {WORKFLOW_ADAPTER_VERSION}")
    if not callable(getattr(adapter, "invoke", None)) or not callable(getattr(adapter, "cancel", None)):
        raise TypeError("workflow adapter does not implement the execution contract")
    global _adapter
    with _lock:
        if _adapter is not None and not replace:
            raise RuntimeError("workflow adapter is already registered")
        _adapter = adapter


def get_workflow_adapter() -> WorkflowExecutionAdapter:
    with _lock:
        if _adapter is None:
            raise RuntimeError("workflow execution capability is unavailable")
        return _adapter


def workflow_adapter_available() -> bool:
    try:
        adapter = get_workflow_adapter()
        return bool(adapter.available())
    except Exception:
        return False


__all__ = [
    "WORKFLOW_ADAPTER_VERSION",
    "WorkflowExecutionAdapter",
    "WorkflowInvocation",
    "WorkflowInvocationResult",
    "get_workflow_adapter",
    "register_workflow_adapter",
    "workflow_adapter_available",
]
