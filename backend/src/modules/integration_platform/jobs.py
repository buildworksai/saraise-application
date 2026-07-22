"""Durable command handlers for connector tests, synchronization, and webhooks."""

from __future__ import annotations

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import HandlerAlreadyRegistered, HandlerNotRegistered, get_handler, register_handler

from .services import IntegrationPlatformError, IntegrationService, WebhookDeliveryWorker, WebhookService


def execute_integration_test(job: AsyncJob) -> dict[str, object]:
    result = IntegrationService().execute_test(job.tenant_id, job)
    if result.status != "succeeded":
        raise result.to_exception()
    assert isinstance(result.value, dict)
    return result.value


def execute_integration_sync(job: AsyncJob) -> dict[str, object]:
    result = IntegrationService().execute_sync(job.tenant_id, job)
    if result.status != "succeeded":
        raise result.to_exception()
    assert isinstance(result.value, dict)
    return result.value


def execute_webhook_delivery(job: AsyncJob) -> dict[str, object]:
    result = WebhookDeliveryWorker().execute(job.tenant_id, job)
    # A retry/dead-letter transition is a completed orchestration command with
    # durable failure evidence; returning it prevents core from overwriting the
    # module's richer lifecycle state with an unclassified exception.
    return {
        "status": result.status,
        "delivery": dict(result.value or {}),
        "evidence": dict(result.evidence),
        "error_code": result.error_code or "",
    }


def execute_inbound_webhook(job: AsyncJob) -> dict[str, object]:
    # The open foundation validates, persists, and durably queues inbound
    # traffic.  A paid/business module must register a declared event consumer;
    # absence is explicit and can never become fabricated processing success.
    raise IntegrationPlatformError(
        "inbound_consumer_unavailable",
        "No governed inbound event consumer is registered for this webhook.",
        status_code=503,
        detail={"job_id": str(job.id)},
    )


HANDLERS = {
    IntegrationService.TEST_COMMAND: execute_integration_test,
    IntegrationService.SYNC_COMMAND: execute_integration_sync,
    WebhookService.DELIVERY_COMMAND: execute_webhook_delivery,
    WebhookService.RECEIVE_COMMAND: execute_inbound_webhook,
}


def register_job_handlers() -> None:
    """Register handlers exactly once and reject conflicting ownership."""
    for command, handler in HANDLERS.items():
        try:
            existing = get_handler(command)
        except HandlerNotRegistered:
            # Registration itself remains the duplicate ownership authority.
            pass
        else:
            if existing is not handler:
                raise HandlerAlreadyRegistered(f"A different handler owns {command!r}")
            continue
        register_handler(command, handler)


__all__ = [
    "execute_inbound_webhook", "execute_integration_sync", "execute_integration_test",
    "execute_webhook_delivery", "register_job_handlers",
]
