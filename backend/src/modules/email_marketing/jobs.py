"""Durable email-marketing handlers and tenant-bound worker entrypoints."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, TypeVar
from uuid import UUID

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import HandlerNotRegistered, execute, get_handler, register_handler
from src.core.tenancy import tenant_context_worker

from .adapters import OperationResult, VerifiedDeliveryEvent

RESOLVE_AUDIENCE_COMMAND: Final = "email_marketing.resolve_audience"
SEND_CAMPAIGN_COMMAND: Final = "email_marketing.send_campaign"
SEND_RECIPIENT_COMMAND: Final = "email_marketing.send_recipient"
RECONCILE_DELIVERY_COMMAND: Final = "email_marketing.reconcile_delivery"
PROCESS_PROVIDER_EVENT_COMMAND: Final = "email_marketing.process_provider_event"
COMMANDS: Final = (
    RESOLVE_AUDIENCE_COMMAND,
    SEND_CAMPAIGN_COMMAND,
    SEND_RECIPIENT_COMMAND,
    RECONCILE_DELIVERY_COMMAND,
    PROCESS_PROVIDER_EVENT_COMMAND,
)
ResultT = TypeVar("ResultT")


def _uuid(value: object, field_name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc


def _model_evidence(value: object) -> dict[str, object]:
    """Return only stable IDs/status; provider bodies never enter job results."""
    result: dict[str, object] = {}
    for key in ("id", "status", "provider_message_id", "gateway_key", "attempt_number"):
        candidate = getattr(value, key, None)
        if candidate is not None:
            result[key] = str(candidate) if isinstance(candidate, UUID) else candidate
    if "id" not in result:
        raise ValueError("service result did not return persisted evidence")
    return result


def _operation_evidence(result: OperationResult[ResultT]) -> dict[str, object]:
    payload: dict[str, object] = {
        "successful": result.successful,
        "code": result.code,
        "retryable": result.retryable,
        "ambiguous": result.ambiguous,
    }
    if result.value is not None:
        payload["evidence"] = _model_evidence(result.value)
    return payload


def resolve_audience_handler(job: AsyncJob) -> dict[str, object]:
    from .services import AudienceService

    campaign_id = _uuid(job.payload.get("campaign_id"), "campaign_id")
    result = AudienceService.resolve(job.tenant_id, campaign_id, _uuid(job.actor_id, "actor_id"))
    candidates = getattr(result, "candidates", None)
    resolver_key = getattr(result, "resolver_key", None)
    if isinstance(candidates, tuple) and isinstance(resolver_key, str):
        return {
            "campaign_id": str(campaign_id),
            "resolver_key": resolver_key,
            "resolved_recipient_count": len(candidates),
        }
    count = getattr(result, "resolved_count", getattr(result, "resolved_recipient_count", None))
    if not isinstance(count, int) or count < 0:
        raise ValueError("audience service did not return persisted resolution evidence")
    return {"campaign_id": str(campaign_id), "resolved_recipient_count": count}


def send_campaign_handler(job: AsyncJob) -> dict[str, object]:
    from .services import DeliveryService

    result = DeliveryService.process_campaign_job(job)
    if not isinstance(result, Mapping):
        raise ValueError("campaign delivery service must return an evidence object")
    allowed = {
        "campaign_id",
        "queued_count",
        "queued",
        "submitted_count",
        "suppressed_count",
        "failed_count",
        "remaining_count",
        "status",
    }
    unsafe = set(result) - allowed
    if unsafe:
        raise ValueError("campaign delivery result contains non-allowlisted evidence")
    return dict(result)


def send_recipient_handler(job: AsyncJob) -> dict[str, object]:
    from .services import DeliveryService

    recipient_id = _uuid(job.payload.get("recipient_id"), "recipient_id")
    result = DeliveryService.submit_recipient(job.tenant_id, recipient_id, job.id)
    if not isinstance(result, OperationResult):
        raise ValueError("recipient delivery service must return OperationResult")
    return {"recipient_id": str(recipient_id), **_operation_evidence(result)}


def reconcile_delivery_handler(job: AsyncJob) -> dict[str, object]:
    from .services import DeliveryService

    attempt_id = _uuid(job.payload.get("attempt_id"), "attempt_id")
    result = DeliveryService.reconcile_ambiguous_attempt(job.tenant_id, attempt_id)
    if not isinstance(result, OperationResult):
        raise ValueError("delivery reconciliation service must return OperationResult")
    return {"attempt_id": str(attempt_id), **_operation_evidence(result)}


def process_provider_event_handler(job: AsyncJob) -> dict[str, object]:
    from .services import DeliveryService

    gateway_key = job.payload.get("gateway_key")
    raw_event = job.payload.get("event")
    if not isinstance(gateway_key, str) or not gateway_key or len(gateway_key) > 100:
        raise ValueError("provider event command requires gateway_key")
    if not isinstance(raw_event, Mapping):
        raise ValueError("provider event command requires a verified event object")
    verified = VerifiedDeliveryEvent.from_mapping(raw_event)
    event = DeliveryService.record_provider_event(job.tenant_id, gateway_key, verified)
    return {
        "delivery_event_id": str(getattr(event, "id")),
        "event_type": str(getattr(event, "event_type")),
    }


_HANDLERS: Final = {
    RESOLVE_AUDIENCE_COMMAND: resolve_audience_handler,
    SEND_CAMPAIGN_COMMAND: send_campaign_handler,
    SEND_RECIPIENT_COMMAND: send_recipient_handler,
    RECONCILE_DELIVERY_COMMAND: reconcile_delivery_handler,
    PROCESS_PROVIDER_EVENT_COMMAND: process_provider_event_handler,
}


def register_job_handlers() -> None:
    """Install core handlers idempotently and reject every collision."""
    for command, handler in _HANDLERS.items():
        try:
            current = get_handler(command)
        except HandlerNotRegistered:
            register_handler(command, handler)
            continue
        if current is not handler:
            raise RuntimeError(f"A different async handler is already registered for {command!r}")


def _execute_expected(job_id: UUID, tenant_id: UUID, command: str) -> AsyncJob:
    AsyncJob.objects.get(id=job_id, tenant_id=tenant_id, command=command)
    return execute(job_id, tenant_id)


@tenant_context_worker
def execute_email_marketing_job(*, job_id: UUID, tenant_id: UUID) -> AsyncJob:
    """Generic broker entrypoint when the command is already trusted."""
    return execute(job_id, tenant_id)


@tenant_context_worker
def resolve_audience_worker(*, job_id: UUID, tenant_id: UUID) -> AsyncJob:
    return _execute_expected(job_id, tenant_id, RESOLVE_AUDIENCE_COMMAND)


@tenant_context_worker
def send_campaign_worker(*, job_id: UUID, tenant_id: UUID) -> AsyncJob:
    return _execute_expected(job_id, tenant_id, SEND_CAMPAIGN_COMMAND)


@tenant_context_worker
def send_recipient_worker(*, job_id: UUID, tenant_id: UUID) -> AsyncJob:
    return _execute_expected(job_id, tenant_id, SEND_RECIPIENT_COMMAND)


@tenant_context_worker
def reconcile_delivery_worker(*, job_id: UUID, tenant_id: UUID) -> AsyncJob:
    return _execute_expected(job_id, tenant_id, RECONCILE_DELIVERY_COMMAND)


@tenant_context_worker
def process_provider_event_worker(*, job_id: UUID, tenant_id: UUID) -> AsyncJob:
    return _execute_expected(job_id, tenant_id, PROCESS_PROVIDER_EVENT_COMMAND)


__all__ = [
    "COMMANDS",
    "PROCESS_PROVIDER_EVENT_COMMAND",
    "RECONCILE_DELIVERY_COMMAND",
    "RESOLVE_AUDIENCE_COMMAND",
    "SEND_CAMPAIGN_COMMAND",
    "SEND_RECIPIENT_COMMAND",
    "execute_email_marketing_job",
    "process_provider_event_handler",
    "process_provider_event_worker",
    "reconcile_delivery_handler",
    "reconcile_delivery_worker",
    "register_job_handlers",
    "resolve_audience_handler",
    "resolve_audience_worker",
    "send_campaign_handler",
    "send_campaign_worker",
    "send_recipient_handler",
    "send_recipient_worker",
]
