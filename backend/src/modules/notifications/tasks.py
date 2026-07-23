"""Tenant-bound durable command handlers for notification work.

Broker payloads are deliberately identifier-only.  Rendered content,
destinations, provider credentials, and endpoint secrets are reconstructed by
the service layer after the worker has entered the PostgreSQL tenant context.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from django.utils.dateparse import parse_datetime

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import (
    HandlerAlreadyRegistered,
    HandlerNotRegistered,
    get_handler,
    register_handler,
)
from src.core.tenancy import tenant_context_worker

EXECUTE_DELIVERY_COMMAND: Final[str] = "notifications.delivery.execute"
PROCESS_DUE_COMMAND: Final[str] = "notifications.delivery.process_due"
CONFIRM_DELIVERY_COMMAND: Final[str] = "notifications.delivery.confirm"
PURGE_RETENTION_COMMAND: Final[str] = "notifications.retention.purge"
VERIFY_ENDPOINT_COMMAND: Final[str] = "notifications.endpoint.verify"

COMMANDS: Final[tuple[str, ...]] = (
    EXECUTE_DELIVERY_COMMAND,
    PROCESS_DUE_COMMAND,
    CONFIRM_DELIVERY_COMMAND,
    PURGE_RETENTION_COMMAND,
    VERIFY_ENDPOINT_COMMAND,
)

_FORBIDDEN_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "body",
        "rendered_body",
        "rendered_subject",
        "recipient",
        "recipient_address",
        "address",
        "token",
        "secret",
        "credential",
        "credentials",
        "context_data",
    }
)


def _uuid(value: object, field_name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"async notification payload has an invalid {field_name}") from exc


def _positive_int(value: object, field_name: str, *, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"async notification payload has an invalid {field_name}")
    try:
        number = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"async notification payload has an invalid {field_name}") from exc
    if number < 1 or number > maximum:
        raise ValueError(f"async notification payload has an invalid {field_name}")
    return number


def _safe_payload(job: AsyncJob, expected_command: str) -> Mapping[str, object]:
    if not isinstance(job, AsyncJob) or job.command != expected_command:
        raise ValueError(f"handler accepts only {expected_command!r} jobs")
    if not isinstance(job.payload, Mapping):
        raise ValueError("async notification payload must be an object")
    payload = dict(job.payload)
    forbidden = {str(key).casefold() for key in payload} & _FORBIDDEN_PAYLOAD_KEYS
    if forbidden:
        raise ValueError("async notification payload contains sensitive delivery data")
    payload_tenant = _uuid(payload.get("tenant_id"), "tenant_id")
    if payload_tenant != job.tenant_id:
        raise PermissionError("async notification payload tenant does not match its durable job")
    return payload


@tenant_context_worker
def execute_delivery_worker(*, tenant_id: UUID, delivery_id: UUID) -> object:
    from .services import NotificationDispatchService

    delivery = NotificationDispatchService.execute_delivery(tenant_id, delivery_id)
    return {"delivery_id": str(delivery.id), "status": delivery.status}


@tenant_context_worker
def process_due_worker(*, tenant_id: UUID, limit: int) -> object:
    from .services import NotificationDispatchService

    results = NotificationDispatchService.process_due(tenant_id, limit)
    return {
        "processed": len(results),
        "operations": [
            {
                "operation_id": str(result.operation_id),
                "status": result.status,
                "correlation_id": str(result.correlation_id),
            }
            for result in results
        ],
    }


@tenant_context_worker
def confirm_delivery_worker(
    *,
    tenant_id: UUID,
    delivery_id: UUID,
    provider_event: Mapping[str, object],
    idempotency_key: str,
) -> object:
    from .services import NotificationDispatchService

    delivery = NotificationDispatchService.confirm_delivery(
        tenant_id,
        delivery_id,
        provider_event,
        idempotency_key,
    )
    return {"delivery_id": str(delivery.id), "status": delivery.status}


@tenant_context_worker
def purge_retention_worker(*, tenant_id: UUID, cutoff: datetime) -> object:
    from .services import NotificationDispatchService

    return dict(NotificationDispatchService.purge_expired(tenant_id, cutoff))


@tenant_context_worker
def verify_endpoint_worker(*, tenant_id: UUID, endpoint_id: UUID, actor_id: UUID) -> object:
    from .services import NotificationEndpointService

    endpoint = NotificationEndpointService.verify(tenant_id, endpoint_id, actor_id)
    return {
        "endpoint_id": str(endpoint.id),
        "verified": endpoint.last_verified_at is not None,
    }


def _execute_handler(job: AsyncJob) -> object:
    payload = _safe_payload(job, EXECUTE_DELIVERY_COMMAND)
    return execute_delivery_worker(
        tenant_id=job.tenant_id,
        delivery_id=_uuid(payload.get("delivery_id"), "delivery_id"),
    )


def _process_due_handler(job: AsyncJob) -> object:
    payload = _safe_payload(job, PROCESS_DUE_COMMAND)
    return process_due_worker(
        tenant_id=job.tenant_id,
        limit=_positive_int(payload.get("limit"), "limit", maximum=500),
    )


def _confirm_handler(job: AsyncJob) -> object:
    payload = _safe_payload(job, CONFIRM_DELIVERY_COMMAND)
    event = payload.get("provider_event")
    if not isinstance(event, Mapping):
        raise ValueError("async notification payload has an invalid provider_event")
    # The normalized event is evidence only: raw bodies, headers, signatures,
    # and recipient data must have been verified and discarded at ingress.
    allowed_event_fields = {
        "event_id",
        "event_type",
        "occurred_at",
        "provider_message_id",
        "signature_verified",
    }
    if set(event) - allowed_event_fields:
        raise ValueError("provider_event contains non-canonical fields")
    key = payload.get("idempotency_key")
    if not isinstance(key, str) or not key.strip() or len(key) > 255:
        raise ValueError("async notification payload has an invalid idempotency_key")
    return confirm_delivery_worker(
        tenant_id=job.tenant_id,
        delivery_id=_uuid(payload.get("delivery_id"), "delivery_id"),
        provider_event=dict(event),
        idempotency_key=key.strip(),
    )


def _purge_handler(job: AsyncJob) -> object:
    payload = _safe_payload(job, PURGE_RETENTION_COMMAND)
    raw_cutoff = payload.get("cutoff")
    cutoff = parse_datetime(str(raw_cutoff)) if raw_cutoff not in (None, "") else None
    if cutoff is None or cutoff.tzinfo is None:
        raise ValueError("async notification payload has an invalid cutoff")
    return purge_retention_worker(tenant_id=job.tenant_id, cutoff=cutoff)


def _verify_endpoint_handler(job: AsyncJob) -> object:
    payload = _safe_payload(job, VERIFY_ENDPOINT_COMMAND)
    return verify_endpoint_worker(
        tenant_id=job.tenant_id,
        endpoint_id=_uuid(payload.get("endpoint_id"), "endpoint_id"),
        actor_id=_uuid(job.actor_id, "actor_id"),
    )


_HANDLERS: Final[dict[str, Callable[[AsyncJob], object]]] = {
    EXECUTE_DELIVERY_COMMAND: _execute_handler,
    PROCESS_DUE_COMMAND: _process_due_handler,
    CONFIRM_DELIVERY_COMMAND: _confirm_handler,
    PURGE_RETENTION_COMMAND: _purge_handler,
    VERIFY_ENDPOINT_COMMAND: _verify_endpoint_handler,
}


def register_async_handlers() -> None:
    """Register command ownership idempotently across Django autoreload."""

    for command, handler in _HANDLERS.items():
        try:
            existing = get_handler(command)
        except HandlerNotRegistered:
            register_handler(command, handler)
            continue
        if existing is not handler:
            raise HandlerAlreadyRegistered(
                f"async command {command!r} is already owned by a different handler"
            )


__all__ = [
    "COMMANDS",
    "CONFIRM_DELIVERY_COMMAND",
    "EXECUTE_DELIVERY_COMMAND",
    "PROCESS_DUE_COMMAND",
    "PURGE_RETENTION_COMMAND",
    "VERIFY_ENDPOINT_COMMAND",
    "confirm_delivery_worker",
    "execute_delivery_worker",
    "process_due_worker",
    "purge_retention_worker",
    "register_async_handlers",
    "verify_endpoint_worker",
]
